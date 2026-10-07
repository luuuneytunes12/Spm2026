"""The Safety Officer's Operational Safety Check.

An event the Coordinator has submitted waits in `awaiting_safety_check`.
The Safety Officer either passes it (-> `confirmed`, "Safety Check Passed
(Event Confirmed)") or sends it back to `planning`, flagging the bookings and
equipment lines that need another look. Flagged items keep their status --
the venue stays booked and the stock reserved -- until their staff clear the
flag; until then the event cannot be submitted or passed again.

Gated on the role, not a permission: the Organiser holds every permission,
and must not be able to pass their own event.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_role
from app.core.roles import Role
from app.domain.event_readiness import outstanding_arrangements
from app.models.enums import BookingStatus, EquipmentStatus, EventStatus, NotificationType
from app.models.equipment import EquipmentRequest
from app.models.events import Event, EventStatusHistory
from app.models.user import User
from app.models.venues import VenueBooking
from app.routers.events import _event_activity
from app.schemas.event import EventOut, OrganiserContact
from app.schemas.safety_check import (
    SafetyChangesIn,
    SafetyCheckDetail,
    SafetyCheckSummary,
    SafetyEquipmentLine,
    SafetyReasonIn,
    SafetyVenueBooking,
)
from app.services.notifications import notify

router = APIRouter(prefix="/safety-checks", tags=["safety-checks"])

_safety_officer = require_role(Role.SAFETY_OFFICER)


def _get_event(event_id: int, db: Session, *, lock: bool = False) -> Event:
    event = db.get(Event, event_id, with_for_update=lock)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event


def _awaiting_decision(event_id: int, db: Session) -> Event:
    """The event about to be decided, row-locked so two overlapping decisions
    cannot both find it awaiting a check."""
    event = _get_event(event_id, db, lock=True)
    if event.status != EventStatus.awaiting_safety_check:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Only an event awaiting a safety check can be decided; this one is '{event.status}'.",
        )
    return event


def _approved_booking(db: Session, event: Event) -> VenueBooking | None:
    return db.scalar(
        select(VenueBooking).where(
            VenueBooking.event_id == event.id,
            VenueBooking.status == BookingStatus.approved,
        )
    )


def _reserved_lines(event: Event) -> list[EquipmentRequest]:
    return [line for line in event.equipment_items if line.status is EquipmentStatus.reserved]


def _record(db: Session, event: Event, officer: User, to_status: EventStatus, note: str) -> None:
    db.add(
        EventStatusHistory(
            event_id=event.id,
            changed_by=officer.id,
            from_status=event.status,
            to_status=to_status,
            note=note,
        )
    )
    event.status = to_status


def _notify_all(
    db: Session,
    event: Event,
    staff_ids: set[int | None],
    type: NotificationType,
    message: str,
) -> None:
    """Tell the Organiser, the Coordinator and the given staff, once each."""
    recipients = {event.organiser_id, event.coordinator_id, *staff_ids} - {None}
    for user_id in sorted(recipients):
        notify(db, user_id=user_id, type=type, message=message, event_id=event.id)


def _send_back(
    db: Session,
    event: Event,
    officer: User,
    bookings: list[VenueBooking],
    lines: list[EquipmentRequest],
    *,
    reason: str,
    note: str,
    type: NotificationType,
    message: str,
) -> EventOut:
    """Return the event to planning with `bookings` and `lines` flagged for
    re-review. Nothing is cancelled or released."""
    for item in [*bookings, *lines]:
        item.safety_recheck_reason = reason
    _record(db, event, officer, EventStatus.planning_event, note)
    _notify_all(db, event, {item.reviewed_by for item in [*bookings, *lines]}, type, message)
    db.commit()
    db.refresh(event)
    return EventOut.model_validate(event)


@router.get("", response_model=list[SafetyCheckSummary])
def safety_check_queue(
    db: Session = Depends(get_db),
    _: User = Depends(_safety_officer),
) -> list[SafetyCheckSummary]:
    """Events awaiting a safety check, soonest first. Empty when there are none."""
    events = db.scalars(
        select(Event)
        .where(Event.status == EventStatus.awaiting_safety_check)
        .order_by(Event.proposed_start, Event.id)
    )
    return [
        SafetyCheckSummary(
            id=event.id,
            name=event.name,
            proposed_start=event.proposed_start,
            proposed_end=event.proposed_end,
            coordinator=OrganiserContact.model_validate(event.coordinator) if event.coordinator else None,
        )
        for event in events
    ]


@router.get("/{event_id}", response_model=SafetyCheckDetail)
def get_safety_check(
    event_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(_safety_officer),
) -> SafetyCheckDetail:
    """An event's attendance, venue, accessibility needs and equipment."""
    event = _get_event(event_id, db)
    booking = _approved_booking(db, event)
    return SafetyCheckDetail(
        id=event.id,
        name=event.name,
        status=event.status,
        proposed_start=event.proposed_start,
        proposed_end=event.proposed_end,
        expected_attendance=event.expected_attendance,
        room_layout_preference=event.room_layout_preference,
        accessibility_needs=event.accessibility_needs,
        special_arrangements=event.special_arrangements,
        organiser=OrganiserContact.model_validate(event.organiser),
        coordinator=OrganiserContact.model_validate(event.coordinator) if event.coordinator else None,
        venue_booking=SafetyVenueBooking.model_validate(booking) if booking else None,
        equipment=[
            SafetyEquipmentLine.model_validate(line)
            for line in event.equipment_items
            if line.status is not EquipmentStatus.cancelled
        ],
        activity=_event_activity(db, event.id),
    )


