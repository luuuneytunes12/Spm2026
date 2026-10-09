"""Shared assignment notifications, activity logging, and coordinator pool.

Production assignment is Lead-managed through `lead_assignment`; the legacy
automatic selector remains only as a test setup helper.
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.roles import Role
from app.models.enums import ACTIVE_ASSIGNMENT_STATUSES, NotificationType
from app.models.events import Event, EventStatusHistory
from app.models.user import User
from app.services.notifications import notify


def available_coordinators(db: Session):
    """Query for the assignment pool: Coordinators who are marked available.

    The one definition of "can be assigned a new event" -- `_pick_coordinator`
    chooses from it and the Organiser-facing count reports its size, so the
    two can never disagree about who is in the pool.
    """
    return db.query(User).filter(
        User.role == Role.COORDINATOR.value, User.is_available.is_(True)
    )


def _pick_coordinator(db: Session, *, exclude_id: int | None = None) -> User | None:
    """The available Coordinator with the lightest current load, or None.

    "Load" is how many events are assigned to them under an
    ACTIVE_ASSIGNMENT_STATUSES status -- the same set this module reassigns
    out of. Ties are broken by id, so the choice is deterministic rather
    than whatever order the database happens to return rows in.
    """
    query = available_coordinators(db)
    if exclude_id is not None:
        query = query.filter(User.id != exclude_id)
    candidates = query.all()
    if not candidates:
        return None

    counts = dict(
        db.query(Event.coordinator_id, func.count(Event.id))
        .filter(
            Event.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
            Event.coordinator_id.in_([c.id for c in candidates]),
        )
        .group_by(Event.coordinator_id)
        .all()
    )
    return min(candidates, key=lambda c: (counts.get(c.id, 0), c.id))


def _record(db: Session, event: Event, actor_id: int, note: str) -> None:
    """One activity-log line for a REASSIGNMENT.

    Reuses EventStatusHistory rather than a new table. A reassignment isn't
    a status change (only who owns the active event changes), so `from_status` and `to_status` are both the
    event's current status and the note carries the real information. See
    AssignedEventView's ActivityLine on the frontend for how a same-status
    entry renders as "Assignment" rather than a status arrow into itself.

    Initial Lead assignment keeps the Submitted status and is implemented by
    `services.lead_assignment.AssignEvent`.
    """
    db.add(
        EventStatusHistory(
            event_id=event.id,
            changed_by=actor_id,
            from_status=event.status,
            to_status=event.status,
            note=note,
        )
    )


def _notify(db: Session, coordinator_id: int, event: Event) -> None:
    # Written in the caller's transaction, pushed live only once it commits.
    notify(
        db,
        user_id=coordinator_id,
        type=NotificationType.event_assigned,
        message=f"You have been assigned to coordinate '{event.name or 'an event'}'.",
        event_id=event.id,
    )


def _notify_organiser(db: Session, event: Event, coordinator: User) -> None:
    """Tell the Organiser who is now coordinating their event, and how to reach them.

    A notification, not an activity-log line: the log (EventStatusHistory)
    is the event's shared record, readable by everyone involved in it, while
    this goes only to the Organiser -- the one role whose question is "who
    owns my request?". The Coordinator gets their own, differently worded
    notification from `_notify`. The name and email match what EventView's
    "Your Assigned Event Coordinator" card shows.
    """
    notify(
        db,
        user_id=event.organiser_id,
        type=NotificationType.event_coordinator_assigned,
        message=(
            f"{coordinator.name} ({coordinator.email}) is now coordinating "
            f"'{event.name or 'your event'}'."
        ),
        event_id=event.id,
    )


def assign_coordinator(db: Session, event: Event, actor_id: int) -> User | None:
    """Legacy helper for tests that need to seed an assigned event.

    Production submissions are not auto-assigned. New assignment is handled
    by the Coordinator Lead through `services.lead_assignment.AssignEvent`.
    Returns the selected Coordinator or None.

    Kept for test setup and migration compatibility; assignment does not
    change the event's single authoritative status.
    """
    coordinator = _pick_coordinator(db)
    if coordinator is None:
        return None

    event.coordinator_id = coordinator.id
    db.add(
        EventStatusHistory(
            event_id=event.id,
            changed_by=actor_id,
            from_status=event.status,
            to_status=event.status,
            note=f"Assigned to {coordinator.name}.",
        )
    )
    _notify(db, coordinator.id, event)
    _notify_organiser(db, event, coordinator)
    return coordinator


def reassign_event(db: Session, event: Event, outgoing: User) -> User | None:
    """Move `event` off `outgoing` onto another available Coordinator.

    Legacy helper for an outgoing Coordinator declining an event. Production
    assignment changes are managed by the Lead.
    `outgoing` is recorded as having made the change -- in the activity log
    whether or not anyone takes over. Returns the new Coordinator, or None
    if nobody else is available (the event is left unassigned rather than
    stuck with someone who declined it).

    All three sides are notified: the new Coordinator that they now own it
    (same as an initial assignment), `outgoing` that it moved on and to whom
    -- otherwise the only way they would find out is by noticing it missing
    from their own list -- and the Organiser, with the new Coordinator's
    name and email.
    """
    coordinator = _pick_coordinator(db, exclude_id=outgoing.id)
    event.coordinator_id = coordinator.id if coordinator else None
    if coordinator is None:
        # The decline still happened and must be on the record: with nobody
        # to take over, the event is now unassigned, which is exactly when
        # who let go of it, and when, is worth knowing.
        _record(
            db,
            event,
            outgoing.id,
            f"{outgoing.name} declined this event; no other Coordinator was "
            "available, so it is now unassigned.",
        )
        return None

    _record(
        db,
        event,
        outgoing.id,
        f"Reassigned from {outgoing.name} to {coordinator.name}: "
        f"{outgoing.name} declined this event.",
    )
    _notify(db, coordinator.id, event)
    notify(
        db,
        user_id=outgoing.id,
        type=NotificationType.event_reassigned_away,
        message=(
            f"{coordinator.name} has taken over coordinating "
            f"'{event.name or 'an event'}' (previously assigned to you)."
        ),
        event_id=event.id,
    )
    _notify_organiser(db, event, coordinator)
    return coordinator
