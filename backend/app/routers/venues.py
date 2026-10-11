from collections.abc import Iterable
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.datetimes import as_utc
from app.core.db import get_db
from app.core.deps import require_role
from app.core.roles import Role
from app.domain.venue_occupancy import occupied_window
from app.models.enums import BookingStatus
from app.models.user import User
from app.models.venues import Venue, VenueBooking, VenueUnavailability
from app.services.booking_conflict_flags import effective_buffers, recheck_venue
from app.schemas.venue import (
    BusyPeriod,
    AffectedBooking,
    RecheckSummary,
    SetupTurnaroundUpdate,
    UnavailabilityIn,
    UnavailabilityOut,
    VenueAvailability,
    VenueDetail,
    VenueFilterOptions,
    VenueSummary,
)

router = APIRouter(prefix="/venues", tags=["venues"])

# Gated on role, not on VENUE_READ. The story is for INTERNAL users
# (Event Coordinators and Venue Staff), and VENUE_READ is also held by
# Attendees -- gating on the permission would show them internal venue
# details the story never meant them to see.
_internal = require_role(Role.COORDINATOR, Role.VENUE_STAFF)
_venue_staff = require_role(Role.VENUE_STAFF)

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
_BLOCKING_BOOKING_STATUSES = (BookingStatus.approved,)


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
        # A recorded closure (maintenance, renovation, ...) has no status:
        # once recorded, it blocks. Closures are raw periods, no buffers.
        blocked = exists().where(
            VenueUnavailability.venue_id == Venue.id,
            VenueUnavailability.start_time < window_end,
            VenueUnavailability.end_time > window_start,
        )
        stmt = stmt.where(~blocked)

    venues = list(db.execute(stmt.order_by(Venue.name, Venue.id)).scalars().all())

    if start is not None and end is not None:
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


@router.get("/{venue_id}/availability", response_model=VenueAvailability)
def venue_availability(
    venue_id: int,
    start: datetime | None = Query(None, description="Start of the range, ISO 8601."),
    end: datetime | None = Query(None, description="End of the range, ISO 8601."),
    db: Session = Depends(get_db),
    user: User = Depends(_internal),
) -> VenueAvailability:
    """When the venue is NOT available within a range: the occupied period
    (event plus setup/turnaround) of every approved booking that overlaps it,
    and every recorded closure. Anything not listed is free. Pending,
    rejected and cancelled bookings never appear.

    Only Venue Staff are told which event holds the venue; a Coordinator
    sees that it is taken, not by whom.
    """
    if start is None or end is None:
        _reject("end" if end is None else "start", "Give both a start and an end.")
    window = occupied_window(start, end, 0, 0)
    if window.end <= window.start:
        _reject("end", "The end must be after the start.")
    venue = db.get(Venue, venue_id)
    if venue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venue not found")

    show_names = user.role == Role.VENUE_STAFF.value
    busy: list[BusyPeriod] = []
    approved = db.scalars(
        select(VenueBooking)
        .where(VenueBooking.venue_id == venue.id, VenueBooking.status.in_(_BLOCKING_BOOKING_STATUSES))
        .options(joinedload(VenueBooking.event))
    ).unique()
    for booking in approved:
        occupied = occupied_window(
            booking.start_time, booking.end_time, venue.setup_minutes, venue.turnaround_minutes
        )
        if occupied.overlaps(window):
            busy.append(
                BusyPeriod(
                    kind="booking",
                    start=occupied.start,
                    end=occupied.end,
                    event_start=as_utc(booking.start_time),
                    event_end=as_utc(booking.end_time),
                    event_name=(booking.event.name or "Untitled event") if show_names else None,
                )
            )
    for closure in db.scalars(
        select(VenueUnavailability).where(
            VenueUnavailability.venue_id == venue.id,
            VenueUnavailability.start_time < window.end,
            VenueUnavailability.end_time > window.start,
        )
    ):
        busy.append(
            BusyPeriod(
                kind="closure",
                start=as_utc(closure.start_time),
                end=as_utc(closure.end_time),
                reason_category=closure.reason_category,
                reason=closure.reason,
            )
        )
    busy.sort(key=lambda b: (b.start, b.end))
    return VenueAvailability(venue_id=venue.id, busy=busy)


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
    venue = db.get(Venue, venue_id, with_for_update=True)
    if venue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Venue not found")
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
_AFFECTED_STATUSES = (BookingStatus.pending, BookingStatus.approved)


def _check_range(body: UnavailabilityIn) -> None:
    if as_utc(body.end_time) <= as_utc(body.start_time):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[{"loc": ["body", "end_time"], "msg": "The end must be after the start."}],
        )


def _affected(db: Session, period: VenueUnavailability, now: datetime) -> list[AffectedBooking]:
    """Future pending or approved bookings of the venue inside the period."""
    rows = db.scalars(
        select(VenueBooking)
        .where(
            VenueBooking.venue_id == period.venue_id,
            VenueBooking.status.in_(_AFFECTED_STATUSES),
            VenueBooking.start_time > now,
            VenueBooking.start_time < as_utc(period.end_time),
            VenueBooking.end_time > as_utc(period.start_time),
        )
        .options(joinedload(VenueBooking.event))
        .order_by(VenueBooking.start_time, VenueBooking.id)
    ).unique()
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
    flagged, cleared = recheck_venue(db, venue, user)
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
    period.start_time = body.start_time
    period.end_time = body.end_time
    period.reason_category = body.reason_category.value
    period.reason = body.reason
    period.updated_by = user.id
    period.updated_at = datetime.now(timezone.utc)
    recheck = _after_change(db, venue, user)
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
    period.end_time = now
    period.updated_by = user.id
    period.updated_at = now
    recheck = _after_change(db, venue, user)
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
    db.delete(period)
    _after_change(db, venue, user)
    db.commit()
