from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.datetimes import as_utc
from app.core.db import get_db
from app.core.deps import require_role
from app.core.roles import Role
from app.domain.venue_booking_changes import (
    LIVE_BOOKING_STATUSES,
    VenueBookingChangeService,
)
from app.domain.venue_occupancy import occupied_window, overlap_of
from app.models.enums import BookingStatus, EventStatus, NotificationType
from app.models.events import Event, EventStatusHistory
from app.models.user import User
from app.models.venues import Venue, VenueBooking, VenueUnavailability
from app.services import booking_conflict_flags as flags
from app.schemas.venue_booking import (
    BookingConflict,
    ConflictCancel,
    ConflictKeep,
    VenueBookingCancel,
    VenueBookingCancelAll,
    VenueBookingChange,
    VenueBookingCreate,
    VenueBookingOut,
    VenueBookingRejection,
    VenueHoldIn,
)
from app.routers.venues import expire_tentative_holds
from app.services.notifications import notify
from app.services.venue_holds import active_hold_filter

router = APIRouter(prefix="/venue-bookings", tags=["venue-bookings"])

# Venues are requested while the event is being planned: once approved, and
# for as long as it stays in planning. After it goes to the Safety Officer
# the arrangement is judged as it stands.
BOOKABLE_EVENT_STATUSES = (EventStatus.event_approved, EventStatus.planning_event)

_coordinator = require_role(Role.COORDINATOR)
_venue_staff = require_role(Role.VENUE_STAFF)


def get_change_service(db: Session = Depends(get_db)) -> VenueBookingChangeService:
    return VenueBookingChangeService(db)


def _conflict_between(
    mine: VenueBooking, other: VenueBooking, venue: Venue
) -> BookingConflict | None:
    """What `other` (approved or held) clashes with in `mine`, or None.

    Both occupied windows use the venue's current setup/turnaround and are
    compared with strict overlap, so a request starting exactly when the
    other's occupied period ends is not a conflict.
    """
    setup, turnaround = venue.setup_minutes, venue.turnaround_minutes
    theirs = occupied_window(other.start_time, other.end_time, setup, turnaround)
    shared = overlap_of(occupied_window(mine.start_time, mine.end_time, setup, turnaround), theirs)
    if shared is None:
        return None
    return BookingConflict(
        booking_id=other.id,
        event_id=other.event_id,
        event_name=other.event.name or "Untitled event",
        event_start=other.start_time,
        event_end=other.end_time,
        occupied_start=theirs.start,
        occupied_end=theirs.end,
        overlap_start=shared.start,
        overlap_end=shared.end,
    )


def _closure_conflict(booking: VenueBooking, closure: VenueUnavailability) -> BookingConflict:
    start, end = as_utc(closure.start_time), as_utc(closure.end_time)
    shared = overlap_of(
        occupied_window(booking.start_time, booking.end_time, 0, 0), occupied_window(start, end, 0, 0)
    )
    assert shared is not None
    reason = closure.reason_category + (f": {closure.reason}" if closure.reason else "")
    return BookingConflict(
        kind="unavailability",
        event_start=start,
        event_end=end,
        occupied_start=start,
        occupied_end=end,
        overlap_start=shared.start,
        overlap_end=shared.end,
        reason=reason,
    )


