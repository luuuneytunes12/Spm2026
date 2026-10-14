from collections.abc import Iterable
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_role
from app.core.roles import Role
from app.models.venues import Venue
from app.schemas.venue import VenueDetail, VenueFilterOptions, VenueSummary
from app.services.venue_availability import as_utc, blocked_venue_ids, booked_venue_ids

router = APIRouter(prefix="/venues", tags=["venues"])

# Gated on role, not on VENUE_READ. The story is for INTERNAL users
# (Event Coordinators and Venue Staff), and VENUE_READ is also held by
# Attendees -- gating on the permission would show them internal venue
# details the story never meant them to see.
_internal = require_role(Role.COORDINATOR, Role.VENUE_STAFF)

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
    start: datetime | None = Query(
        None,
        description="Start of the window, ISO 8601. Venues booked, tentatively held or "
        "unavailable in it -- setup and turnaround time included -- are excluded.",
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

    venues = db.execute(stmt.order_by(Venue.name, Venue.id)).scalars().all()

    if start is not None and end is not None:
        # Approved bookings, tentative holds and recorded unavailability that
        # clash with the window, each venue's setup and turnaround time
        # included. The rule lives in app/services/venue_availability.py so
        # that approving a booking applies exactly the same one.
        taken = booked_venue_ids(db, venues, start, end) | blocked_venue_ids(db, venues, start, end)
        venues = [v for v in venues if v.id not in taken]

    # Layout, facilities and accessibility are matched here rather than in
    # SQL. They are Postgres arrays in production but JSON in the SQLite the
    # tests run on, and case-insensitive matching inside an array has no
    # expression that works the same on both. Keyword and capacity -- the
    # parts that shrink the list most -- stay in SQL, and the date window is
    # narrowed in SQL before its exact check. Fine at the hundreds of venues
    # ConnectSphere has; revisit if that becomes many thousands.
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
