"""Telling Coordinators of PENDING requests when a venue's unavailability
changes (SCRUM-94).

Approved bookings and active holds are flagged by the conflict re-check
(`booking_conflict_flags.recheck_venue`), which tells their Coordinator when
the flag is set and when it is lifted. A pending request is not flaggable --
Venue Staff already see the clash in their review queue -- so this class does
the telling for it: snapshot which pending requests are affected before a
period is created, edited, ended or deleted, compare after, and notify only
the change. Nothing here touches a booking or its Event.

The caller holds the venue row lock and commits; nothing here commits.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.enums import BookingStatus, NotificationType
from app.models.venues import Venue, VenueBooking, VenueUnavailability
from app.services.booking_conflict_flags import closure_overlaps, unavailable_notice
from app.services.notifications import notify


@dataclass(frozen=True)
class _Hit:
    booking: VenueBooking
    closure: VenueUnavailability


class PendingRequestNotices:
    """Use as: `notices = PendingRequestNotices(db, venue)` BEFORE changing a
    period, then `notices.send()` after the change (before the commit)."""

    def __init__(self, db: Session, venue: Venue) -> None:
        self.db = db
        self.venue = venue
        self.before = self._affected()

    def _affected(self) -> dict[int, _Hit]:
        """Future pending requests whose occupied window overlaps any period,
        each with the first period it overlaps."""
        self.db.flush()
        now = datetime.now(timezone.utc)
        closures = list(
            self.db.scalars(
                select(VenueUnavailability)
                .where(VenueUnavailability.venue_id == self.venue.id)
                .order_by(VenueUnavailability.start_time, VenueUnavailability.id)
            )
        )
        hits: dict[int, _Hit] = {}
        for booking in self.db.scalars(
            select(VenueBooking)
            .where(
                VenueBooking.venue_id == self.venue.id,
                VenueBooking.status == BookingStatus.pending,
                VenueBooking.start_time > now,
            )
            .options(joinedload(VenueBooking.event))
        ).unique():
            closure = next((c for c in closures if closure_overlaps(booking, c, self.venue)), None)
            if closure is not None:
                hits[booking.id] = _Hit(booking, closure)
        return hits

    def send(self) -> tuple[int, int]:
        """Notify newly affected and no-longer-affected requests' Coordinators;
        returns (told affected, told cleared)."""
        after = self._affected()
        newly = [after[i] for i in after.keys() - self.before.keys()]
        freed = [self.before[i] for i in self.before.keys() - after.keys()]
        for hit in newly:
            self._tell(hit, unavailable_notice(self.venue, hit.closure, hit.booking, what="request"))
        for hit in freed:
            self._tell(
                hit,
                f"{self.venue.name} is no longer unavailable during your request for "
                f"'{hit.booking.event.name or 'Untitled event'}': the mark is removed and no further "
                "action is needed.",
            )
        return len(newly), len(freed)

    def _tell(self, hit: _Hit, message: str) -> None:
        coordinator_id = hit.booking.event.coordinator_id
        if coordinator_id is None:
            return
        notify(
            self.db,
            user_id=coordinator_id,
            event_id=hit.booking.event_id,
            type=NotificationType.venue_unavailability_recorded,
            message=message,
        )
