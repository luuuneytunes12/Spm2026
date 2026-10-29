"""Tell Attendees about the events they are registered for.

    AttendeeNotice                 base: an EventNotice whose recipients are Attendees
      EventChangedNotice             a confirmed Event's date, time or Venue changed:
                                     every Attendee still REGISTERED gets one notice
                                     per save, listing everything that changed.
                                     Withdrawn and unregistered people get nothing.
      RegistrationStatusNotice       one Attendee's registration was saved as
                                     Registered or Withdrawn: that Attendee is told.

Every notice is written in the caller's transaction (see notify): if the save
rolls back nobody is told. Nothing here commits.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import EventStatus, NotificationType, RegistrationStatus
from app.models.events import Event
from app.models.registrations import Registration
from app.services.submission_notice import EventNotice

# A change is only news to Attendees once the event is confirmed: before
# that nobody can be registered for it.
CONFIRMED = EventStatus.safety_check_passed


def _utc(value: datetime) -> datetime:
    # SQLite hands back naive datetimes; Postgres aware ones. Both are UTC.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _as_datetime(value: datetime | str | None) -> datetime | None:
    """A change request stores its values as JSON, so a date arrives as an
    ISO string; the event column holds a datetime."""
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return _utc(value)


def _when(value: datetime) -> str:
    return f"{value.day} {value:%b %Y, %H:%M} UTC"


class AttendeeNotice(EventNotice):
    """Base: sent to Attendees about an Event."""


class EventChangedNotice(AttendeeNotice):
    """One notice per save, to every Attendee still registered."""

    type = NotificationType.event_details_changed

    def __init__(self, changes: list[str]) -> None:
        self.changes = changes

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
        name = event.name or "Untitled event"
        return f"'{name}', which you are registered for, has changed: " + "; ".join(self.changes) + "."

    def send(self, db: Session, event: Event) -> None:
        if self.changes:
            super().send(db, event)

    # --- what changed, in words ---------------------------------------------

    @staticmethod
    def schedule_changes(
        before_start: datetime | str | None,
        before_end: datetime | str | None,
        after_start: datetime | str | None,
        after_end: datetime | str | None,
    ) -> list[str]:
        """The new start and/or end, only for the ones that actually moved."""
        changes = []
        if _as_datetime(after_start) != _as_datetime(before_start) and after_start is not None:
            changes.append(f"it now starts {_when(_as_datetime(after_start))}")
        if _as_datetime(after_end) != _as_datetime(before_end) and after_end is not None:
            changes.append(f"it now ends {_when(_as_datetime(after_end))}")
        return changes

    @staticmethod
    def venue_change(new_venue: str, old_venue: str) -> list[str]:
        return [f"the venue is now {new_venue} (replacing {old_venue})"]


class RegistrationStatusNotice(EventNotice):
    """One Attendee's registration was saved: confirm the Event and its status."""

    type = NotificationType.registration_status_changed

    _LABELS = {
        RegistrationStatus.registered: "Registered",
        RegistrationStatus.withdrawn: "Withdrawn",
    }

    def __init__(self, registration: Registration) -> None:
        self.registration = registration

    def recipients(self, db: Session, event: Event) -> list[int]:
        return [self.registration.attendee_id]

    def message(self, event: Event) -> str:
        name = event.name or "Untitled event"
        when = f" on {_when(_utc(event.proposed_start))}" if event.proposed_start else ""
        status = self._LABELS[self.registration.status]
        return f"Your registration for '{name}'{when} is now {status}."
