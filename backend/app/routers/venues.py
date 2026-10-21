from collections.abc import Iterable
from datetime import datetime, timezone
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import ProgrammingError, SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.core.datetimes import as_utc
from app.core.db import get_db
from app.core.deps import require_role
from app.core.roles import Role
from app.domain.venue_occupancy import occupied_window
from app.models.enums import BookingStatus
from app.models.events import Event
from app.models.user import User
from app.models.venues import Venue, VenueBooking, VenueUnavailability
from app.services.booking_conflict_flags import closure_overlaps, effective_buffers, recheck_venue
from app.services.venue_holds import active_hold_filter as _active_hold_filter
from app.services.venue_holds import expire_tentative_holds
from app.services.unavailability_notices import PendingRequestNotices
from app.schemas.venue import (
    AffectedBooking,
    BusyPeriod,
    CombinedVenueCapacityCheck,
    EventVenueSuitabilityItem,
    EventVenueSuitabilityOut,
    RecheckSummary,
    SetupTurnaroundUpdate,
    UnavailabilityIn,
    UnavailabilityOut,
    VenueAvailabilityItem,
    VenueAvailabilityOut,
    VenueDetail,
    VenueFilterOptions,
    VenueSuitabilityCheck,
    VenueSuitabilityOut,
    VenueSummary,
)

router = APIRouter(prefix="/venues", tags=["venues"])
logger = logging.getLogger(__name__)

# Gated on role, not on VENUE_READ. The story is for INTERNAL users
# (Event Coordinators and Venue Staff), and VENUE_READ is also held by
# Attendees -- gating on the permission would show them internal venue
# details the story never meant them to see.
_internal = require_role(Role.COORDINATOR, Role.VENUE_STAFF)
_venue_staff = require_role(Role.VENUE_STAFF)
_coordinator = require_role(Role.COORDINATOR)

# Which bookings take a venue out of a date search.
#
# A confirmed booking (W4 p4, Booking Conflict Detection) and a tentative hold
# that has not expired (SCRUM-97: "the held window is treated as occupied").
# Rejected, cancelled and expired ones never are; a pending one is not yet.
# Always pair this with _active_hold_filter(now): a hold past its expiry but
# not yet swept must not block.
_BLOCKING_BOOKING_STATUSES = (BookingStatus.approved, BookingStatus.tentative_hold)
_SUITABILITY_BOOKING_STATUSES = (
    BookingStatus.pending,
    BookingStatus.approved,
    BookingStatus.tentative_hold,
)


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


def _checks_for_requirements(
    venue: Venue,
    expected_attendance: int | None,
    room_layout_preference: str | None,
    accessibility_needs: str | None,
    facilities_needs: str | None,
) -> list[VenueSuitabilityCheck]:
    checks: list[VenueSuitabilityCheck] = []
    if expected_attendance is None:
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
        capacity_met = venue.capacity >= expected_attendance
        checks.append(
            VenueSuitabilityCheck(
                category="capacity",
                requirement=f"{expected_attendance} people",
                available=f"{venue.capacity} people",
                met=capacity_met,
                message=(
                    "Capacity is sufficient."
                    if capacity_met
                    else f"Insufficient capacity: Capacity {venue.capacity} "
                    f"< attendance {expected_attendance}."
                ),
            )
        )

    layout = (room_layout_preference or "").strip()
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

    for requirement in _requirement_items(accessibility_needs):
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

    for requirement in _requirement_items(facilities_needs):
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


def _suitability_checks(event: Event, venue: Venue) -> list[VenueSuitabilityCheck]:
    return _checks_for_requirements(
        venue,
        event.expected_attendance,
        event.room_layout_preference,
        event.accessibility_needs,
        event.venue_requirements,
    )


def _booking_suitability_checks(
    event: Event, booking: VenueBooking
) -> list[VenueSuitabilityCheck]:
    return _checks_for_requirements(
        booking.venue,
        booking.expected_attendance
        if booking.expected_attendance is not None
        else event.expected_attendance,
        booking.room_layout_preference or event.room_layout_preference,
        booking.accessibility_needs or event.accessibility_needs,
        booking.facilities_needs or event.venue_requirements,
    )


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
    start: datetime | None = Query(
        None,
        description="Start of the window, ISO 8601. Venues with an approved booking, an "
        "unexpired tentative hold or a closure clashing with it -- each venue's setup and "
        "turnaround time included -- are excluded.",
    ),
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

    expire_tentative_holds(db)
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

    venues = list(db.execute(stmt.order_by(Venue.name, Venue.id)).scalars().all())

    if start is not None and end is not None:
        venues = _free_of_closures(db, venues, as_utc(start), as_utc(end))
        venues = _free_of_bookings(db, venues, as_utc(start), as_utc(end))

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