@router.post("/{event_id}/approve", response_model=EventOut)
def approve_safety_check(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_safety_officer),
) -> EventOut:
    """Pass the event: it is confirmed and may proceed to preparation.

    Refused while any arrangement is no longer approved / reserved -- staff
    may have changed it since the Coordinator submitted.
    """
    event = _awaiting_decision(event_id, db)
    outstanding = outstanding_arrangements(db, event)
    if outstanding:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot approve. Outstanding: " + "; ".join(outstanding) + ".",
        )

    booking = _approved_booking(db, event)
    staff = {booking.reviewed_by if booking else None, *(line.reviewed_by for line in _reserved_lines(event))}
    _record(db, event, user, EventStatus.safety_check_passed, "Safety Check passed by the Safety Officer.")
    _notify_all(
        db,
        event,
        staff,
        NotificationType.safety_check_passed,
        f"'{event.name or 'Event'}' passed its Safety Check and is confirmed.",
    )
    db.commit()
    db.refresh(event)
    return EventOut.model_validate(event)


@router.post("/{event_id}/request-changes", response_model=EventOut)
def request_safety_changes(
    event_id: int,
    body: SafetyChangesIn,
    db: Session = Depends(get_db),
    user: User = Depends(_safety_officer),
) -> EventOut:
    """Send the event back to planning with only the marked items to review."""
    event = _awaiting_decision(event_id, db)
    if not body.venue_booking_ids and not body.equipment_request_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Mark at least one venue booking or equipment item to change.",
        )

    booking = _approved_booking(db, event)
    bookings = [booking] if booking and booking.id in body.venue_booking_ids else []
    lines = [line for line in _reserved_lines(event) if line.id in body.equipment_request_ids]
    if len(bookings) != len(set(body.venue_booking_ids)) or len(lines) != len(
        set(body.equipment_request_ids)
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only this event's approved venue booking and reserved equipment can be marked.",
        )

    return _send_back(
        db,
        event,
        user,
        bookings,
        lines,
        reason=body.reason,
        note=f"Safety changes requested: {body.reason}",
        type=NotificationType.safety_changes_requested,
        message=f"Safety changes requested for '{event.name or 'Event'}': {body.reason}",
    )


@router.post("/{event_id}/reject", response_model=EventOut)
def reject_safety_check(
    event_id: int,
    body: SafetyReasonIn,
    db: Session = Depends(get_db),
    user: User = Depends(_safety_officer),
) -> EventOut:
    """Reject the safety arrangement: back to planning with every venue and
    equipment arrangement to review again. Nothing is cancelled."""
    event = _awaiting_decision(event_id, db)
    booking = _approved_booking(db, event)
    return _send_back(
        db,
        event,
        user,
        [booking] if booking else [],
        _reserved_lines(event),
        reason=body.reason,
        note=f"Safety arrangement rejected: {body.reason}",
        type=NotificationType.safety_check_rejected,
        message=f"The safety arrangement for '{event.name or 'Event'}' was rejected: {body.reason}",
    )
