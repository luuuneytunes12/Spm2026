"""When a venue is free: the one overlap rule shared by the venue search and
booking approval, so the two can never disagree about the same venue.

A venue needs time either side of every event -- `setup_minutes` to prepare
before it and `turnaround_minutes` to reset after it (Week 1 briefing,
"Setup and Turnaround Time"). So a booking of [start, end) occupies the
venue for [start - setup, end + turnaround), and so does the event being
searched for. Two of them clash when those padded periods overlap, which
means consecutive events need `setup + turnaround` minutes between them.

A recorded unavailability period (maintenance, renovation, ...) is not an
event and needs no setup of its own; it clashes when it overlaps the padded
period of the event being searched for.

Overlap is strict -- each starts before the other ends -- so periods that
only touch do not clash: with no setup or turnaround, a session ending at
09:00 leaves the room free for one starting at 09:00.

The exact check runs in Python rather than SQL. Padding a timestamp by a
per-venue number of minutes has no expression that works the same on the
Postgres used in production and the SQLite the unit tests run on. SQL still
does the narrowing: it is given the widest padding of the venues in play as
a plain parameter, so it returns a small superset that Python then checks
venue by venue.
"""

from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import BookingStatus
from app.models.venues import Venue, VenueBooking, VenueUnavailability

# Bookings that take a venue out of a date search.
#
# `approved` is a confirmed booking (W4 p4: "A confirmed booking should affect
# whether that venue is considered available"). `pending` is the TENTATIVE
# HOLD: a request awaiting a Venue Staff decision holds the venue until it is
# decided (Week 1 briefing, "Tentative Venue Holding"). Rejected, cancelled
# and hold_expired bookings are history and never hold anything.
HOLDING_BOOKING_STATUSES = (BookingStatus.approved, BookingStatus.pending)

# Bookings that stop Venue Staff APPROVING another one. Only confirmed ones:
# two Coordinators may both hold the same slot while their requests wait,
# and refusing to approve either because of the other would leave both stuck.
CONFIRMED_BOOKING_STATUSES = (BookingStatus.approved,)


def as_utc(moment: datetime) -> datetime:
    """Normalise to UTC. A time without a zone is read as UTC -- SQLite hands
    back naive times, and the frontend always sends a zone."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def occupied(venue: Venue, start: datetime, end: datetime) -> tuple[datetime, datetime]:
    """How long an event of [start, end) keeps `venue` busy, setup and
    turnaround included."""
    return (
        as_utc(start) - timedelta(minutes=venue.setup_minutes or 0),
        as_utc(end) + timedelta(minutes=venue.turnaround_minutes or 0),
    )


def overlaps(a: tuple[datetime, datetime], b: tuple[datetime, datetime]) -> bool:
    """Each starts before the other ends. Periods that only touch do not."""
    return as_utc(a[0]) < as_utc(b[1]) and as_utc(a[1]) > as_utc(b[0])


def _reach(venues: Sequence[Venue]) -> timedelta:
    """The widest gap any of these venues needs between two events -- how far
    either side of the window SQL must look so nothing is missed."""
    return timedelta(
        minutes=max((v.setup_minutes or 0) + (v.turnaround_minutes or 0) for v in venues)
    )


def booked_venue_ids(
    db: Session,
    venues: Sequence[Venue],
    start: datetime,
    end: datetime,
    *,
    statuses: Iterable[BookingStatus] = HOLDING_BOOKING_STATUSES,
    ignore_booking_id: int | None = None,
) -> set[int]:
    """Ids of the `venues` with a booking in `statuses` that clashes with an
    event of [start, end), setup and turnaround included.

    `ignore_booking_id` leaves one booking out -- the one being approved,
    which cannot clash with itself.
    """
    if not venues:
        return set()
    by_id = {v.id: v for v in venues}
    start, end = as_utc(start), as_utc(end)
    reach = _reach(venues)

    stmt = select(VenueBooking).where(
        VenueBooking.venue_id.in_(by_id),
        VenueBooking.status.in_(tuple(statuses)),
        VenueBooking.start_time < end + reach,
        VenueBooking.end_time > start - reach,
    )
    if ignore_booking_id is not None:
        stmt = stmt.where(VenueBooking.id != ignore_booking_id)

    busy: set[int] = set()
    for booking in db.scalars(stmt):
        venue = by_id[booking.venue_id]
        if overlaps(
            occupied(venue, booking.start_time, booking.end_time),
            occupied(venue, start, end),
        ):
            busy.add(venue.id)
    return busy


def blocked_venue_ids(
    db: Session, venues: Sequence[Venue], start: datetime, end: datetime
) -> set[int]:
    """Ids of the `venues` with a recorded unavailability period that clashes
    with an event of [start, end), setup and turnaround included. A recorded
    period has no status: once recorded, it blocks."""
    if not venues:
        return set()
    by_id = {v.id: v for v in venues}
    start, end = as_utc(start), as_utc(end)
    reach = _reach(venues)

    stmt = select(VenueUnavailability).where(
        VenueUnavailability.venue_id.in_(by_id),
        VenueUnavailability.start_time < end + reach,
        VenueUnavailability.end_time > start - reach,
    )

    blocked: set[int] = set()
    for period in db.scalars(stmt):
        venue = by_id[period.venue_id]
        if overlaps((period.start_time, period.end_time), occupied(venue, start, end)):
            blocked.add(venue.id)
    return blocked
