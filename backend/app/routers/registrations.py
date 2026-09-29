from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_role
from app.core.roles import Role
from app.models.enums import EventStatus, RegistrationStatus
from app.models.events import Event
from app.models.registrations import Registration
from app.models.user import User
from app.schemas.registration import RegistrableEvent

router = APIRouter(prefix="/registrations", tags=["registrations"])

# Registering is something an Attendee does for THEMSELVES, so it is gated on
# identity rather than a permission. REGISTRATION_MANAGE is the Coordinator's
# "manage other people's registrations" and is deliberately not reused here.
_attendee = require_role(Role.ATTENDEE)


def registration_open(event: Event) -> bool:
    """The single definition of "can someone register for this right now".

    Open means: the event is confirmed, its Organiser enabled registration,
    and it has not started yet. There is no separate closing date on
    `events`, so the start time is what closes registration.
    """
    if event.status != EventStatus.confirmed or not event.registration_enabled:
        return False
    if event.proposed_start is None:
        return True
    start = event.proposed_start
    # SQLite (the test DB) hands back naive datetimes; Postgres timestamptz
    # hands back aware ones. Both are stored as UTC.
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return start > datetime.now(timezone.utc)


def _out(event: Event, registration: Registration | None) -> RegistrableEvent:
    return RegistrableEvent(
        id=event.id,
        name=event.name,
        proposed_start=event.proposed_start,
        proposed_end=event.proposed_end,
        registration_open=registration_open(event),
        my_status=registration.status if registration else None,
    )


def _my_registration(event_id: int, user: User, db: Session) -> Registration | None:
    return (
        db.query(Registration)
        .filter(Registration.event_id == event_id, Registration.attendee_id == user.id)
        .one_or_none()
    )


@router.get("/events", response_model=list[RegistrableEvent])
def list_registrable_events(
    db: Session = Depends(get_db),
    user: User = Depends(_attendee),
) -> list[RegistrableEvent]:
    """Confirmed events that take registrations, plus any event the caller
    has a registration for (so a registration never vanishes from view just
    because the event later closed). Soonest first."""
    rows = (
        db.query(Event, Registration)
        .outerjoin(
            Registration,
            and_(Registration.event_id == Event.id, Registration.attendee_id == user.id),
        )
        .filter(
            or_(
                and_(Event.status == EventStatus.confirmed, Event.registration_enabled.is_(True)),
                Registration.id.is_not(None),
            )
        )
        .order_by(Event.proposed_start, Event.id)
        .all()
    )
    return [_out(event, registration) for event, registration in rows]


@router.post("/events/{event_id}", response_model=RegistrableEvent)
def register(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_attendee),
) -> RegistrableEvent:
    """Register the caller, or re-register them after a withdrawal.

    A withdrawn registration is flipped back on the SAME row: the table is
    unique on (event_id, attendee_id), so there is only ever one row per
    Attendee per event.
    """
    event = db.get(Event, event_id)
    registration = _my_registration(event_id, user, db) if event else None
    # Events an Attendee could never register for are "not found" -- the
    # same principle as _get_own_event: this must not probe draft ids.
    if event is None or (
        registration is None
        and (event.status != EventStatus.confirmed or not event.registration_enabled)
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    if registration is not None and registration.status == RegistrationStatus.registered:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You are already registered for this event.",
        )
    if not registration_open(event):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Registration for this event has closed.",
        )

    if registration is None:
        registration = Registration(event_id=event.id, attendee_id=user.id)
        db.add(registration)
    else:
        registration.registered_at = datetime.now(timezone.utc)
        registration.withdrawn_at = None
    registration.status = RegistrationStatus.registered

    try:
        db.commit()
    except IntegrityError:
        # A concurrent request (double click) inserted the row first.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You are already registered for this event.",
        ) from None
    db.refresh(registration)
    return _out(event, registration)


@router.post("/events/{event_id}/withdraw", response_model=RegistrableEvent)
def withdraw(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_attendee),
) -> RegistrableEvent:
    """Release the caller's place. Allowed even after registration closes --
    giving a place back late is still better than not giving it back."""
    registration = _my_registration(event_id, user, db)
    if registration is None or registration.status != RegistrationStatus.registered:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You are not registered for this event.",
        )

    registration.status = RegistrationStatus.withdrawn
    registration.withdrawn_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(registration)
    return _out(registration.event, registration)