def _free_of_closures(db: Session, venues: list[Venue], start: datetime, end: datetime) -> list[Venue]:
    """Drop venues with a recorded closure (maintenance, renovation, ...)
    that clashes with the window.

    A closure has no status: once recorded, it blocks. It is a raw period --
    no setup or turnaround of its own -- but the event being searched for is
    widened by the venue's setup and turnaround (Filter Venues by Date and
    Time, AC1): a closed room cannot be set up before the event or reset
    after it either. Touching edges are still free.
    """
    if not venues:
        return venues
    by_venue: dict[int, list[VenueUnavailability]] = {}
    for closure in db.scalars(
        select(VenueUnavailability).where(VenueUnavailability.venue_id.in_([v.id for v in venues]))
    ):
        by_venue.setdefault(closure.venue_id, []).append(closure)

    free = []
    for venue in venues:
        wanted = occupied_window(start, end, venue.setup_minutes, venue.turnaround_minutes)
        if not any(
            wanted.overlaps(occupied_window(c.start_time, c.end_time, 0, 0))
            for c in by_venue.get(venue.id, [])
        ):
            free.append(venue)
    return free


def _free_of_bookings(db: Session, venues: list[Venue], start: datetime, end: datetime) -> list[Venue]:
    """Drop venues whose confirmed bookings clash with the window.

    Done here rather than in SQL because each venue has its own setup and
    turnaround: the searched window and every booking are widened by that
    venue's buffers (0 when not set), then compared with strict overlap, so
    touching edges are still free.
    """
    if not venues:
        return venues
    by_venue: dict[int, list[VenueBooking]] = {}
    for booking in db.scalars(
        select(VenueBooking).where(
            VenueBooking.venue_id.in_([v.id for v in venues]),
            VenueBooking.status.in_(_BLOCKING_BOOKING_STATUSES),
            _active_hold_filter(datetime.now(timezone.utc)),
        )
    ):
        by_venue.setdefault(booking.venue_id, []).append(booking)

    free = []
    for venue in venues:
        wanted = occupied_window(start, end, venue.setup_minutes, venue.turnaround_minutes)
        if not any(
            wanted.overlaps(occupied_window(b.start_time, b.end_time, venue.setup_minutes, venue.turnaround_minutes))
            for b in by_venue.get(venue.id, [])
        ):
            free.append(venue)
    return free


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
def venue_availability(
    venue_id: int,
    start: datetime | None = Query(None, description="Start of the range, ISO 8601."),
    end: datetime | None = Query(None, description="End of the range, ISO 8601."),
    db: Session = Depends(get_db),
    user: User = Depends(_internal),
) -> VenueAvailabilityOut:
    """When the venue is NOT available within a range.

    `busy` and `items` describe the same periods for two readers:
      * `busy`: the OCCUPIED period (event plus setup/turnaround) of every
        approved booking and active tentative hold, and every closure;
      * `items`: the same, as calendar entries carrying the event window, the
        occupied window, the hold's expiry and a closure's reason.
    Anything not listed is free. Pending, rejected, cancelled and expired
    bookings never appear.

    Only Venue Staff are told which event holds the venue; a Coordinator
    sees that it is taken, not by whom.
    """
    if start is None or end is None:
        _reject("end" if end is None else "start", "Give both a start and an end.")
    window = occupied_window(start, end, 0, 0)
    if window.end <= window.start:
        _reject("end", "The end must be after the start.")
    try:
        venue = db.get(Venue, venue_id)
        if venue is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venue not found")

        now = datetime.now(timezone.utc)
        expire_tentative_holds(db)
        show_names = user.role == Role.VENUE_STAFF.value
        closures = db.scalars(
            select(VenueUnavailability).where(
                VenueUnavailability.venue_id == venue.id,
                VenueUnavailability.start_time < window.end,
                VenueUnavailability.end_time > window.start,
            )
        ).all()
        bookings = db.scalars(
            select(VenueBooking)
            .where(
                VenueBooking.venue_id == venue.id,
                VenueBooking.status.in_(_BLOCKING_BOOKING_STATUSES),
                _active_hold_filter(now),
            )
            .options(joinedload(VenueBooking.event))
        ).unique()

        busy: list[BusyPeriod] = []
        items: list[VenueAvailabilityItem] = []
        for booking in bookings:
            occupied = occupied_window(
                booking.start_time, booking.end_time, venue.setup_minutes, venue.turnaround_minutes
            )
            if not occupied.overlaps(window):
                continue
            held = booking.status == BookingStatus.tentative_hold
            # Which event holds the venue is Venue Staff's to know (SCRUM-41);
            # a Coordinator only sees that it is taken.
            visible = show_names
            name = (booking.event.name or "Untitled event") if visible else None
            event_start, event_end = as_utc(booking.start_time), as_utc(booking.end_time)
            busy.append(
                BusyPeriod(
                    kind="tentative_hold" if held else "booking",
                    start=occupied.start,
                    end=occupied.end,
                    event_start=event_start,
                    event_end=event_end,
                    event_name=name,
                    expires_at=booking.expires_at if held else None,
                    hold_action=booking.hold_action if held and visible else None,
                )
            )
            items.append(
                VenueAvailabilityItem(
                    id=booking.id,
                    kind="tentative_hold" if held else "confirmed_booking",
                    start_time=event_start,
                    end_time=event_end,
                    occupied_start=occupied.start,
                    occupied_end=occupied.end,
                    event_id=booking.event_id if visible else None,
                    event_name=name,
                    expires_at=booking.expires_at if held else None,
                    hold_action=booking.hold_action if held and visible else None,
                    conflicts_with_unavailability=any(
                        as_utc(c.start_time) < event_end and as_utc(c.end_time) > event_start
                        for c in closures
                    ),
                )
            )
        for closure in closures:
            busy.append(
                BusyPeriod(
                    kind="closure",
                    start=as_utc(closure.start_time),
                    end=as_utc(closure.end_time),
                    reason_category=closure.reason_category,
                    reason=closure.reason,
                )
            )
            items.append(
                VenueAvailabilityItem(
                    id=closure.id,
                    kind="unavailability",
                    start_time=as_utc(closure.start_time),
                    end_time=as_utc(closure.end_time),
                    occupied_start=as_utc(closure.start_time),
                    occupied_end=as_utc(closure.end_time),
                    reason_category=closure.reason_category,
                    reason=closure.reason,
                )
            )
        busy.sort(key=lambda b: (b.start, b.end))
        items.sort(key=lambda i: (i.occupied_start or i.start_time, i.kind, i.id))
        return VenueAvailabilityOut(
            venue_id=venue.id, start=as_utc(start), end=as_utc(end), busy=busy, items=items
        )
    except ProgrammingError as exc:
        logger.exception("Failed to retrieve venue availability (venue_id=%s)", venue_id)
        if "venue_bookings.expires_at" in str(exc.orig) and "does not exist" in str(exc.orig):
            detail = (
                "The database is missing venue_bookings.expires_at. Apply "
                "backend/sql/019_multi_venue_tentative_holds.sql to the configured "
                "database, then retry."
            )
        else:
            detail = (
                "Availability could not be retrieved because a database query failed. "
                "Check the backend logs for the error details."
            )
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail) from exc
    except SQLAlchemyError as exc:
        logger.exception("Failed to retrieve venue availability (venue_id=%s)", venue_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Availability could not be retrieved because a database query failed. "
            "Check the backend logs for the error details.",
        ) from exc


