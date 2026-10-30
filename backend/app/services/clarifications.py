"""Clarification exchange between an Event's Coordinator and Organiser
(SCRUM-27 request, SCRUM-103 reply)."""

from sqlalchemy.orm import Session

from app.models.clarifications import EventClarification
from app.models.enums import EventStatus, NotificationType
from app.models.events import Event, EventStatusHistory
from app.models.user import User
from app.schemas.clarification import ClarificationOut
from app.schemas.event import EventIn
from app.services.equipment_lines import replace_equipment_lines
from app.services.notifications import notify
from app.services.tech_support_notices import notify_if_rescheduled
from app.services.venue_staff_notices import ApprovedEventChangedNotice


def to_out(row: EventClarification) -> ClarificationOut:
    return ClarificationOut(
        id=row.id,
        event_id=row.event_id,
        kind=row.kind,
        message=row.message,
        author_id=row.author_id,
        author_name=row.author.name,
        created_at=row.created_at,
    )


def _record(db: Session, event: Event, user: User, kind: str, message: str, to: EventStatus, note: str):
    """Save the message, move the status and log both, in the caller's transaction."""
    row = EventClarification(event_id=event.id, kind=kind, message=message, author_id=user.id)
    db.add(row)
    db.add(
        EventStatusHistory(
            event_id=event.id,
            changed_by=user.id,
            from_status=event.status,
            to_status=to,
            note=note,
        )
    )
    event.status = to
    db.flush()
    db.refresh(row)
    return row


def request_clarification(db: Session, event: Event, coordinator: User, message: str) -> EventClarification:
    row = _record(
        db, event, coordinator, "request", message, EventStatus.awaiting_organiser_reply, message
    )
    notify(
        db,
        user_id=event.organiser_id,
        type=NotificationType.clarification_requested,
        message=f"{coordinator.name} needs clarification on '{event.name or 'your event'}'. Open it to read and reply.",
        event_id=event.id,
    )
    return row


def _apply_updates(db: Session, event: Event, updates: EventIn) -> list[str]:
    """Apply the amended fields; returns 'field: old -> new' lines."""
    changes = updates.model_dump(exclude_unset=True)
    summary: list[str] = []
    if "equipment_items" in changes:
        changes.pop("equipment_items")
        replace_equipment_lines(db, event, updates.equipment_items or [])
        summary.append("equipment_items updated")
    for field, value in changes.items():
        if field == "registration_enabled" and value is None:
            continue
        old = getattr(event, field)
        if old != value:
            summary.append(f"{field}: {old if old is not None else '(empty)'} -> {value if value is not None else '(empty)'}")
        setattr(event, field, value)
    return summary


def reply_to_clarification(
    db: Session, event: Event, organiser: User, message: str, updates: EventIn | None
) -> EventClarification:
    note = message
    if updates is not None:
        old_start, old_end = event.proposed_start, event.proposed_end
        venue_staff_before = ApprovedEventChangedNotice.before(db, event)
        summary = _apply_updates(db, event, updates)
        notify_if_rescheduled(db, event, old_start, old_end)
        ApprovedEventChangedNotice.since(venue_staff_before, event).send(db, event)
        if summary:
            note = f"{message}\nChanged: " + "; ".join(summary)
    row = _record(db, event, organiser, "reply", message, EventStatus.under_review, note)
    if event.coordinator_id is not None:
        notify(
            db,
            user_id=event.coordinator_id,
            type=NotificationType.clarification_replied,
            # The Event's Organiser, loaded: the signed-in user a route is
            # given is built from the token and has no name.
            message=f"{event.organiser.name} replied to your clarification request on '{event.name or 'the event'}'.",
            event_id=event.id,
        )
    return row
