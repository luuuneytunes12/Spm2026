from collections.abc import Iterable
from datetime import datetime, timezone
import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.datetimes import as_utc
from app.core.db import get_db
from app.core.deps import require_role
from app.core.roles import Role
from app.models.enums import BookingStatus, NotificationType
from app.models.events import Event
from app.models.user import User
from app.models.venues import Venue, VenueBooking, VenueUnavailability
from app.services.notifications import notify
from app.schemas.venue import (
    CombinedVenueCapacityCheck,
    EventVenueSuitabilityItem,
    EventVenueSuitabilityOut,
    VenueAvailabilityItem,
    VenueAvailabilityOut,
    VenueDetail,
    VenueFilterOptions,
    VenueSummary,
    VenueSuitabilityCheck,
    VenueSuitabilityOut,
    VenueUnavailabilityCreate,
    VenueUnavailabilityOut,
)

router = APIRouter(prefix="/venues", tags=["venues"])

# Gated on role, not on VENUE_READ. The story is for INTERNAL users
# (Event Coordinators and Venue Staff), and VENUE_READ is also held by
# Attendees -- gating on the permission would show them internal venue
# details the story never meant them to see.
_internal = require_role(Role.COORDINATOR, Role.VENUE_STAFF)
_coordinator = require_role(Role.COORDINATOR)

# Which bookings take a venue out of a date search.
#
# Only a confirmed booking: W4 p4, Booking Conflict Detection -- "A
# confirmed booking should affect whether that venue is considered
# available." Rejected and cancelled bookings never will be confirmed, and a
# pending one is not yet.
#
# PROVISIONAL for pending. Venue Booking Request and Approval are separate
# stories, not built yet. If they decide a pending request should hold the
# venue, add BookingStatus.pending here and flip the matching test case in
# tests/test_venue_search.py.
_BLOCKING_BOOKING_STATUSES = (BookingStatus.approved, BookingStatus.tentative_hold)


def _reject(field: str, message: str) -> None:
    """A 422 in FastAPI's own shape, naming the query parameter at fault."""
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=[{"loc": ["query", field], "msg": message}],
    )


def _folded(values: Iterable[str] | None) -> set[str]:
    """Recorded values, compared ignoring case and surrounding spaces.

    Layouts, facilities and accessibility features are free text typed by
    Venue Staff, so "Projector" and "projector" must count as the same
    thing -- a Coordinator's filter should not trip over capitalisation.
    """
    return {v.strip().casefold() for v in values or [] if v and v.strip()}


def _has_all(recorded: Iterable[str] | None, wanted: Iterable[str]) -> bool:
    """True when the venue has EVERY wanted value, not just one.

    An event that needs a projector and video conferencing is not served by
    a room with only one of them.
    """
    return _folded(wanted) <= _folded(recorded)


def _distinct(values: Iterable[str]) -> list[str]:
    """Each value once, ignoring case, sorted -- keeping the first spelling.

    Since matching ignores case, offering "Projector" and "projector" as two
    choices would give two options that return identical results.
    """
    kept: dict[str, str] = {}
    for value in sorted((v.strip() for v in values if v and v.strip()), key=lambda v: (v.casefold(), v)):
        kept.setdefault(value.casefold(), value)
    return list(kept.values())


def _requirement_items(value: str | None) -> list[str]:
    """Read the existing free-text fields as comma/semicolon/newline lists."""
    return [item.strip() for item in re.split(r"[,;\n]", value or "") if item.strip()]


def _active_hold_filter(now: datetime):
    return or_(
        VenueBooking.status != BookingStatus.tentative_hold,
        and_(
            VenueBooking.expires_at.is_not(None),
            VenueBooking.expires_at > now,
        ),
    )