@router.put("/{venue_id}/setup-turnaround", response_model=VenueDetail)
def save_setup_turnaround(
    venue_id: int,
    body: SetupTurnaroundUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(_venue_staff),
) -> VenueDetail:
    """Venue Staff set the whole minutes needed before and after an Event.

    Both values are saved together or not at all (the body is validated
    before anything is written). Saving the same values again changes
    nothing but who/when. Venue Staff only: a Coordinator reads the values
    but cannot change them.

    When the effective values change, the venue's future approved bookings
    are re-checked in the same transaction (the venue row is locked, so an
    approval cannot slip in between): any that now clash are flagged, never
    cancelled, and earlier flags that no longer apply are cleared. Saving the
    same values again re-checks nothing, so nobody is notified twice.
    """
    venue = _locked_venue(db, venue_id)
    before = effective_buffers(venue)
    venue.setup_minutes = body.setup_minutes
    venue.turnaround_minutes = body.turnaround_minutes
    venue.setup_turnaround_updated_by = user.id
    venue.setup_turnaround_updated_at = datetime.now(timezone.utc)
    flagged = cleared = 0
    if effective_buffers(venue) != before:
        flagged, cleared = recheck_venue(db, venue, user)
    db.commit()
    db.refresh(venue)
    detail = VenueDetail.model_validate(venue)
    detail.recheck = RecheckSummary(flagged=flagged, cleared=cleared)
    return detail


