from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.db import get_db
from app.core.deps import require_role
from app.core.roles import Role
from app.models.enums import BookingStatus, EventStatus, NotificationType
from app.models.events import Event, EventStatusHistory
from app.models.user import User
from app.models.venues import Venue, VenueBooking, VenueUnavailability
from app.schemas.venue_booking import (
    VenueBookingCreate,
    VenueBookingOut,
    VenueBookingRejection,
    VenueHoldIn,
)
from app.routers.venues import expire_tentative_holds
from app.services.notifications import notify

router = APIRouter(prefix="/venue-bookings", tags=["venue-bookings"])

# Venues are requested while the event is being planned: once approved, and
# for as long as it stays in planning. After it goes to the Safety Officer
# the arrangement is judged as it stands.
BOOKABLE_EVENT_STATUSES = (EventStatus.event_approved, EventStatus.planning_event)

LIVE_BOOKING_STATUSES = (
    BookingStatus.pending,
    BookingStatus.tentative_hold,
    BookingStatus.approved,
)

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
        room_layout_preference=booking.room_layout_preference or event.room_layout_preference,
        accessibility_needs=booking.accessibility_needs or event.accessibility_needs,
        facilities_needs=booking.facilities_needs or event.venue_requirements,
        venue_requirements=event.venue_requirements,
        requested_by=booking.requested_by_user,
        decision_notes=booking.decision_notes,
        suggested_alternative=booking.suggested_alternative,
        expires_at=booking.expires_at,
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
    VenueBooking.status == BookingStatus.tentative_hold,
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
    expire_tentative_holds(db)
    booking = db.get(VenueBooking, booking_id, with_for_update=True)
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking request not found")
    if booking.status == BookingStatus.approved and booking.safety_recheck_reason:
        return booking
    if booking.status == BookingStatus.tentative_hold:
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
    if decision != BookingStatus.tentative_hold:
        booking.expires_at = None
    booking.safety_recheck_reason = None
    booking.reviewed_by = staff.id
    booking.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    booking = db.scalars(_with_relations(select(VenueBooking).where(VenueBooking.id == booking.id))).one()
    return _out(booking)


@router.post("/{booking_id}/hold", response_model=VenueBookingOut)
def create_tentative_hold(
    booking_id: int,
    body: VenueHoldIn,
    db: Session = Depends(get_db),
    user: User = Depends(_venue_staff),
) -> VenueBookingOut:
    """Place a temporary hold on a pending request for follow-up."""
    booking = db.get(VenueBooking, booking_id, with_for_update=True)
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking request not found")
    if booking.status != BookingStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only a pending venue booking can be placed on tentative hold.",
        )
    now = datetime.now(timezone.utc)
    # TODO(confirm): The hold duration defaults to 24 hours until the business confirms it.
    expires_at = body.expires_at or (now + timedelta(hours=24))
    comparable_expiry = expires_at.replace(tzinfo=timezone.utc) if expires_at.tzinfo is None else expires_at
    if comparable_expiry <= now:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A tentative hold expiry must be in the future.",
        )
    booking.status = BookingStatus.tentative_hold
    booking.expires_at = expires_at
    booking.reviewed_by = user.id
    booking.reviewed_at = now
    coordinator_id = booking.event.coordinator_id
    if coordinator_id is not None:
        notify(
            db,
            user_id=coordinator_id,
            type=NotificationType.venue_hold_expiring,
            message=(
                f"The tentative hold for {booking.venue.name} will expire "
                f"at {expires_at.isoformat()}."
            ),
            event_id=booking.event_id,
        )
    db.commit()
    booking = db.scalars(
        _with_relations(select(VenueBooking).where(VenueBooking.id == booking.id))
    ).unique().one()
    return _out(booking)


@router.post(
    "/events/{event_id}",
    response_model=list[VenueBookingOut],
    status_code=status.HTTP_201_CREATED,
)
def submit_venue_booking(
    event_id: int,
    body: VenueBookingCreate,
    db: Session = Depends(get_db),
    user: User = Depends(_coordinator),
) -> list[VenueBookingOut]:
    """Ask for one or more venues for an event the caller coordinates.

    A separate booking is made for each venue, all under the same event, each
    waiting for Venue Staff. The first request on an approved event moves it
    to Planning Event, and that is logged. All or nothing: if any venue is
    refused, none are created.
    404 for an event that is not assigned to the caller, the same as
    GET /events/assigned/{id}: "not yours" and "does not exist" are
    indistinguishable. The event row is locked so two overlapping submits
    (a double-clicked button) cannot both pass the duplicate check.
    """
    if not body.venues:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Select a venue before submitting the booking request.",
        )
    venue_ids = [v.venue_id for v in body.venues]
    if len(set(venue_ids)) != len(venue_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Each venue can only be selected once.",
        )

    event = db.get(Event, event_id, with_for_update=True)
    if event is None or event.coordinator_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    if event.status not in BOOKABLE_EVENT_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A venue can only be requested while the event is 'Event Approved' or "
                f"'Planning Event'; it is '{event.status}'."
            ),
        )
    if event.proposed_start is None or event.proposed_end is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The event has no date and time to book the venue for.",
        )

    expire_tentative_holds(db)
    venues = {v.id: v for v in db.scalars(select(Venue).where(Venue.id.in_(venue_ids)))}
    for venue_id in venue_ids:
        venue = venues.get(venue_id)
        if venue is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="That venue does not exist."
            )
        if not venue.is_active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{venue.name} is inactive and cannot be booked.",
            )

    already_requested = db.scalar(
        select(VenueBooking.venue_id).where(
            VenueBooking.event_id == event.id,
            VenueBooking.venue_id.in_(venue_ids),
            VenueBooking.status.in_(LIVE_BOOKING_STATUSES),
        )
    )
    if already_requested is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"This event already has a live booking request for "
                f"{venues[already_requested].name}."
            ),
        )

    created = []
    for request in body.venues:
        booking = VenueBooking(
            event_id=event.id,
            venue_id=request.venue_id,
            requested_by=user.id,
            start_time=event.proposed_start,
            end_time=event.proposed_end,
            status=BookingStatus.pending,
            room_layout_preference=request.room_layout_preference,
            accessibility_needs=request.accessibility_needs,
            facilities_needs=request.facilities_needs,
        )
        db.add(booking)
        created.append(booking)

    if event.status == EventStatus.event_approved:
        previous = event.status
        event.status = EventStatus.planning_event
        db.add(
            EventStatusHistory(
                event_id=event.id,
                changed_by=user.id,
                from_status=previous,
                to_status=event.status,
                note="First venue booking requested by the Event Coordinator.",
            )
        )
    db.flush()
    ids = [b.id for b in created]
    db.commit()
    rows = db.scalars(
        _with_relations(select(VenueBooking).where(VenueBooking.id.in_(ids)).order_by(VenueBooking.id))
    ).unique()
    return [_out(b) for b in rows]


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
    expire_tentative_holds(db)
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
    expire_tentative_holds(db)
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
    expire_tentative_holds(db)
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