def expire_tentative_holds(db: Session, now: datetime | None = None) -> int:
    """Release expired holds and notify their Coordinators on the next API use."""
    current = now or datetime.now(timezone.utc)
    # TODO(confirm): Schedule this operation periodically so notifications
    # are delivered at expiry even when no venue page is being requested.
    holds = db.scalars(
        select(VenueBooking)
        .options(joinedload(VenueBooking.event))
        .where(
            VenueBooking.status == BookingStatus.tentative_hold,
            or_(
                VenueBooking.expires_at.is_(None),
                VenueBooking.expires_at <= current,
            ),
        )
    ).unique().all()
    for hold in holds:
        hold.status = BookingStatus.cancelled
        hold.decision_notes = "Tentative hold expired."
        coordinator_id = hold.event.coordinator_id
        if coordinator_id is not None:
            notify(
                db,
                user_id=coordinator_id,
                type=NotificationType.venue_hold_expired,
                message=(
                    f"The tentative hold for {hold.venue.name} on "
                    f"'{hold.event.name or 'your event'}' expired."
                ),
                event_id=hold.event_id,
            )
    if holds:
        db.commit()
    return len(holds)


def _suitability_checks(event: Event, venue: Venue) -> list[VenueSuitabilityCheck]:
    checks: list[VenueSuitabilityCheck] = []
    if event.expected_attendance is None:
        checks.append(
            VenueSuitabilityCheck(
                category="capacity",
                requirement="Expected attendance is not recorded",
                available=f"{venue.capacity} people",
                met=False,
                message="Cannot confirm capacity until the event attendance is recorded.",
            )
        )
    else:
        capacity_met = venue.capacity >= event.expected_attendance
        checks.append(
            VenueSuitabilityCheck(
                category="capacity",
                requirement=f"{event.expected_attendance} people",
                available=f"{venue.capacity} people",
                met=capacity_met,
                message=(
                    "Capacity is sufficient."
                    if capacity_met
                    else f"Insufficient capacity: {venue.capacity} available; "
                    f"{event.expected_attendance} required."
                ),
            )
        )

    layout = (event.room_layout_preference or "").strip()
    if layout:
        layout_met = layout.casefold() in _folded(venue.supported_layouts)
        checks.append(
            VenueSuitabilityCheck(
                category="layout",
                requirement=layout,
                available=", ".join(venue.supported_layouts or []) or "None recorded",
                met=layout_met,
                message=(
                    f"Layout '{layout}' is supported."
                    if layout_met
                    else f"Unsupported layout: '{layout}' is not offered by this venue."
                ),
            )
        )

    for requirement in _requirement_items(event.accessibility_needs):
        met = requirement.casefold() in _folded(venue.accessibility_features)
        checks.append(
            VenueSuitabilityCheck(
                category="accessibility",
                requirement=requirement,
                available=", ".join(venue.accessibility_features or []) or "None recorded",
                met=met,
                message=(
                    f"Accessibility feature '{requirement}' is available."
                    if met
                    else f"Missing accessibility feature: '{requirement}'."
                ),
            )
        )

    for requirement in _requirement_items(event.venue_requirements):
        met = requirement.casefold() in _folded(venue.facilities)
        checks.append(
            VenueSuitabilityCheck(
                category="facility",
                requirement=requirement,
                available=", ".join(venue.facilities or []) or "None recorded",
                met=met,
                message=(
                    f"Facility '{requirement}' is available."
                    if met
                    else f"Missing facility: '{requirement}'."
                ),
            )
        )
    return checks


# Declared before "/{venue_id}". That route takes an int, so "filter-options"
# would otherwise be captured as a venue id and fail as an invalid number.
@router.get("/filter-options", response_model=VenueFilterOptions)
def list_filter_options(
    db: Session = Depends(get_db),
    _: object = Depends(_internal),
) -> VenueFilterOptions:
    """The layouts, facilities and accessibility features recorded for any
    venue -- the choices the search filters offer.

    Inactive venues' values are included: inactive venues appear in results
    (flagged), so their values must be choosable too. The lists are never
    narrowed by an active search, so a filter can always be widened again.
    """
    venues = db.execute(select(Venue)).scalars().all()
    return VenueFilterOptions(
        layouts=_distinct(v for venue in venues for v in venue.supported_layouts or []),
        facilities=_distinct(v for venue in venues for v in venue.facilities or []),
        accessibility_features=_distinct(
            v for venue in venues for v in venue.accessibility_features or []
        ),
    )