def _conflicts(bookings: list[VenueBooking], db: Session, viewer: User) -> dict[int, list[BookingConflict]]:
    """Conflicts per booking id, for Venue Staff viewing pending requests and
    flagged approved bookings only.

    Anyone else gets nothing, so no other event's name reaches a Coordinator
    or Organiser. The approved bookings are loaded once for all the venues
    involved, not once per booking.
    """
    if viewer.role != Role.VENUE_STAFF.value:
        return {}
    pending = [
        b
        for b in bookings
        if b.status in (BookingStatus.pending, BookingStatus.tentative_hold)
        or (b.status == BookingStatus.approved and b.conflict_flagged_at is not None)
    ]
    if not pending:
        return {}
    approved: dict[int, list[VenueBooking]] = {}
    for other in db.scalars(
        select(VenueBooking)
        .where(
            VenueBooking.venue_id.in_({b.venue_id for b in pending}),
            # An active tentative hold occupies its window too (SCRUM-97).
            VenueBooking.status.in_((BookingStatus.approved, BookingStatus.tentative_hold)),
            active_hold_filter(datetime.now(timezone.utc)),
        )
        .options(joinedload(VenueBooking.event))
        .order_by(VenueBooking.start_time, VenueBooking.id)
    ).unique():
        approved.setdefault(other.venue_id, []).append(other)
    # Periods Venue Staff marked the venue unavailable (SCRUM-93): shown the
    # same way, with the reason, so the request is flagged during review.
    closures: dict[int, list[VenueUnavailability]] = {}
    for closure in db.scalars(
        select(VenueUnavailability)
        .where(VenueUnavailability.venue_id.in_({b.venue_id for b in pending}))
        .order_by(VenueUnavailability.start_time, VenueUnavailability.id)
    ):
        closures.setdefault(closure.venue_id, []).append(closure)
    found: dict[int, list[BookingConflict]] = {}
    for booking in pending:
        hits = [
            c
            for other in approved.get(booking.venue_id, [])
            if other.id != booking.id
            and (c := _conflict_between(booking, other, booking.venue)) is not None
        ]
        hits += [
            _closure_conflict(booking, closure)
            for closure in closures.get(booking.venue_id, [])
            if flags.closure_overlaps(booking, closure)
        ]
        found[booking.id] = hits
    return found


def _outs(bookings, db: Session, viewer: User) -> list[VenueBookingOut]:
    bookings = list(bookings)
    conflicts = _conflicts(bookings, db, viewer)
    return [_out(b, conflicts.get(b.id, [])) for b in bookings]


def _out(booking: VenueBooking, conflicts: list[BookingConflict] | None = None) -> VenueBookingOut:
    event = booking.event
    setup = booking.venue.setup_minutes or 0
    turnaround = booking.venue.turnaround_minutes or 0
    occupied = occupied_window(booking.start_time, booking.end_time, setup, turnaround)
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
        conflict_flagged=booking.conflict_flagged_at is not None,
        setup_minutes=setup,
        turnaround_minutes=turnaround,
        occupied_start=occupied.start,
        occupied_end=occupied.end,
        conflicts=conflicts or [],
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
    # Sweep expired holds first: the sweep commits, which would drop a lock.
    expire_tentative_holds(db)
    # Venue first, then the booking: the same order as the setup/turnaround
    # re-check and keep-conflict, so none of them can deadlock on each other.
    venue_id = db.scalar(select(VenueBooking.venue_id).where(VenueBooking.id == booking_id))
    if venue_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking request not found")
    db.get(Venue, venue_id, with_for_update=True)
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
    """Record the outcome with who decided and when, and return it.

    A flagged conflict (SCRUM-92) is cleared by either decision: re-approval
    only passes when nothing overlaps, and a rejected booking holds nothing.
    A rejection frees the venue, so other bookings that only clashed with this
    one are un-flagged too.
    """
    was_approved = booking.status == BookingStatus.approved
    flags.release(
        db, booking, staff, f"Venue booking '{booking.venue.name}' conflict cleared: booking {decision}."
    )
    booking.status = decision
    if decision != BookingStatus.tentative_hold:
        booking.expires_at = None
    booking.safety_recheck_reason = None
    booking.reviewed_by = staff.id
    booking.reviewed_at = datetime.now(timezone.utc)
    if was_approved and decision != BookingStatus.approved:
        db.flush()
        flags.recheck_venue(db, booking.venue, staff, may_flag=False)
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
    # Sweep first (it commits), then venue before booking: the same lock order
    # as every other venue-staff action, so none can deadlock on another.
    expire_tentative_holds(db)
    venue_id = db.scalar(select(VenueBooking.venue_id).where(VenueBooking.id == booking_id))
    if venue_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking request not found")
    db.get(Venue, venue_id, with_for_update=True)
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
    return _outs(rows, db, user)


def _reloaded(db: Session, ids: list[int], viewer: User) -> list[VenueBookingOut]:
    """The bookings as they are now, with their relations, in id order."""
    rows = db.scalars(
        _with_relations(select(VenueBooking).where(VenueBooking.id.in_(ids)).order_by(VenueBooking.id))
    ).unique()
    return _outs(rows, db, viewer)


