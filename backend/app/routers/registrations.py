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


def _utc(value: datetime) -> datetime:
    # SQLite (the test DB) hands back naive datetimes; Postgres timestamptz
    # hands back aware ones. Both are stored as UTC.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def registration_open(event: Event) -> bool:
    """The single definition of "can someone register for this right now".

    Open means: the event is confirmed and registration is enabled. When the
    Coordinator has set a registration window, today must fall between its
    open and close dates. An event with no window (registration switched on
    before windows existed) falls back to the old rule: open until it starts.
    """
    if event.status != EventStatus.confirmed or not event.registration_enabled:
        return False
    now = datetime.now(timezone.utc)
    if event.registration_opens_at is not None and event.registration_closes_at is not None:
        return _utc(event.registration_opens_at) <= now <= _utc(event.registration_closes_at)
    if event.proposed_start is None:
        return True
    return _utc(event.proposed_start) > now


def _out(event: Event, registration: Registration | None) -> RegistrableEvent:
    return RegistrableEvent(
        id=event.id,
        name=event.name,
        proposed_start=event.proposed_start,
        proposed_end=event.proposed_end,
        registration_open=registration_open(event),
        registration_opens_at=event.registration_opens_at,
        registration_closes_at=event.registration_closes_at,
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


@router.get("/mine", response_model=list[RegistrableEvent])
def list_my_registrations(
    db: Session = Depends(get_db),
    user: User = Depends(_attendee),
) -> list[RegistrableEvent]:
    """Every event the caller has registered for -- including ones they have
    since withdrawn from, which stay listed with that status.

    One row per event: the table is unique on (event_id, attendee_id), and
    re-registering flips the same row back to `registered` rather than adding
    a second. Never registered means an empty list. Soonest event first.
    """
    rows = (
        db.query(Event, Registration)
        .join(Registration, Registration.event_id == Event.id)
        .filter(Registration.attendee_id == user.id)
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
        opens = event.registration_opens_at
        not_yet_open = opens is not None and _utc(opens) > datetime.now(timezone.utc)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Registration for this event has not opened yet."
                if not_yet_open
                else "Registration for this event has closed."
            ),
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