@router.get("", response_model=list[VenueSummary])
def list_venues(
    q: str | None = Query(None, description="Matched against name and location."),
    min_capacity: int | None = Query(
        None, ge=1, description="Expected attendance: smaller venues are excluded."
    ),
    layout: str | None = Query(None, description="One layout the venue must support."),
    facilities: list[str] = Query(
        default=[], description="Repeat for each; the venue must have every one."
    ),
    accessibility: list[str] = Query(
        default=[], description="Repeat for each; the venue must have every one."
    ),
    start: datetime | None = Query(None, description="Start of the window, ISO 8601."),
    end: datetime | None = Query(None, description="End of the window, ISO 8601."),
    db: Session = Depends(get_db),
    _: object = Depends(_internal),
) -> list[VenueSummary]:
    """Every venue, alphabetically -- narrowed by whatever criteria are given.

    With no parameters this is the same list as before search existed. Every
    criterion given must hold (AND).

    Inactive venues are still listed (flagged by `is_active`): Venue Staff
    need to see them, and a Coordinator is better told "inactive" than left
    wondering where a venue went.
    """
    # Half a time window, or one that ends before it starts, is a mistake,
    # not a search. Rejected rather than ignored: ignoring it would show
    # venues as free for a period nobody actually asked about.
    if (start is None) != (end is None):
        _reject("end" if end is None else "start", "Give both a start and an end.")
    if start is not None and end is not None and as_utc(end) <= as_utc(start):
        _reject("end", "The end must be after the start.")

    stmt = select(Venue)

    if q and q.strip():
        term = q.strip()
        # autoescape so a % or _ typed by the user is matched literally
        # instead of acting as a wildcard.
        stmt = stmt.where(
            or_(
                Venue.name.icontains(term, autoescape=True),
                Venue.location.icontains(term, autoescape=True),
            )
        )

    if min_capacity is not None:
        # A venue that holds exactly the expected attendance fits it.
        stmt = stmt.where(Venue.capacity >= min_capacity)

    if start is not None and end is not None:
        window_start, window_end = as_utc(start), as_utc(end)
        now = datetime.now(timezone.utc)
        # Two periods overlap when each starts before the other ends. Strict
        # comparisons, so back-to-back is not an overlap: a session ending at
        # 09:00 leaves the room free for one starting at 09:00.
        booked = exists().where(
            VenueBooking.venue_id == Venue.id,
            VenueBooking.status.in_(_BLOCKING_BOOKING_STATUSES),
            _active_hold_filter(now),
            VenueBooking.start_time < window_end,
            VenueBooking.end_time > window_start,
        )
        # A recorded closure (maintenance, renovation, ...) has no status:
        # once recorded, it blocks.
        blocked = exists().where(
            VenueUnavailability.venue_id == Venue.id,
            VenueUnavailability.start_time < window_end,
            VenueUnavailability.end_time > window_start,
        )
        stmt = stmt.where(~booked, ~blocked)

    venues = db.execute(stmt.order_by(Venue.name, Venue.id)).scalars().all()

    # Layout, facilities and accessibility are matched here rather than in
    # SQL. They are Postgres arrays in production but JSON in the SQLite the
    # tests run on, and case-insensitive matching inside an array has no
    # expression that works the same on both. Keyword, capacity and the date
    # window -- the parts that shrink the list most -- stay in SQL. Fine at
    # the hundreds of venues ConnectSphere has; revisit if that becomes many
    # thousands.
    if layout and layout.strip():
        venues = [v for v in venues if _has_all(v.supported_layouts, [layout])]
    if _folded(facilities):
        venues = [v for v in venues if _has_all(v.facilities, facilities)]
    if _folded(accessibility):
        venues = [v for v in venues if _has_all(v.accessibility_features, accessibility)]

    return [VenueSummary.model_validate(v) for v in venues]