# --- Temporarily unavailable periods (SCRUM-93) -------------------------------
#
# Venue Staff record a period and a reason. It is saved even when bookings
# already fall inside it: those bookings are identified (and the approved ones
# flagged for Venue Staff to resolve) but never cancelled, and neither is their
# Event.

# Bookings that hold, or are asking for, the venue.
_AFFECTED_STATUSES = (BookingStatus.pending, BookingStatus.approved, BookingStatus.tentative_hold)


def _check_range(body: UnavailabilityIn) -> None:
    if as_utc(body.end_time) <= as_utc(body.start_time):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[{"loc": ["body", "end_time"], "msg": "The end must be after the start."}],
        )


def _affected(db: Session, period: VenueUnavailability, now: datetime) -> list[AffectedBooking]:
    """Future pending, held or approved bookings of the venue whose occupied
    window (setup and turnaround included, SCRUM-94) overlaps the period."""
    venue = db.get(Venue, period.venue_id)
    rows = [
        b
        for b in db.scalars(
            select(VenueBooking)
            .where(
                VenueBooking.venue_id == period.venue_id,
                VenueBooking.status.in_(_AFFECTED_STATUSES),
                _active_hold_filter(now),
                VenueBooking.start_time > now,
            )
            .options(joinedload(VenueBooking.event))
            .order_by(VenueBooking.start_time, VenueBooking.id)
        ).unique()
        if closure_overlaps(b, period, venue)
    ]
    return [
        AffectedBooking(
            booking_id=b.id,
            event_id=b.event_id,
            event_name=b.event.name or "Untitled event",
            status=str(b.status),
            start_time=as_utc(b.start_time),
            end_time=as_utc(b.end_time),
            flagged=b.conflict_flagged_at is not None,
        )
        for b in rows
    ]


def _period_out(
    db: Session, period: VenueUnavailability, user: User, recheck: RecheckSummary | None = None
) -> UnavailabilityOut:
    out = UnavailabilityOut.model_validate(period)
    out.start_time, out.end_time = as_utc(period.start_time), as_utc(period.end_time)
    if user.role == Role.VENUE_STAFF.value:
        out.affected_bookings = _affected(db, period, datetime.now(timezone.utc))
    out.recheck = recheck
    return out


def _locked_venue(db: Session, venue_id: int) -> Venue:
    # Sweep expired holds first: the sweep commits, which would drop the lock.
    expire_tentative_holds(db)
    venue = db.get(Venue, venue_id, with_for_update=True)
    if venue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venue not found")
    return venue


def _locked_period(db: Session, venue_id: int, period_id: int) -> VenueUnavailability:
    period = db.get(VenueUnavailability, period_id)
    if period is None or period.venue_id != venue_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unavailability period not found")
    return period


def _after_change(db: Session, venue: Venue, user: User) -> RecheckSummary:
    db.flush()
    flagged, cleared = recheck_venue(db, venue, user, notify_on_clear=True)
    return RecheckSummary(flagged=flagged, cleared=cleared)


