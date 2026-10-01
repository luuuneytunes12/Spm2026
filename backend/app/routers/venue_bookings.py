from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.db import get_db
from app.core.deps import require_role
from app.core.roles import Role
from app.models.enums import PLANNED_EVENT_STATUSES, BookingStatus
from app.models.events import Event
from app.models.user import User
from app.models.venues import Venue, VenueBooking
from app.schemas.venue_booking import VenueBookingCreate, VenueBookingOut

router = APIRouter(prefix="/venue-bookings", tags=["venue-bookings"])

# A venue is requested once the event has been approved: the story sits
# between approval and event day.
BOOKABLE_EVENT_STATUSES = PLANNED_EVENT_STATUSES

# A request that is still live: a second one for the same event would be a
# double-click or a misunderstanding. A rejected or cancelled one is history,
# so the Coordinator may try another venue.
LIVE_BOOKING_STATUSES = (BookingStatus.pending, BookingStatus.approved)

_coordinator = require_role(Role.COORDINATOR)
_venue_staff = require_role(Role.VENUE_STAFF)


def _out(booking: VenueBooking) -> VenueBookingOut:
    event = booking.event
    return VenueBookingOut(
        id=booking.id,
        status=booking.status,
        created_at=booking.created_at,
        event=event,
        venue=booking.venue,
        start_time=booking.start_time,
        end_time=booking.end_time,
        expected_attendance=event.expected_attendance,
        room_layout_preference=event.room_layout_preference,
        accessibility_needs=event.accessibility_needs,
        venue_requirements=event.venue_requirements,
        requested_by=booking.requested_by_user,
    )


def _with_relations(stmt):
    return stmt.options(
        joinedload(VenueBooking.event),
        joinedload(VenueBooking.venue),
        joinedload(VenueBooking.requested_by_user),
    )


@router.post(
    "/events/{event_id}",
    response_model=VenueBookingOut,
    status_code=status.HTTP_201_CREATED,
)
def submit_venue_booking(
    event_id: int,
    body: VenueBookingCreate,
    db: Session = Depends(get_db),
    user: User = Depends(_coordinator),
) -> VenueBookingOut:
    """Ask for a venue for an event the caller coordinates.

    404 for an event that is not assigned to the caller, the same as
    GET /events/assigned/{id}: "not yours" and "does not exist" are
    indistinguishable. The event row is locked so two overlapping submits
    (a double-clicked button) cannot both pass the duplicate check.
    """
    if body.venue_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Select a venue before submitting the booking request.",
        )

    event = db.get(Event, event_id, with_for_update=True)
    if event is None or event.coordinator_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    if event.status not in BOOKABLE_EVENT_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A venue can only be requested once the event is approved; it is '{event.status}'.",
        )
    if event.proposed_start is None or event.proposed_end is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The event has no date and time to book the venue for.",
        )

    venue = db.get(Venue, body.venue_id)
    if venue is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="That venue does not exist."
        )
    if not venue.is_active:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="That venue is inactive and cannot be booked.",
        )

    already = db.scalar(
        select(VenueBooking.id).where(
            VenueBooking.event_id == event.id,
            VenueBooking.status.in_(LIVE_BOOKING_STATUSES),
        )
    )
    if already is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This event already has a venue booking request.",
        )

    booking = VenueBooking(
        event_id=event.id,
        venue_id=venue.id,
        requested_by=user.id,
        start_time=event.proposed_start,
        end_time=event.proposed_end,
        status=BookingStatus.pending,
    )
    db.add(booking)
    db.commit()
    booking = db.scalars(_with_relations(select(VenueBooking).where(VenueBooking.id == booking.id))).one()
    return _out(booking)


@router.get("/events/{event_id}", response_model=list[VenueBookingOut])
def list_event_venue_bookings(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_coordinator),
) -> list[VenueBookingOut]:
    """The booking requests made for one event the caller coordinates,
    newest first."""
    event = db.get(Event, event_id)
    if event is None or event.coordinator_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    bookings = db.scalars(
        _with_relations(
            select(VenueBooking)
            .where(VenueBooking.event_id == event.id)
            .order_by(VenueBooking.created_at.desc(), VenueBooking.id.desc())
        )
    ).unique()
    return [_out(b) for b in bookings]


@router.get("/queue", response_model=list[VenueBookingOut])
def venue_booking_queue(
    db: Session = Depends(get_db),
    _: User = Depends(_venue_staff),
) -> list[VenueBookingOut]:
    """Pending booking requests for Venue Staff to review, oldest first."""
    bookings = db.scalars(
        _with_relations(
            select(VenueBooking)
            .where(VenueBooking.status == BookingStatus.pending)
            .order_by(VenueBooking.created_at, VenueBooking.id)
        )
    ).unique()
    return [_out(b) for b in bookings]


@router.get("/{booking_id}", response_model=VenueBookingOut)
def get_venue_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(_venue_staff),
) -> VenueBookingOut:
    booking = db.scalars(
        _with_relations(select(VenueBooking).where(VenueBooking.id == booking_id))
    ).unique().first()
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking request not found")
    return _out(booking)