# The Coordinator changing or cancelling their event's bookings (SCRUM-96).
# Thin on purpose: every rule lives in app/domain/venue_booking_changes.py. A
# sweep of expired holds comes first -- it commits, so it cannot come after
# the locks the service takes -- and the route commits what the service did.


@router.patch("/{booking_id}", response_model=VenueBookingOut)
def change_venue_booking(
    booking_id: int,
    body: VenueBookingChange,
    db: Session = Depends(get_db),
    service: VenueBookingChangeService = Depends(get_change_service),
    user: User = Depends(_coordinator),
) -> VenueBookingOut:
    """Change one booking's venue, or what is needed of it. Only that booking
    returns to Pending for Venue Staff; the others are untouched."""
    expire_tentative_holds(db)
    booking = service.change(booking_id, user, **body.model_dump(exclude_unset=True))
    db.commit()
    return _reloaded(db, [booking.id], user)[0]


@router.post("/{booking_id}/cancel", response_model=VenueBookingOut)
def cancel_venue_booking(
    booking_id: int,
    body: VenueBookingCancel,
    db: Session = Depends(get_db),
    service: VenueBookingChangeService = Depends(get_change_service),
    user: User = Depends(_coordinator),
) -> VenueBookingOut:
    """Cancel one booking. The others, and the event, are untouched."""
    expire_tentative_holds(db)
    booking = service.cancel(booking_id, user, body.reason)
    db.commit()
    return _reloaded(db, [booking.id], user)[0]


@router.get("/events/{event_id}/cancellable", response_model=list[VenueBookingOut])
def list_cancellable_venue_bookings(
    event_id: int,
    db: Session = Depends(get_db),
    service: VenueBookingChangeService = Depends(get_change_service),
    user: User = Depends(_coordinator),
) -> list[VenueBookingOut]:
    """The bookings "cancel all" would cancel: the list shown before the
    Coordinator confirms."""
    expire_tentative_holds(db)
    bookings = service.live_bookings(event_id, user)
    return _reloaded(db, [b.id for b in bookings], user)


@router.post("/events/{event_id}/cancel-all", response_model=list[VenueBookingOut])
def cancel_all_venue_bookings(
    event_id: int,
    body: VenueBookingCancelAll,
    db: Session = Depends(get_db),
    service: VenueBookingChangeService = Depends(get_change_service),
    user: User = Depends(_coordinator),
) -> list[VenueBookingOut]:
    """Cancel the listed bookings -- all of the event's live ones, or nothing:
    409 if the live bookings are no longer exactly those that were shown."""
    expire_tentative_holds(db)
    cancelled = service.cancel_all(event_id, user, body.booking_ids, body.reason)
    db.commit()
    return _reloaded(db, [b.id for b in cancelled], user)


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
    return _outs(bookings, db, user)


@router.get("/queue", response_model=list[VenueBookingOut])
def venue_booking_queue(
    db: Session = Depends(get_db),
    user: User = Depends(_venue_staff),
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
    return _outs(bookings, db, user)


@router.get("/flagged", response_model=list[VenueBookingOut])
def flagged_venue_bookings(
    db: Session = Depends(get_db),
    user: User = Depends(_venue_staff),
) -> list[VenueBookingOut]:
    """Approved bookings flagged as conflicting after a venue's setup or
    turnaround changed, soonest first, each with the bookings it overlaps
    and the overlapping period."""
    expire_tentative_holds(db)
    bookings = db.scalars(
        _with_relations(
            select(VenueBooking)
            .where(VenueBooking.conflict_flagged_at.is_not(None))
            .order_by(VenueBooking.start_time, VenueBooking.id)
        )
    ).unique()
    return _outs(bookings, db, user)


@router.get("/{booking_id}", response_model=VenueBookingOut)
def get_venue_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_venue_staff),
) -> VenueBookingOut:
    expire_tentative_holds(db)
    booking = db.scalars(
        _with_relations(select(VenueBooking).where(VenueBooking.id == booking_id))
    ).unique().first()
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking request not found")
    return _outs([booking], db, user)[0]


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
    venue = db.get(Venue, booking.venue_id, with_for_update=True)

    # Same overlap rule as the venue search: each period starts before the
    # other ends, so touching edges do not clash. Both periods include the
    # venue's setup and turnaround, so a booking that leaves too little time
    # to reset and set up again is a clash (0 when none is recorded). The
    # setup/turnaround saved on the venue now applies to every booking there.
    others = db.scalars(
        select(VenueBooking)
        .where(
            VenueBooking.venue_id == booking.venue_id,
            VenueBooking.id != booking.id,
            VenueBooking.status == BookingStatus.approved,
        )
        .options(joinedload(VenueBooking.event))
        .order_by(VenueBooking.start_time, VenueBooking.id)
    ).unique()
    hits = [c for o in others if (c := _conflict_between(booking, o, venue)) is not None]
    if hits:
        first = hits[0]
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "The venue is already booked for another event at that time: "
                f"{first.event_name}, {first.overlap_start:%Y-%m-%d %H:%M} to "
                f"{first.overlap_end:%Y-%m-%d %H:%M} UTC."
            ),
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