@router.get("/{venue_id}/unavailability", response_model=list[UnavailabilityOut])
def list_unavailability(
    venue_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_internal),
) -> list[UnavailabilityOut]:
    """Every recorded period for the venue, soonest first, with the reason.
    Venue Staff also see the future bookings each one affects."""
    if db.get(Venue, venue_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venue not found")
    periods = db.scalars(
        select(VenueUnavailability)
        .where(VenueUnavailability.venue_id == venue_id)
        .order_by(VenueUnavailability.start_time, VenueUnavailability.id)
    )
    return [_period_out(db, p, user) for p in periods]


@router.post(
    "/{venue_id}/unavailability", response_model=UnavailabilityOut, status_code=status.HTTP_201_CREATED
)
def create_unavailability(
    venue_id: int,
    body: UnavailabilityIn,
    db: Session = Depends(get_db),
    user: User = Depends(_venue_staff),
) -> UnavailabilityOut:
    """Mark the venue unavailable. Venue Staff only (403 otherwise). An end
    not after the start is refused (422 naming `end_time`) and nothing is
    saved. Bookings already inside the period do not stop it being saved."""
    _check_range(body)
    venue = _locked_venue(db, venue_id)
    notices = PendingRequestNotices(db, venue)
    period = VenueUnavailability(
        venue_id=venue.id,
        start_time=body.start_time,
        end_time=body.end_time,
        reason_category=body.reason_category.value,
        reason=body.reason,
        created_by=user.id,
        updated_by=user.id,
        updated_at=datetime.now(timezone.utc),
    )
    db.add(period)
    recheck = _after_change(db, venue, user)
    notices.send()
    db.commit()
    db.refresh(period)
    return _period_out(db, period, user, recheck)


@router.put("/{venue_id}/unavailability/{period_id}", response_model=UnavailabilityOut)
def update_unavailability(
    venue_id: int,
    period_id: int,
    body: UnavailabilityIn,
    db: Session = Depends(get_db),
    user: User = Depends(_venue_staff),
) -> UnavailabilityOut:
    """Change a period. The venue is available again outside the new period:
    flags set only by the old one are cleared by the re-check."""
    _check_range(body)
    venue = _locked_venue(db, venue_id)
    period = _locked_period(db, venue_id, period_id)
    notices = PendingRequestNotices(db, venue)
    period.start_time = body.start_time
    period.end_time = body.end_time
    period.reason_category = body.reason_category.value
    period.reason = body.reason
    period.updated_by = user.id
    period.updated_at = datetime.now(timezone.utc)
    recheck = _after_change(db, venue, user)
    notices.send()
    db.commit()
    db.refresh(period)
    return _period_out(db, period, user, recheck)


@router.post("/{venue_id}/unavailability/{period_id}/end", response_model=UnavailabilityOut)
def end_unavailability_early(
    venue_id: int,
    period_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_venue_staff),
) -> UnavailabilityOut:
    """End a period that is under way now: its end becomes the current time.
    409 when it has not started or has already ended (use edit or delete)."""
    venue = _locked_venue(db, venue_id)
    period = _locked_period(db, venue_id, period_id)
    now = datetime.now(timezone.utc)
    if not (as_utc(period.start_time) <= now < as_utc(period.end_time)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only a period that is under way can be ended early.",
        )
    notices = PendingRequestNotices(db, venue)
    period.end_time = now
    period.updated_by = user.id
    period.updated_at = now
    recheck = _after_change(db, venue, user)
    notices.send()
    db.commit()
    db.refresh(period)
    return _period_out(db, period, user, recheck)


@router.delete("/{venue_id}/unavailability/{period_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_unavailability(
    venue_id: int,
    period_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_venue_staff),
) -> None:
    """Remove a period; the venue is available again for all of it."""
    venue = _locked_venue(db, venue_id)
    period = _locked_period(db, venue_id, period_id)
    notices = PendingRequestNotices(db, venue)
    db.delete(period)
    _after_change(db, venue, user)
    notices.send()
    db.commit()


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
            VenueBooking.status.in_(_SUITABILITY_BOOKING_STATUSES),
            _active_hold_filter(now),
        )
        .order_by(VenueBooking.id)
    ).unique().all()
    venue_results = []
    for booking in bookings:
        checks = _booking_suitability_checks(event, booking)
        venue_results.append(EventVenueSuitabilityItem(
            booking_id=booking.id,
            venue_id=booking.venue.id,
            venue_name=booking.venue.name,
            expected_attendance=(
                booking.expected_attendance
                if booking.expected_attendance is not None
                else event.expected_attendance
            ),
            suitable=all(check.met for check in checks),
            checks=checks,
        ))
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


@router.get(
    "/bookings/{booking_id}/suitability",
    response_model=EventVenueSuitabilityItem,
)
def check_booking_venue_suitability(
    booking_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(_coordinator),
) -> EventVenueSuitabilityItem:
    """Recheck only one active booking for an event assigned to the caller."""
    now = datetime.now(timezone.utc)
    expire_tentative_holds(db, now)
    booking = db.scalars(
        select(VenueBooking)
        .options(joinedload(VenueBooking.event), joinedload(VenueBooking.venue))
        .where(
            VenueBooking.id == booking_id,
            VenueBooking.status.in_(_SUITABILITY_BOOKING_STATUSES),
            _active_hold_filter(now),
        )
    ).unique().one_or_none()
    if booking is None or booking.event.coordinator_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active venue booking not found",
        )

    checks = _booking_suitability_checks(booking.event, booking)
    return EventVenueSuitabilityItem(
        booking_id=booking.id,
        venue_id=booking.venue.id,
        venue_name=booking.venue.name,
        expected_attendance=(
            booking.expected_attendance
            if booking.expected_attendance is not None
            else booking.event.expected_attendance
        ),
        suitable=all(check.met for check in checks),
        checks=checks,
    )