@router.get("/{venue_id}", response_model=VenueDetail)
def get_venue(
    venue_id: int,
    db: Session = Depends(get_db),
    _: object = Depends(_internal),
) -> VenueDetail:
    venue = db.get(Venue, venue_id)
    if venue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venue not found")
    return VenueDetail.model_validate(venue)


@router.get("/{venue_id}/availability", response_model=VenueAvailabilityOut)
def get_venue_availability(
    venue_id: int,
    start: datetime = Query(..., description="Start of the calendar window, ISO 8601."),
    end: datetime = Query(..., description="End of the calendar window, ISO 8601."),
    db: Session = Depends(get_db),
    _: object = Depends(_internal),
) -> VenueAvailabilityOut:
    """Return confirmed bookings, active tentative holds and closures."""
    venue = db.get(Venue, venue_id)
    if venue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venue not found")
    if as_utc(end) <= as_utc(start):
        _reject("end", "The end must be after the start.")

    expire_tentative_holds(db)
    window_start, window_end = as_utc(start), as_utc(end)
    bookings = db.scalars(
        select(VenueBooking)
        .options(joinedload(VenueBooking.event))
        .where(
            VenueBooking.venue_id == venue_id,
            VenueBooking.status.in_(_BLOCKING_BOOKING_STATUSES),
            _active_hold_filter(datetime.now(timezone.utc)),
            VenueBooking.start_time < window_end,
            VenueBooking.end_time > window_start,
        )
    ).unique().all()
    closures = db.scalars(
        select(VenueUnavailability).where(
            VenueUnavailability.venue_id == venue_id,
            VenueUnavailability.start_time < window_end,
            VenueUnavailability.end_time > window_start,
        )
    ).all()

    items = [
        VenueAvailabilityItem(
            id=booking.id,
            kind=(
                "confirmed_booking"
                if booking.status == BookingStatus.approved
                else "tentative_hold"
            ),
            start_time=booking.start_time,
            end_time=booking.end_time,
            event_id=booking.event_id,
            event_name=booking.event.name,
            expires_at=booking.expires_at,
        )
        for booking in bookings
    ]
    for item in items:
        item.conflicts_with_unavailability = any(
            closure.start_time < item.end_time and closure.end_time > item.start_time
            for closure in closures
        )
    items.extend(
        VenueAvailabilityItem(
            id=closure.id,
            kind="unavailability",
            start_time=closure.start_time,
            end_time=closure.end_time,
            reason=closure.reason,
        )
        for closure in closures
    )
    items.sort(key=lambda item: (as_utc(item.start_time), item.kind, item.id))
    return VenueAvailabilityOut(venue_id=venue_id, start=start, end=end, items=items)


