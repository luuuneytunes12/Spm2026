"""An Event Coordinator changing or cancelling one Venue Booking (SCRUM-96).

    VenueBookingChangeService
        The rules and the orchestration: change one booking, cancel one, or
        cancel every live booking of an event. Given its collaborators; builds
        only defaults for them.

    BookingChange (value object)
        What a change was -- the venue and each need, before and after. It
        decides whether anything changed and puts it into words.

    VenueStaffRecipients (abstract)  /  AllVenueStaff
        Who is told. No document assigns Venue Staff to venues and their
        queue is global, so today everyone with the role is told. A rule that
        tells only the staff of the venues involved would be another
        subclass, handed to the service in its place.

    ActivityLog (abstract)  /  EventHistoryLog
        Where the record goes. The real one writes the Event's status
        history, with the same status before and after: a change to one
        booking does not change the Event's status (DoD 11a).

A booking has no time of its own: it is the Event's. So a change is the venue
and what is needed of it, never a time.

Nothing here commits. The route commits, so the booking, its log line and its
notices are written together or not at all; and every rule is checked before
anything is changed, so a refusal leaves nothing behind.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.roles import Role
from app.domain.errors import Conflict, InvalidInput, NotFound
from app.models.enums import PLANNING_STATUSES, BookingStatus, NotificationType
from app.models.events import Event, EventStatusHistory
from app.models.user import User
from app.models.venues import Venue, VenueBooking
from app.services import booking_conflict_flags as flags
from app.services.notifications import notify

# Where a booking may be changed or cancelled: while the event is being
# planned, the same window in which a venue can be requested. Once the event
# goes to the Safety Officer its arrangement is judged as it stands, and a
# send-back returns it here. Kept equal to the requesting window on purpose
# (tests/test_venue_booking_change_service.py pins it): if requesting is ever
# widened -- W7 #2's replacement after the Safety Check -- changing and
# cancelling must widen with it.
VENUE_CHANGE_EVENT_STATUSES = PLANNING_STATUSES

# A booking that can still be changed or cancelled. Rejected and cancelled
# are history: another venue is asked for with a new request.
LIVE_BOOKING_STATUSES = (
    BookingStatus.pending,
    BookingStatus.tentative_hold,
    BookingStatus.approved,
)

# What a change may touch. Never a time.
_CHANGEABLE = frozenset(
    {
        "venue_id",
        "expected_attendance",
        "room_layout_preference",
        "accessibility_needs",
        "facilities_needs",
    }
)

_NEED_LABELS = {
    "room_layout_preference": "room layout",
    "accessibility_needs": "accessibility needs",
    "facilities_needs": "facilities",
}


def _clean(value: object) -> str | None:
    """Blank is not given: a need left blank is what the event says."""
    if value is None:
        return None
    return str(value).strip() or None


def _show(value: str | None) -> str:
    return f"'{value}'" if value else "as the event says"


@dataclass(frozen=True)
class BookingChange:
    """One change to a booking, as an immutable fact."""

    venue_before: str
    venue_after: str
    attendance_before: int | None
    attendance_after: int | None
    needs_before: Mapping[str, str | None]
    needs_after: Mapping[str, str | None]

    @property
    def changed_fields(self) -> list[str]:
        """What differs, in a fixed order: the venue, then each need."""
        fields = ["venue"] if self.venue_before != self.venue_after else []
        if self.attendance_before != self.attendance_after:
            fields.append("expected attendance")
        fields += [
            need
            for need in _NEED_LABELS
            if self.needs_before.get(need) != self.needs_after.get(need)
        ]
        return fields

    @property
    def is_empty(self) -> bool:
        return not self.changed_fields

    def summary(self) -> str:
        """The change in words, leaving out what did not change."""
        parts = []
        for field in self.changed_fields:
            if field == "venue":
                parts.append(f"venue {self.venue_before} → {self.venue_after}")
            elif field == "expected attendance":
                parts.append(
                    f"attendance {_show_number(self.attendance_before)} "
                    f"→ {_show_number(self.attendance_after)}"
                )
            else:
                parts.append(
                    f"{_NEED_LABELS[field]} {_show(self.needs_before.get(field))} "
                    f"→ {_show(self.needs_after.get(field))}"
                )
        return "; ".join(parts)


def _show_number(value: int | None) -> str:
    return str(value) if value is not None else "as the event says"


class VenueStaffRecipients(ABC):
    """Who is told about a change to a booking at some venues."""

    @abstractmethod
    def for_venues(self, venue_ids: Sequence[int]) -> list[User]:
        """The people to tell, each once, for bookings at these venues."""


class AllVenueStaff(VenueStaffRecipients):
    """Every Venue Staff member, whichever venues are involved.

    No document assigns staff to venues, and the Venue Staff queue already
    shows every venue to every one of them. Nobody else is told: not the
    Coordinator who did it, nor any other role.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def for_venues(self, venue_ids: Sequence[int]) -> list[User]:
        return list(
            self._db.scalars(
                select(User).where(User.role == Role.VENUE_STAFF.value).order_by(User.id)
            )
        )


