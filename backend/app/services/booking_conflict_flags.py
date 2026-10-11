"""Flagging bookings that clash after a venue's setup/turnaround changes (SCRUM-92).

A booking is never cancelled or changed by this: it keeps its status, gets
`conflict_flagged_at`, the Event's Coordinator is told once, and Venue Staff
resolve it (change/cancel it, or keep it with a reason).

The caller holds the venue row lock and commits; nothing here commits.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.datetimes import as_utc
from app.domain.venue_occupancy import occupied_window
from app.models.enums import BookingStatus, NotificationType
from app.models.events import EventStatusHistory
from app.models.user import User
from app.models.venues import Venue, VenueBooking, VenueUnavailability
from app.services.notifications import notify

# Bookings that hold the venue and so can be flagged: approved bookings and,
# once SCRUM-97 adds the status, active holds (SCRUM-92 AC1). Until then the
# else branch keeps it to approved bookings only.
_HOLD = getattr(BookingStatus, "hold", None)
if _HOLD is not None:
    FLAGGABLE_STATUSES = (BookingStatus.approved, _HOLD)
else:
    FLAGGABLE_STATUSES = (BookingStatus.approved,)

# A flagged booking in one of these is no longer something to resolve.
INACTIVE_STATUSES = (BookingStatus.rejected, BookingStatus.cancelled)

# What a flagged booking is compared against: other APPROVED bookings only
# (the SCRUM-41 rule). A hold does not block anyone, so it is not added here.
BLOCKING_STATUSES = (BookingStatus.approved,)


def effective_buffers(venue: Venue) -> tuple[int, int]:
    return venue.setup_minutes or 0, venue.turnaround_minutes or 0


def _log(db: Session, booking: VenueBooking, actor: User, note: str) -> None:
    """An Activity Log line: no status change, so from == to."""
    db.add(
        EventStatusHistory(
            event_id=booking.event_id,
            changed_by=actor.id,
            from_status=booking.event.status,
            to_status=booking.event.status,
            note=note,
        )
    )


def _closures(db: Session, venue: Venue) -> list[VenueUnavailability]:
    return list(db.scalars(select(VenueUnavailability).where(VenueUnavailability.venue_id == venue.id)))


def closure_overlaps(booking: VenueBooking, closure: VenueUnavailability) -> bool:
    """A closure is a raw period (no setup/turnaround), the same rule the
    approval check and the venue search use: strict overlap with the event."""
    return as_utc(closure.start_time) < as_utc(booking.end_time) and as_utc(closure.end_time) > as_utc(
        booking.start_time
    )


def _clash_kind(
    booking: VenueBooking,
    blockers: list[VenueBooking],
    closures: list[VenueUnavailability],
    venue: Venue,
) -> str | None:
    """"booking" if it overlaps another approved booking, "unavailability" if
    it is inside a period the venue is marked unavailable, else None."""
    setup, turnaround = effective_buffers(venue)
    mine = occupied_window(booking.start_time, booking.end_time, setup, turnaround)
    if any(
        other.id != booking.id
        and mine.overlaps(occupied_window(other.start_time, other.end_time, setup, turnaround))
        for other in blockers
    ):
        return "booking"
    if any(closure_overlaps(booking, c) for c in closures):
        return "unavailability"
    return None


def _blockers(db: Session, venue: Venue) -> list[VenueBooking]:
    return list(
        db.scalars(
            select(VenueBooking).where(
                VenueBooking.venue_id == venue.id, VenueBooking.status.in_(BLOCKING_STATUSES)
            )
        )
    )


def release(db: Session, booking: VenueBooking, actor: User, note: str) -> bool:
    """Clear the flag and log why. False (and nothing logged) if not flagged."""
    if booking.conflict_flagged_at is None:
        return False
    booking.conflict_flagged_at = None
    _log(db, booking, actor, note)
    return True


def log_resolution(db: Session, booking: VenueBooking, actor: User, note: str) -> None:
    """Activity Log line for a resolution done outside this module."""
    _log(db, booking, actor, note)


def notify_cancelled(db: Session, event, venue_name: str, reason: str) -> None:
    notify(
        db,
        user_id=event.coordinator_id,
        event_id=event.id,
        type=NotificationType.venue_booking_conflict,
        message=(
            f"Venue Staff cancelled your booking '{venue_name}' for '{event.name or 'Untitled event'}' "
            f"to resolve a conflict. Reason: {reason}. The event is not cancelled: request another venue."
        ),
    )


def booking_changed(db: Session, booking: VenueBooking, actor: User, *, now: datetime | None = None) -> bool:
    """Call after a booking is changed or cancelled (SCRUM-96 will); the caller commits.

    Cancelled or rejected: its flag is cleared and logged. Otherwise (moved,
    shortened): the venue is re-checked and the flag clears if it no longer
    overlaps. Returns True if this booking's flag was cleared.
    """
    if booking.conflict_flagged_at is None:
        return False
    # Either way the venue is re-checked: a cancelled or moved booking may be
    # the only thing another flagged booking still overlapped. Re-checking also
    # clears this booking itself when it was cancelled or rejected.
    recheck_venue(db, booking.venue, actor, may_flag=False, now=now)
    return booking.conflict_flagged_at is None


def recheck_venue(
    db: Session, venue: Venue, actor: User, *, may_flag: bool = True, now: datetime | None = None
) -> tuple[int, int]:
    """Re-check the venue's future bookings; returns (newly flagged, cleared).

    Future means start_time > now. A booking already flagged that still
    clashes is left alone (no second notification); one that no longer
    clashes is un-flagged with an Activity Log line. `may_flag=False` only
    un-flags (used when a booking elsewhere was rejected or cancelled).
    """
    now = now or datetime.now(timezone.utc)
    db.flush()  # see a status the caller just changed
    blockers = _blockers(db, venue)
    closures = _closures(db, venue)
    flagged = cleared = 0
    # A flagged booking that was cancelled or rejected has nothing left to resolve.
    for dead in db.scalars(
        select(VenueBooking)
        .where(
            VenueBooking.venue_id == venue.id,
            VenueBooking.status.in_(INACTIVE_STATUSES),
            VenueBooking.conflict_flagged_at.is_not(None),
        )
        .options(joinedload(VenueBooking.event))
    ).unique():
        if release(db, dead, actor, f"Venue booking '{venue.name}' {dead.status.value}: the conflict flag is cleared."):
            cleared += 1
    candidates = db.scalars(
        select(VenueBooking)
        .where(
            VenueBooking.venue_id == venue.id,
            VenueBooking.status.in_(FLAGGABLE_STATUSES),
            VenueBooking.start_time > now,
        )
        .options(joinedload(VenueBooking.event))
        .order_by(VenueBooking.start_time, VenueBooking.id)
    ).unique()
    for booking in candidates:
        clash = _clash_kind(booking, blockers, closures, venue)
        if clash and booking.conflict_flagged_at is None and may_flag:
            booking.conflict_flagged_at = now
            flagged += 1
            event = booking.event
            if clash == "unavailability":
                log_text = (
                    f"Venue booking '{venue.name}' flagged: the venue was marked temporarily "
                    "unavailable during this booking. The Event is not cancelled."
                )
                tell = (
                    f"Your venue booking '{venue.name}' for '{event.name or 'Untitled event'}' "
                    "falls in a period the venue is unavailable. Venue Staff will resolve it."
                )
            else:
                log_text = (
                    f"Venue booking '{venue.name}' flagged: it now conflicts with another booking "
                    "after the venue's setup/turnaround time changed."
                )
                tell = (
                    f"Your venue booking '{venue.name}' for '{event.name or 'Untitled event'}' "
                    "now conflicts with another booking. Venue Staff will resolve it."
                )
            _log(db, booking, actor, log_text)
            if event.coordinator_id is not None:
                notify(
                    db,
                    user_id=event.coordinator_id,
                    event_id=event.id,
                    type=NotificationType.venue_booking_conflict,
                    message=tell,
                )
        elif not clash and release(
            db,
            booking,
            actor,
            f"Venue booking '{venue.name}' conflict cleared automatically: "
            "it no longer overlaps another booking or an unavailable period.",
        ):
            cleared += 1
    return flagged, cleared