@router.post(
    "/{venue_id}/unavailability",
    response_model=VenueUnavailabilityOut,
    status_code=status.HTTP_201_CREATED,
)
def record_venue_unavailability(
    venue_id: int,
    body: VenueUnavailabilityCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.VENUE_STAFF)),
) -> VenueUnavailabilityOut:
    """Record a closure without cancelling bookings; notify affected Coordinators."""
    venue = db.get(Venue, venue_id)
    if venue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venue not found")
    if as_utc(body.end_time) <= as_utc(body.start_time):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The end must be after the start.",
        )

    now = datetime.now(timezone.utc)
    expire_tentative_holds(db, now)
    closure = VenueUnavailability(
        venue_id=venue.id,
        start_time=body.start_time,
        end_time=body.end_time,
        reason=body.reason,
        created_by=user.id,
    )
    db.add(closure)
    db.flush()
    affected = db.scalars(
        select(VenueBooking)
        .options(joinedload(VenueBooking.event))
        .where(
            VenueBooking.venue_id == venue.id,
            VenueBooking.status.in_(
                (BookingStatus.pending, BookingStatus.tentative_hold, BookingStatus.approved)
            ),
            _active_hold_filter(now),
            VenueBooking.start_time < body.end_time,
            VenueBooking.end_time > body.start_time,
        )
        .order_by(VenueBooking.id)
    ).unique().all()
    notified: set[int] = set()
    event_ids = sorted({booking.event_id for booking in affected})
    for booking in affected:
        coordinator_id = booking.event.coordinator_id
        if coordinator_id is not None and coordinator_id not in notified:
            notify(
                db,
                user_id=coordinator_id,
                type=NotificationType.venue_unavailability_recorded,
                message=(
                    f"{venue.name} is unavailable during your event "
                    f"'{booking.event.name or 'event'}': {body.reason}. "
                    "The existing event and booking have not been cancelled."
                ),
                event_id=booking.event_id,
            )
            notified.add(coordinator_id)
    db.commit()
    db.refresh(closure)
    return VenueUnavailabilityOut(
        id=closure.id,
        venue_id=closure.venue_id,
        start_time=closure.start_time,
        end_time=closure.end_time,
        reason=closure.reason or body.reason,
        affected_booking_ids=[booking.id for booking in affected],
        affected_event_ids=event_ids,
    )


@router.get(
    "/{venue_id}/suitability/{event_id}",
    response_model=VenueSuitabilityOut,
)
def check_venue_suitability(
    venue_id: int,
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_coordinator),
) -> VenueSuitabilityOut:
    """Compare one of the caller's assigned events against a venue."""
    venue = db.get(Venue, venue_id)
    if venue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venue not found")
    event = db.get(Event, event_id)
    if event is None or event.coordinator_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    checks = _suitability_checks(event, venue)
    return VenueSuitabilityOut(
        venue_id=venue.id,
        event_id=event.id,
        event_name=event.name,
        suitable=all(check.met for check in checks),
        checks=checks,
    )


@router.get("/events/{event_id}/suitability", response_model=EventVenueSuitabilityOut)
def check_event_venue_suitability(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_coordinator),
) -> EventVenueSuitabilityOut:
    """Check each active venue on an assigned event and its combined capacity."""
    event = db.get(Event, event_id)
    if event is None or event.coordinator_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    now = datetime.now(timezone.utc)
    expire_tentative_holds(db, now)
    bookings = db.scalars(
        select(VenueBooking)
        .options(joinedload(VenueBooking.venue))
        .where(
            VenueBooking.event_id == event.id,
            VenueBooking.status.in_(_BLOCKING_BOOKING_STATUSES),
            _active_hold_filter(now),
        )
        .order_by(VenueBooking.id)
    ).unique().all()
    venue_results = [
        EventVenueSuitabilityItem(
            booking_id=booking.id,
            venue_id=booking.venue.id,
            venue_name=booking.venue.name,
            suitable=all(check.met for check in _suitability_checks(event, booking.venue)),
            checks=_suitability_checks(event, booking.venue),
        )
        for booking in bookings
    ]
    available_capacity = sum({booking.venue.id: booking.venue.capacity for booking in bookings}.values())
    if event.expected_attendance is None:
        combined = CombinedVenueCapacityCheck(
            required_capacity=None,
            available_capacity=available_capacity,
            met=False,
            message="Cannot confirm combined capacity until expected attendance is recorded.",
        )
    else:
        capacity_met = available_capacity > event.expected_attendance
        combined = CombinedVenueCapacityCheck(
            required_capacity=event.expected_attendance,
            available_capacity=available_capacity,
            met=capacity_met,
            message=(
                f"Combined capacity is {available_capacity}; it must exceed "
                f"{event.expected_attendance} attendees."
            ),
        )
    return EventVenueSuitabilityOut(
        event_id=event.id,
        event_name=event.name,
        suitable=bool(venue_results) and all(result.suitable for result in venue_results) and combined.met,
        venues=venue_results,
        combined_capacity=combined,
    )