@router.post("/{booking_id}/keep-conflict", response_model=VenueBookingOut)
def keep_conflicting_booking(
    booking_id: int,
    body: ConflictKeep,
    db: Session = Depends(get_db),
    user: User = Depends(_venue_staff),
) -> VenueBookingOut:
    """Venue Staff accept a flagged overlap and keep the booking as it is.

    The reason is required. The flag is cleared and the resolution (actor,
    time, reason) goes in the Activity Log. 409 when the booking is not
    flagged, which also makes a repeated call a no-op. The venue is locked
    first, as in the setup/turnaround save, so the two cannot interleave.
    """
    expire_tentative_holds(db)  # commits: before the locks, never after
    booking = db.get(VenueBooking, booking_id)
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking request not found")
    db.get(Venue, booking.venue_id, with_for_update=True)
    db.refresh(booking, with_for_update=True)
    if booking.conflict_flagged_at is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This booking is not flagged as conflicting."
        )
    flags.release(
        db,
        booking,
        user,
        f"Venue booking '{booking.venue.name}' conflict kept by Venue Staff. Reason: {body.reason}",
    )
    db.commit()
    booking = db.scalars(_with_relations(select(VenueBooking).where(VenueBooking.id == booking_id))).unique().one()
    return _outs([booking], db, user)[0]


@router.post("/{booking_id}/cancel-flagged", response_model=VenueBookingOut)
def cancel_flagged_booking(
    booking_id: int,
    body: ConflictCancel,
    db: Session = Depends(get_db),
    user: User = Depends(_venue_staff),
) -> VenueBookingOut:
    """Venue Staff cancel a flagged booking so it no longer overlaps (SCRUM-92 AC6).

    Only a flagged booking can be cancelled here; 409 otherwise. The reason is
    required. The booking's flag is cleared, any other booking that only
    clashed with it is un-flagged, the resolution (actor, time, reason) goes
    in the Activity Log and the Event's Coordinator is told. The Event itself
    is not cancelled: the Coordinator still has to arrange a venue.
    """
    expire_tentative_holds(db)  # commits: before the locks, never after
    booking = db.get(VenueBooking, booking_id)
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking request not found")
    db.get(Venue, booking.venue_id, with_for_update=True)
    db.refresh(booking, with_for_update=True)
    if booking.conflict_flagged_at is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This booking is not flagged as conflicting."
        )
    event = booking.event
    venue_name = booking.venue.name
    booking.status = BookingStatus.cancelled
    flags.log_resolution(
        db, booking, user, f"Venue booking '{venue_name}' cancelled by Venue Staff to resolve a conflict. Reason: {body.reason}"
    )
    flags.booking_changed(db, booking, user)
    if event.coordinator_id is not None:
        flags.notify_cancelled(db, event, venue_name, body.reason)
    db.commit()
    booking = db.scalars(_with_relations(select(VenueBooking).where(VenueBooking.id == booking_id))).unique().one()
    return _outs([booking], db, user)[0]
