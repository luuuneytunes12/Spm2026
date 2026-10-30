"""Tell an Event Organiser where their Event stands.

Only the Event's own Organiser is ever told: another Organiser's Event never
reaches them. Every notice is written in the caller's transaction (see
notify), so a save that rolls back tells nobody. Nothing here commits.

    OrganiserNotice                  base: an EventNotice sent to the Event's Organiser
      EventStatusChangedNotice         the Event's status changed: names the new one
      VenueBookingDecisionNotice       Venue Staff approved or rejected ONE booking
      EquipmentOutcomeNotice           Technical Support confirmed a requirement
                                       or found it unavailable

A status can change in a dozen places (submit, assignment, approval, Safety
Check, a reopen, cancel, ...), so the status notice is hooked on the Session,
like venue_release: `before_flush` notes each Event's status as the
transaction found it, and `before_commit` tells its Organiser once if the
status it commits with is different. Where the same work already sends the
Organiser a notice that names the new status (approved, rejected, a Safety
Check decision), that one stands and no second is sent.
"""

from sqlalchemy import event as sa_event
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.domain.requirement_progress import RequirementStatus
from app.models.enums import BookingStatus, EventStatus, NotificationType
from app.models.equipment import CoordinatorEquipmentRequirement
from app.models.events import Event
from app.services.notifications import _PENDING_KEY as _PENDING_NOTIFICATIONS
from app.services.submission_notice import EventNotice


def _name(event: Event) -> str:
    return event.name or "Untitled event"


class OrganiserNotice(EventNotice):
    """Base: sent to the Event's Organiser, and nobody else."""

    def recipients(self, db: Session, event: Event) -> list[int]:
        return [event.organiser_id] if event.organiser_id is not None else []


class EventStatusChangedNotice(OrganiserNotice):
    """The Event's status changed: name the Event and its new status."""

    type = NotificationType.event_status_changed

    def __init__(self, status: EventStatus) -> None:
        self.status = EventStatus(status)

    def message(self, event: Event) -> str:
        return f"Your event '{_name(event)}' is now {self.status.label}."


class VenueBookingDecisionNotice(OrganiserNotice):
    """Venue Staff decided one booking: name the Event, that Venue and the decision."""

    type = NotificationType.venue_booking_decided

    _WORDS = {BookingStatus.approved: "approved", BookingStatus.rejected: "rejected"}

    def __init__(
        self,
        venue_name: str,
        decision: BookingStatus,
        reason: str | None = None,
        alternative: str | None = None,
    ) -> None:
        if decision not in self._WORDS:
            raise ValueError(f"Not a booking decision: {decision}")
        self.venue_name = venue_name
        self.decision = decision
        self.reason = reason
        self.alternative = alternative

    def message(self, event: Event) -> str:
        text = (
            f"The venue booking of {self.venue_name} for '{_name(event)}' "
            f"was {self._WORDS[self.decision]} by Venue Staff."
        )
        if self.reason:
            text += f" Reason: {self.reason}"
        if self.alternative:
            text += f" Suggested alternative: {self.alternative}"
        return text


class EquipmentOutcomeNotice(OrganiserNotice):
    """Technical Support's outcome for one requirement: confirmed or unavailable."""

    type = NotificationType.equipment_outcome

    # The outcomes the Organiser hears about. Requested (still being worked
    # on, or only part reserved) and Available (freed after the event) are not.
    _WORDS = {RequirementStatus.RESERVED: "confirmed", RequirementStatus.UNAVAILABLE: "unavailable"}

    def __init__(
        self,
        requirement: CoordinatorEquipmentRequirement,
        outcome: RequirementStatus,
        reason: str | None = None,
    ) -> None:
        self.requirement = requirement
        self.outcome = outcome
        self.reason = reason

    @classmethod
    def for_change(
        cls,
        requirement: CoordinatorEquipmentRequirement,
        before: RequirementStatus,
        after: RequirementStatus,
        reason: str | None = None,
    ) -> "EquipmentOutcomeNotice | None":
        """The notice for a status change, or None when it is not news."""
        if before is after or after not in cls._WORDS:
            return None
        return cls(requirement, after, reason)

    def message(self, event: Event) -> str:
        r = self.requirement
        text = (
            f"Equipment for '{_name(event)}': {r.quantity_needed} x {r.category} "
            f"is {self._WORDS[self.outcome]} by Technical Support."
        )
        if self.outcome is RequirementStatus.UNAVAILABLE and self.reason:
            text += f" Reason: {self.reason}"
        return text


# --- the status hook ---------------------------------------------------------

# Notices that already tell the Organiser the new status in words of their
# own. When the work sent one of these, the generic status notice is not sent.
STATUS_ANNOUNCING_TYPES = frozenset(
    {
        NotificationType.event_status_changed,
        NotificationType.event_approved,
        NotificationType.event_rejected,
        NotificationType.safety_check_passed,
        NotificationType.safety_changes_requested,
        NotificationType.safety_check_rejected,
        NotificationType.event_cancelled,
    }
)

# Key on Session.info: {event id: the status this transaction found it in}.
_STATUS_FROM_KEY = "organiser_status_from"


def _already_announced(session: Session, event: Event) -> bool:
    return any(
        user_id == event.organiser_id
        and payload.get("event_id") == event.id
        and payload.get("type") in STATUS_ANNOUNCING_TYPES
        for user_id, payload in session.info.get(_PENDING_NOTIFICATIONS, [])
    )


@sa_event.listens_for(Session, "before_flush")
def _note_status_before(session: Session, flush_context, instances) -> None:
    found = session.info.setdefault(_STATUS_FROM_KEY, {})
    for obj in session.dirty:
        if not isinstance(obj, Event) or obj.id in found:
            continue
        history = inspect(obj).attrs.status.history
        if history.added:
            # The first status this transaction saw is the one it started from.
            found[obj.id] = history.deleted[0] if history.deleted else None


@sa_event.listens_for(Session, "before_commit")
def _tell_organisers(session: Session) -> None:
    session.flush()  # so status changes not yet flushed are noted too
    for event_id, before in session.info.pop(_STATUS_FROM_KEY, {}).items():
        event = session.get(Event, event_id)
        if event is None or event.status is None:
            continue
        if before is not None and EventStatus(before) == EventStatus(event.status):
            continue  # moved and came back within the same save: no news
        if _already_announced(session, event):
            continue
        EventStatusChangedNotice(event.status).send(session, event)
    # Sending flushes again; nothing it writes changes a status.
    session.info.pop(_STATUS_FROM_KEY, None)


@sa_event.listens_for(Session, "after_rollback")
def _discard_status_from(session: Session) -> None:
    session.info.pop(_STATUS_FROM_KEY, None)


__all__ = [
    "STATUS_ANNOUNCING_TYPES",
    "EquipmentOutcomeNotice",
    "EventStatusChangedNotice",
    "OrganiserNotice",
    "VenueBookingDecisionNotice",
]