class ActivityLog(ABC):
    """The record of who did what, and when."""

    @abstractmethod
    def record(self, event: Event, actor: User, note: str) -> None:
        """Add one entry for `event`."""


class EventHistoryLog(ActivityLog):
    """The Event's Activity Log: its status history, written with no change
    of status. Entries are only ever added, never edited."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def record(self, event: Event, actor: User, note: str) -> None:
        self._db.add(
            EventStatusHistory(
                event_id=event.id,
                changed_by=actor.id,
                from_status=event.status,
                to_status=event.status,
                note=note,
            )
        )


class VenueBookingChangeService:
    """An Event Coordinator's changes to the Venue Bookings of their events.

    Every rule about who may, when, and what happens lives here and nowhere
    else: the routes only parse input and call these methods.
    """

    def __init__(
        self,
        db: Session,
        recipients: VenueStaffRecipients | None = None,
        activity: ActivityLog | None = None,
    ) -> None:
        self._db = db
        self._recipients = recipients if recipients is not None else AllVenueStaff(db)
        self._activity = activity if activity is not None else EventHistoryLog(db)

    # --- queries ------------------------------------------------------------

    def live_bookings(self, event_id: int, coordinator: User) -> list[VenueBooking]:
        """The bookings "cancel all" would cancel, oldest first: the list the
        Coordinator is shown before confirming."""
        event = self._own_event(event_id, coordinator)
        self._ensure_in_window(event)
        return self._live_of(event)

    # --- commands -----------------------------------------------------------

    def change(self, booking_id: int, coordinator: User, **changes: object) -> VenueBooking:
        """Change a booking's venue and/or what is needed of it. It returns
        to Pending for Venue Staff. Fields not mentioned are left alone."""
        unknown = set(changes) - _CHANGEABLE
        if unknown:
            raise TypeError(f"Not changeable here: {', '.join(sorted(unknown))}")

        new_venue_id = changes.get("venue_id")
        booking, event = self._locked_booking(
            booking_id, coordinator, extra_venues=[new_venue_id] if new_venue_id else []
        )
        self._ensure_in_window(event)
        self._ensure_live(booking)

        old_venue = booking.venue
        new_venue = self._checked_venue(event, booking, new_venue_id)
        needs_after = {
            need: (_clean(changes[need]) if need in changes else getattr(booking, need))
            for need in _NEED_LABELS
        }
        attendance_after = changes.get("expected_attendance", booking.expected_attendance)
        if attendance_after is not None and (
            isinstance(attendance_after, bool)
            or not isinstance(attendance_after, int)
            or attendance_after <= 0
        ):
            raise InvalidInput(
                "Expected attendance must be a whole number greater than 0.",
                field="expected_attendance",
            )
        change = BookingChange(
            venue_before=old_venue.name,
            venue_after=new_venue.name,
            attendance_before=booking.expected_attendance,
            attendance_after=attendance_after,
            needs_before={need: getattr(booking, need) for need in _NEED_LABELS},
            needs_after=needs_after,
        )
        if change.is_empty:
            raise InvalidInput("Change the venue, or what you need from it.")

        # Every rule has passed; from here on, things change.
        held_the_venue = booking.status in (BookingStatus.approved, BookingStatus.tentative_hold)
        booking.venue = new_venue
        booking.expected_attendance = change.attendance_after
        for need, value in needs_after.items():
            setattr(booking, need, value)
        self._back_to_pending(booking)
        if held_the_venue:
            self._free(old_venue, coordinator)

        self._activity.record(
            event,
            coordinator,
            f"Venue booking '{old_venue.name}' changed: {change.summary()}. "
            "It returns to Pending for Venue Staff review.",
        )
        self._tell(
            event,
            [old_venue.id, new_venue.id],
            NotificationType.venue_booking_changed,
            f"The Event Coordinator changed the venue booking '{old_venue.name}' for "
            f"'{self._name(event)}': {change.summary()}. It is back in the queue as a pending request.",
        )
        self._db.flush()
        return booking

    def cancel(
        self, booking_id: int, coordinator: User, reason: str | None = None
    ) -> VenueBooking:
        """Cancel one booking. The others, and the event, are untouched."""
        booking, event = self._locked_booking(booking_id, coordinator)
        self._ensure_in_window(event)
        self._ensure_live(booking)

        self._withdraw(booking, event, coordinator, _clean(reason))
        self._db.flush()
        return booking

    def cancel_all(
        self,
        event_id: int,
        coordinator: User,
        booking_ids: Sequence[int],
        reason: str | None = None,
    ) -> list[VenueBooking]:
        """Cancel every live booking of the event -- exactly those listed.

        The second confirmation is enforced here, not only by the page: what
        is cancelled is the list the Coordinator was shown, and if the live
        bookings are no longer exactly those, nothing is cancelled. Cancelling
        only the listed ones would leave them believing everything is gone;
        cancelling a new one would cancel something they never saw.
        """
        event = self._locked_own_event(event_id, coordinator)
        self._ensure_in_window(event)
        if not booking_ids:
            raise InvalidInput("Choose the bookings to cancel.", field="booking_ids")

        live = self._lock_live_of(event)
        if not live:
            raise Conflict("This event has no live venue bookings to cancel.")
        if set(booking_ids) != {b.id for b in live}:
            raise Conflict(
                "The event's venue bookings changed since the list was shown. "
                "Review the list and confirm again."
            )

        why = _clean(reason)
        for booking in live:
            self._withdraw(booking, event, coordinator, why, free_venue=False)
        for venue in {b.venue_id: b.venue for b in live}.values():
            self._free(venue, coordinator)
        self._db.flush()
        return live

    # --- rules --------------------------------------------------------------

    def _own_event(self, event_id: int, coordinator: User) -> Event:
        """The event, if it is assigned to this Coordinator. Anything else is
        NotFound: "not yours" and "does not exist" must look the same, or ids
        could be probed."""
        event = self._db.get(Event, event_id)
        if event is None or event.coordinator_id != coordinator.id:
            raise NotFound("Event not found")
        return event

    def _locked_own_event(self, event_id: int, coordinator: User) -> Event:
        """The same, with the row locked: two overlapping requests on one
        event are taken one at a time."""
        self._own_event(event_id, coordinator)  # ownership first, before any lock
        event = self._db.get(Event, event_id, with_for_update=True, populate_existing=True)
        if event is None or event.coordinator_id != coordinator.id:  # reassigned meanwhile
            raise NotFound("Event not found")
        return event

    def _locked_booking(
        self, booking_id: int, coordinator: User, extra_venues: Sequence[int] = ()
    ) -> tuple[VenueBooking, Event]:
        """The booking and its event, locked in the order the rest of the
        venue code uses -- event, then venues by id, then the booking -- so
        none of them can deadlock on another."""
        found = self._db.execute(
            select(VenueBooking.event_id, VenueBooking.venue_id).where(VenueBooking.id == booking_id)
        ).one_or_none()
        if found is None:
            raise NotFound("Booking not found")
        event_id, venue_id = found
        try:
            event = self._locked_own_event(event_id, coordinator)
        except NotFound:
            raise NotFound("Booking not found") from None
        for locked in sorted({venue_id, *extra_venues}):
            self._db.get(Venue, locked, with_for_update=True, populate_existing=True)
        booking = self._db.get(VenueBooking, booking_id, with_for_update=True, populate_existing=True)
        if booking is None:
            raise NotFound("Booking not found")
        return booking, event

    @staticmethod
    def _ensure_in_window(event: Event) -> None:
        if event.status not in VENUE_CHANGE_EVENT_STATUSES:
            raise Conflict(
                "Venue bookings can only be changed or cancelled while the event is "
                "'Event Approved' or 'Planning Event'; it is '" + str(event.status) + "'."
            )

    @staticmethod
    def _ensure_live(booking: VenueBooking) -> None:
        if booking.status not in LIVE_BOOKING_STATUSES:
            raise Conflict(
                f"This booking is {booking.status.value} and can no longer be changed or cancelled."
            )

    def _checked_venue(self, event: Event, booking: VenueBooking, venue_id: object) -> Venue:
        """The venue the booking will be at: its own, or a valid new one."""
        if venue_id is None or venue_id == booking.venue_id:
            return booking.venue
        venue = self._db.get(Venue, venue_id) if isinstance(venue_id, int) else None
        if venue is None:
            raise InvalidInput("That venue does not exist.", field="venue_id")
        if not venue.is_active:
            raise InvalidInput(f"{venue.name} is inactive and cannot be booked.", field="venue_id")
        already = self._db.scalar(
            select(VenueBooking.id).where(
                VenueBooking.event_id == event.id,
                VenueBooking.venue_id == venue.id,
                VenueBooking.id != booking.id,
                VenueBooking.status.in_(LIVE_BOOKING_STATUSES),
            )
        )
        if already is not None:
            raise Conflict(
                f"This event already has a live booking request for {venue.name}.",
                field="venue_id",
            )
        return venue

    def _live_of(self, event: Event) -> list[VenueBooking]:
        return list(
            self._db.scalars(
                select(VenueBooking)
                .where(
                    VenueBooking.event_id == event.id,
                    VenueBooking.status.in_(LIVE_BOOKING_STATUSES),
                )
                .order_by(VenueBooking.id)
            )
        )

    def _lock_live_of(self, event: Event) -> list[VenueBooking]:
        """The live bookings, with their venues locked first and the rows
        after, in the same order as everywhere else."""
        venue_ids = sorted(
            set(
                self._db.scalars(
                    select(VenueBooking.venue_id).where(
                        VenueBooking.event_id == event.id,
                        VenueBooking.status.in_(LIVE_BOOKING_STATUSES),
                    )
                )
            )
        )
        for venue_id in venue_ids:
            self._db.get(Venue, venue_id, with_for_update=True, populate_existing=True)
        return list(
            self._db.scalars(
                select(VenueBooking)
                .where(
                    VenueBooking.event_id == event.id,
                    VenueBooking.status.in_(LIVE_BOOKING_STATUSES),
                )
                .order_by(VenueBooking.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )

    # --- effects ------------------------------------------------------------

    @staticmethod
    def _back_to_pending(booking: VenueBooking) -> None:
        """Pending again, with nothing left of the old decision to read as if
        it still applied. A pending booking does not hold the venue, so it
        does not count as approved until it is approved again."""
        booking.status = BookingStatus.pending
        booking.reviewed_by = None
        booking.reviewed_at = None
        booking.decision_notes = None
        booking.suggested_alternative = None
        booking.expires_at = None
        booking.safety_recheck_reason = None
        booking.conflict_flagged_at = None

    def _withdraw(
        self,
        booking: VenueBooking,
        event: Event,
        coordinator: User,
        reason: str | None,
        *,
        free_venue: bool = True,
    ) -> None:
        """Cancel one booking, record it and tell Venue Staff.

        The Coordinator's reason goes in the log and the notice, not in
        `decision_notes`: that field is Venue Staff's, and the booking would
        read as if they had given it.
        """
        held_the_venue = booking.status in (BookingStatus.approved, BookingStatus.tentative_hold)
        venue = booking.venue
        booking.status = BookingStatus.cancelled
        booking.expires_at = None
        booking.safety_recheck_reason = None
        if held_the_venue and free_venue:
            self._free(venue, coordinator)

        suffix = f" Reason: {reason}" if reason else ""
        self._activity.record(
            event, coordinator, f"Venue booking '{venue.name}' cancelled by the Event Coordinator.{suffix}"
        )
        self._tell(
            event,
            [venue.id],
            NotificationType.venue_booking_cancelled,
            f"The Event Coordinator cancelled the venue booking '{venue.name}' for "
            f"'{self._name(event)}'.{suffix}",
        )

    def _free(self, venue: Venue, coordinator: User) -> None:
        """The venue no longer holds this booking: other bookings that only
        clashed with it stop being flagged, and a flag on this one clears."""
        flags.recheck_venue(self._db, venue, coordinator, may_flag=False)

    def _tell(
        self, event: Event, venue_ids: Sequence[int], kind: NotificationType, message: str
    ) -> None:
        for person in self._recipients.for_venues(venue_ids):
            notify(self._db, user_id=person.id, type=kind, message=message, event_id=event.id)

    @staticmethod
    def _name(event: Event) -> str:
        return event.name or "Untitled event"
