"""Coordinator assignment: picking one, and leaving a record behind.

Shared by two entry points -- POST /events/{id}/submit (initial assignment)
and PATCH /coordinators/me/availability (reassignment when one goes
unavailable) -- so both follow the same selection rule and leave the same
kind of trail. See the "Mark myself unavailable" story:

    As an Event Coordinator, I want to mark myself as unavailable, so that
    my assigned events are automatically reassigned to another coordinator.
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.roles import Role
from app.models.enums import EventStatus
from app.models.events import Event, EventStatusHistory
from app.models.notifications import Notification
from app.models.user import User

# Statuses under which an event still needs an active Coordinator working
# it. COMPLETED, CANCELLED and REJECTED are exits from the pipeline -- an
# event there does not need reassigning just because its (former)
# Coordinator has gone unavailable.
ACTIVE_ASSIGNMENT_STATUSES: tuple[EventStatus, ...] = (
    EventStatus.submitted,
    EventStatus.under_review,
    EventStatus.changes_requested,
    EventStatus.approved,
    EventStatus.planning,
    EventStatus.confirmed,
)


def _pick_coordinator(db: Session, *, exclude_id: int | None = None) -> User | None:
    """The available Coordinator with the lightest current load, or None.

    "Load" is how many events are assigned to them under an
    ACTIVE_ASSIGNMENT_STATUSES status -- the same set this module reassigns
    out of. Ties are broken by id, so the choice is deterministic rather
    than whatever order the database happens to return rows in.
    """
    query = db.query(User).filter(User.role == Role.COORDINATOR.value, User.is_available.is_(True))
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
    a status change (the event was already under review; only who is
    reviewing it changes), so `from_status` and `to_status` are both the
    event's current status and the note carries the real information. See
    AssignedEventView's ActivityLine on the frontend for how a same-status
    entry renders as "Assignment" rather than a status arrow into itself.

    An INITIAL assignment does not go through here -- see
    `assign_coordinator`, which writes its own EventStatusHistory row
    because that one genuinely does change status (submitted -> under
    review).
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
    db.add(
        Notification(
            user_id=coordinator_id,
            event_id=event.id,
            type="event_assigned",
            message=f"You have been assigned to coordinate '{event.name or 'an event'}'.",
        )
    )


def assign_coordinator(db: Session, event: Event, actor_id: int) -> User | None:
    """Auto-assign an available Coordinator to a freshly submitted event.

    Returns the Coordinator assigned, or None if nobody is available -- the
    event is left unassigned rather than the submission failing. Silent in
    that case: there is no assignment to log yet, and an Organiser still
    sees their request went through, just not yet picked up.

    Being assigned IS what "under review" means: a submitted request that
    already has a Coordinator on it but still reads "Submitted" is
    misleading to the very person now responsible for it. So this is a real
    status transition, not just a same-status note -- unlike
    `reassign_event`, which never changes status (the event was already
    under review; only who is reviewing it changes).
    """
    coordinator = _pick_coordinator(db)
    if coordinator is None:
        return None

    event.coordinator_id = coordinator.id
    previous_status = event.status
    if event.status == EventStatus.submitted:
        event.status = EventStatus.under_review

    db.add(
        EventStatusHistory(
            event_id=event.id,
            changed_by=actor_id,
            from_status=previous_status,
            to_status=event.status,
            note=f"Assigned to {coordinator.name}.",
        )
    )
    _notify(db, coordinator.id, event)
    return coordinator


def reassign_event(db: Session, event: Event, outgoing: User) -> User | None:
    """Move `event` off `outgoing` onto another available Coordinator.

    `outgoing` is both whose events these are and who is recorded as having
    made the change -- it is their own availability toggle that triggers
    this. Returns the new Coordinator, or None if nobody else is available
    (the event is left unassigned rather than stuck with someone who
    cannot work on it).

    Both sides are notified: the new Coordinator that they now own it (same
    as an initial assignment), and `outgoing` that it moved on and to whom
    -- otherwise the only way they would find out is by noticing it missing
    from their own list.
    """
    coordinator = _pick_coordinator(db, exclude_id=outgoing.id)
    event.coordinator_id = coordinator.id if coordinator else None
    if coordinator is None:
        return None

    _record(
        db,
        event,
        outgoing.id,
        f"Reassigned from {outgoing.name} to {coordinator.name}: "
        f"{outgoing.name} marked themselves unavailable.",
    )
    _notify(db, coordinator.id, event)
    db.add(
        Notification(
            user_id=outgoing.id,
            event_id=event.id,
            type="event_reassigned_away",
            message=(
                f"{coordinator.name} has taken over coordinating "
                f"'{event.name or 'an event'}' (previously assigned to you)."
            ),
        )
    )
    return coordinator


def events_needing_reassignment(db: Session, coordinator_id: int) -> list[Event]:
    """Events currently active under `coordinator_id`'s watch.

    What `reassign_event` should be called for, one by one, when that
    Coordinator marks themselves unavailable.
    """
    return (
        db.query(Event)
        .filter(Event.coordinator_id == coordinator_id, Event.status.in_(ACTIVE_ASSIGNMENT_STATUSES))
        .all()
    )
