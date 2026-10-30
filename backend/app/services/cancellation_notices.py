"""Tell everyone involved in an Event that it was cancelled, so they stop
planning or preparing for it.

Each role's notice extends that role's own notice base, so "who is told"
stays the rule the rest of that role's notices follow:

    AttendeeCancelledNotice      (AttendeeNotice)      every Attendee still REGISTERED;
                                                       a withdrawn one is not told (AC1, AC6)
    VenueCancelledNotice         (VenueStaffNotice)    every Venue Staff member, one per
                                                       active booking: Venue and date/time (AC2)
    EquipmentCancelledNotice     (TechSupportNotice)   the Technical Support Staff who
                                                       reserved the equipment (AC3)
    SafetyCheckCancelledNotice   (SafetyCheckWithdrawnNotice)  every Safety Officer, if it
                                                       was awaiting its Safety Check (AC4)
    OrganiserCancelledNotice     (OrganiserNotice)     the Event's Organiser (AC5)
    CoordinatorCancelledNotice   (CoordinatorNotice)   its Coordinator (AC5)

`EventCancellation` reads what the Event had BEFORE the cancel takes effect
-- its status, its active bookings (released at commit by venue_release) and
its reserved equipment (set to cancelled by the route) -- and then sends
them all in the cancel's own transaction. If it rolls back nobody is told.
Nothing here commits.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.enums import BookingStatus, EquipmentStatus, EventStatus, NotificationType, RegistrationStatus
from app.models.equipment import EquipmentRequest
from app.models.events import Event
from app.models.registrations import Registration
from app.models.venues import VenueBooking
from app.services.attendee_notices import AttendeeNotice
from app.services.coordinator_notices import CoordinatorNotice
from app.services.organiser_notices import OrganiserNotice
from app.services.safety_notices import SafetyCheckWithdrawnNotice, describe
from app.services.tech_support_notices import TechSupportNotice, when
from app.services.venue_staff_notices import VenueStaffNotice

# Live bookings: the ones a Venue is being prepared for (venue_release frees them).
ACTIVE_BOOKING_STATUSES = (BookingStatus.pending, BookingStatus.tentative_hold, BookingStatus.approved)


def _name(event: Event) -> str:
    return event.name or "Untitled event"


class _WithReason:
    """A cancellation notice that carries the Coordinator's reason."""

    type = NotificationType.event_cancelled

    def __init__(self, reason: str) -> None:
        self.reason = reason


class AttendeeCancelledNotice(_WithReason, AttendeeNotice):
    """The Event name and why -- to Attendees still registered."""

    def recipients(self, db: Session, event: Event) -> list[int]:
        return list(
            db.scalars(
                select(Registration.attendee_id)
                .where(
                    Registration.event_id == event.id,
                    Registration.status == RegistrationStatus.registered,
                )
                .order_by(Registration.attendee_id)
            )
        )

    def message(self, event: Event) -> str:
        return f"'{_name(event)}', which you are registered for, has been cancelled. Reason: {self.reason}"


class OrganiserCancelledNotice(_WithReason, OrganiserNotice):
    def message(self, event: Event) -> str:
        return f"Your event '{_name(event)}' has been cancelled. Reason: {self.reason}"


class CoordinatorCancelledNotice(_WithReason, CoordinatorNotice):
    def message(self, event: Event) -> str:
        return f"'{_name(event)}', which you coordinate, has been cancelled. Reason: {self.reason}"


class VenueCancelledNotice(VenueStaffNotice):
    """One active booking: the Event, the Venue and its date/time.

    The Venue Staff member who decided this booking is left out: the
    release notice (venue_release) already tells them, with the same facts.
    """

    type = NotificationType.event_cancelled

    def __init__(self, booking: VenueBooking) -> None:
        self.booking = booking

    def recipients(self, db: Session, event: Event) -> list[int]:
        return [user_id for user_id in super().recipients(db, event) if user_id != self.booking.reviewed_by]

    def message(self, event: Event) -> str:
        b = self.booking
        return (
            f"'{_name(event)}' has been cancelled. Its booking of {b.venue.name} "
            f"({when(b.start_time, b.end_time)}) is no longer needed."
        )


class EquipmentCancelledNotice(TechSupportNotice):
    """The Event and its reserved equipment -- to whoever reserved it.

    A reservation with nobody recorded against it tells every Technical
    Support Staff member, so it is never missed.
    """

    type = NotificationType.event_cancelled

    def __init__(self, lines: list[EquipmentRequest]) -> None:
        self.lines = lines

    def recipients(self, db: Session, event: Event) -> list[int]:
        reservers = {line.reviewed_by for line in self.lines}
        if None in reservers:
            return super().recipients(db, event)
        return sorted(reservers)

    def message(self, event: Event) -> str:
        items = ", ".join(f"{line.quantity_requested} x {line.equipment.name}" for line in self.lines)
        return f"'{_name(event)}' has been cancelled. Its reserved equipment is no longer needed: {items}."


class SafetyCheckCancelledNotice(SafetyCheckWithdrawnNotice):
    """Same type (and link: the queue) as any other exit from the queue."""

    def message(self, event: Event) -> str:
        return (
            f"{describe(event)} has left your Safety Check queue because it was cancelled, "
            f"so it no longer needs checking. Reason: {self.reason}"
        )


class EventCancellation:
    """Everyone involved in one Event, told it was cancelled and why."""

    def __init__(self, db: Session, event: Event) -> None:
        # Read before the cancel takes effect.
        self.db = db
        self.event = event
        self.previous_status = event.status
        self.bookings = list(
            db.scalars(
                select(VenueBooking)
                .options(joinedload(VenueBooking.venue))
                .where(VenueBooking.event_id == event.id, VenueBooking.status.in_(ACTIVE_BOOKING_STATUSES))
                .order_by(VenueBooking.id)
            ).unique()
        )
        self.equipment = [line for line in event.equipment_items if line.status is EquipmentStatus.reserved]

    def send(self, reason: str) -> None:
        db, event = self.db, self.event
        AttendeeCancelledNotice(reason).send(db, event)
        for booking in self.bookings:
            VenueCancelledNotice(booking).send(db, event)
        if self.equipment:
            EquipmentCancelledNotice(self.equipment).send(db, event)
        if self.previous_status == EventStatus.awaiting_safety_check:
            SafetyCheckCancelledNotice(reason=reason).send(db, event)
        OrganiserCancelledNotice(reason).send(db, event)
        CoordinatorCancelledNotice(reason).send(db, event)
