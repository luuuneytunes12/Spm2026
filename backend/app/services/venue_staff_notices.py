"""Tell Venue Staff what they need to review or re-plan at their venues.

Every Venue Staff member manages every venue (confirmed with the customer),
so every one of them is told -- through the same recipient rule the booking
change notices use, AllVenueStaff. Nobody else is. Every notice is written in
the caller's transaction (see notify), so a save that rolls back tells
nobody. Nothing here commits.

    VenueStaffNotice                 base: an EventNotice sent to every Venue Staff member
      BookingRequestedNotice           a booking was requested, or a replacement for one
                                       whose venue became unavailable (AC1, AC2)
      ApprovedEventChangedNotice       the date, time or expected attendance of an Event
                                       with an Approved booking changed (AC4)
      SafetyReturnedNotice             the Event did not clear its Safety Check and is
                                       back in Planning Event (AC6)

`ApprovedEventChangedNotice.before(db, event)` is taken BEFORE the change is
applied: a date or attendance change reopens the Event's bookings for review
in the same save, so afterwards they are no longer Approved.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.datetimes import as_utc
from app.domain.venue_booking_changes import AllVenueStaff
from app.models.enums import BookingStatus, NotificationType
from app.models.events import Event
from app.models.venues import Venue, VenueBooking
from app.services.submission_notice import EventNotice
from app.services.tech_support_notices import when


def _name(event: Event) -> str:
    return event.name or "Untitled event"


class VenueStaffNotice(EventNotice):
    """Base: sent to every Venue Staff member, each once."""

    def recipients(self, db: Session, event: Event) -> list[int]:
        return [staff.id for staff in AllVenueStaff(db).for_venues([])]


class BookingRequestedNotice(VenueStaffNotice):
    """A booking request to review: the Event, the Venue, and the date/time."""

    type = NotificationType.venue_booking_requested

    def __init__(self, booking: VenueBooking, replaces: VenueBooking | None = None) -> None:
        self.booking = booking
        self.replaces = replaces

    def message(self, event: Event) -> str:
        b = self.booking
        text = (
            f"New venue booking request for '{_name(event)}': {b.venue.name}, "
            f"{when(b.start_time, b.end_time)}."
        )
        if self.replaces is not None:
            text += f" It replaces {self.replaces.venue.name}, which became unavailable."
        return text


@dataclass(frozen=True)
class EventBefore:
    """What Venue Staff planned around, read before a change is applied."""

    start: datetime | None
    end: datetime | None
    attendance: int | None
    approved_venues: tuple[str, ...]


class ApprovedEventChangedNotice(VenueStaffNotice):
    """The Event, its Approved venue(s), and what changed -- one per save."""

    type = NotificationType.approved_event_changed

    def __init__(self, venues: tuple[str, ...], changes: list[str]) -> None:
        self.venues = venues
        self.changes = changes

    @staticmethod
    def before(db: Session, event: Event) -> EventBefore:
        venues = db.scalars(
            select(Venue.name)
            .join(VenueBooking, VenueBooking.venue_id == Venue.id)
            .where(VenueBooking.event_id == event.id, VenueBooking.status == BookingStatus.approved)
            .order_by(VenueBooking.id)
        )
        return EventBefore(event.proposed_start, event.proposed_end, event.expected_attendance, tuple(venues))

    @classmethod
    def since(cls, before: EventBefore, event: Event) -> "ApprovedEventChangedNotice":
        """What changed between `before` and the Event as it is now."""
        changes = []
        moved = _differs(before.start, event.proposed_start) or _differs(before.end, event.proposed_end)
        if moved:
            changes.append(
                f"it now runs {when(event.proposed_start, event.proposed_end)} "
                f"(was {when(before.start, before.end)})"
            )
        if before.attendance != event.expected_attendance:
            changes.append(
                f"expected attendance is now {event.expected_attendance} (was {before.attendance})"
            )
        return cls(before.approved_venues, changes)

    def send(self, db: Session, event: Event) -> None:
        # Only news when the Event had an Approved booking and something changed.
        if self.venues and self.changes:
            super().send(db, event)

    def message(self, event: Event) -> str:
        return (
            f"'{_name(event)}', approved at {' and '.join(self.venues)}, has changed: "
            + "; ".join(self.changes)
            + "."
        )


class SafetyReturnedNotice(VenueStaffNotice):
    """The Event did not clear its Safety Check and is back in Planning Event.

    `already_told` are the Venue Staff the Safety Officer's own notice
    reached (those who decided a booking it marked), so nobody hears twice.
    """

    type = NotificationType.safety_returned_to_planning

    def __init__(self, reason: str, already_told: set[int] | None = None) -> None:
        self.reason = reason
        self.already_told = already_told or set()

    def recipients(self, db: Session, event: Event) -> list[int]:
        return [user_id for user_id in super().recipients(db, event) if user_id not in self.already_told]

    def message(self, event: Event) -> str:
        return (
            f"'{_name(event)}' did not clear its Safety Check and is back in Planning Event. "
            f"Reason: {self.reason}"
        )


def _differs(a: datetime | None, b: datetime | None) -> bool:
    if a is None or b is None:
        return a is not b
    return as_utc(a) != as_utc(b)
