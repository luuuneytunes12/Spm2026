from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.db import get_db
from app.core.deps import require_role
from app.core.roles import Role
from app.models.enums import PLANNED_EVENT_STATUSES, BookingStatus
from app.models.events import Event
from app.models.user import User
from app.models.venues import Venue, VenueBooking, VenueUnavailability
from app.schemas.venue_booking import VenueBookingCreate, VenueBookingOut, VenueBookingRejection

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
        decision_notes=booking.decision_notes,
        suggested_alternative=booking.suggested_alternative,
        safety_recheck_reason=booking.safety_recheck_reason,
        reviewed_by=booking.reviewed_by_user,
        reviewed_at=booking.reviewed_at,
    )


def _with_relations(stmt):
    return stmt.options(
        joinedload(VenueBooking.event),
        joinedload(VenueBooking.venue),
        joinedload(VenueBooking.requested_by_user),
        joinedload(VenueBooking.reviewed_by_user),
    )


# Awaiting a Venue Staff decision: a new request, or an approved booking a
# Safety Officer has sent back for another look (still holding the venue).
_AWAITING_DECISION = or_(
    VenueBooking.status == BookingStatus.pending,
    and_(
        VenueBooking.status == BookingStatus.approved,
        VenueBooking.safety_recheck_reason.is_not(None),
    ),
)


def _pending_for_decision(booking_id: int, db: Session) -> VenueBooking:
    """The request Venue Staff are about to decide on, row-locked.

    The lock is what makes a decision final: two overlapping decisions (a
    double-click, or two staff on the same request) cannot both find it
    pending, so the second is refused instead of overwriting the first.
    An approved booking flagged for safety re-review is decided again the
    same way; either decision clears the flag.
    """
    booking = db.get(VenueBooking, booking_id, with_for_update=True)
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking request not found")
    if booking.status == BookingStatus.approved and booking.safety_recheck_reason:
        return booking
    if booking.status != BookingStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This booking request has already been {booking.status}.",
        )
    return booking


def _decide(booking: VenueBooking, decision: BookingStatus, staff: User, db: Session) -> VenueBookingOut:
    """Record the outcome with who decided and when, and return it."""
    booking.status = decision
    booking.safety_recheck_reason = None
    booking.reviewed_by = staff.id
    booking.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    booking = db.scalars(_with_relations(select(VenueBooking).where(VenueBooking.id == booking.id))).one()
    return _out(booking)


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
    """Booking requests for Venue Staff to review, oldest first: pending
    ones, and approved ones a Safety Officer has sent back."""
    bookings = db.scalars(
        _with_relations(
            select(VenueBooking)
            .where(_AWAITING_DECISION)
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


@router.post("/{booking_id}/approve", response_model=VenueBookingOut)
def approve_venue_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_venue_staff),
) -> VenueBookingOut:
    """Approve a pending request, confirming the venue for the event.

    Refused when the venue is no longer free for that time -- already
    confirmed for another event, or blocked out -- since approving would
    double-book it. The venue row is locked so two requests for the same
    venue and time, approved at the same moment, cannot both get through.
    """
    booking = _pending_for_decision(booking_id, db)
    db.get(Venue, booking.venue_id, with_for_update=True)

    # Same overlap rule as the venue search: each starts before the other
    # ends, so back-to-back bookings do not clash.
    taken = db.scalar(
        select(VenueBooking.id).where(
            VenueBooking.venue_id == booking.venue_id,
            VenueBooking.id != booking.id,
            VenueBooking.status == BookingStatus.approved,
            VenueBooking.start_time < booking.end_time,
            VenueBooking.end_time > booking.start_time,
        )
    )
    if taken is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The venue is already booked for another event at that time.",
        )
    blocked = db.scalar(
        select(VenueUnavailability.id).where(
            VenueUnavailability.venue_id == booking.venue_id,
            VenueUnavailability.start_time < booking.end_time,
            VenueUnavailability.end_time > booking.start_time,
        )
    )
    if blocked is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The venue is marked unavailable at that time.",
        )

    return _decide(booking, BookingStatus.approved, user, db)


@router.post("/{booking_id}/reject", response_model=VenueBookingOut)
def reject_venue_booking(
    booking_id: int,
    body: VenueBookingRejection,
    db: Session = Depends(get_db),
    user: User = Depends(_venue_staff),
) -> VenueBookingOut:
    """Reject a pending request, telling the Coordinator why, what to try
    instead, or both. The event is then free to be requested again."""
    if body.reason is None and body.suggested_alternative is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Give a reason, an alternative, or both before rejecting.",
        )
    booking = _pending_for_decision(booking_id, db)
    booking.decision_notes = body.reason
    booking.suggested_alternative = body.suggested_alternative
    return _decide(booking, BookingStatus.rejected, user, db)
