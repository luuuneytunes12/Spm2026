"""Tell the Safety Officer an event has joined their queue.

An event enters the queue ('Awaiting Safety Check') only when its Coordinator
submits it -- the first time, or again after a Safety Officer sent it back.
Checks are not assigned to one officer, so every Safety Officer is told, in
the submit transaction: if the submit rolls back nobody is notified.

    SafetyOfficerNotice          base: every Safety Officer, event + date + Coordinator
      SafetyCheckRequestedNotice   submitted, or resubmitted after being sent back
"""

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.roles import Role
from app.models.enums import EventStatus, NotificationType
from app.models.events import Event, EventStatusHistory
from app.models.user import User
from app.services.submission_notice import EventNotice


def describe(event: Event) -> str:
    """'Spring Fair' on 2 Nov 2026 (Event Coordinator: Jane Tan).

    Written into the text itself, so the line still reads right if the event
    is later renamed, moved or handed to another Coordinator."""
    name = event.name or "Untitled event"
    when = (
        f"{event.proposed_start.day} {event.proposed_start:%b %Y}"
        if event.proposed_start
        else "no date set"
    )
    coordinator = event.coordinator.name if event.coordinator else "none assigned"
    return f"'{name}' on {when} (Event Coordinator: {coordinator})"


class SafetyOfficerNotice(EventNotice):
    """Base: sent to every Safety Officer -- checks are not assigned to one."""

    def recipients(self, db: Session, event: Event) -> list[int]:
        return list(
            db.scalars(select(User.id).where(User.role == Role.SAFETY_OFFICER.value).order_by(User.id))
        )


class SafetyCheckRequestedNotice(SafetyOfficerNotice):
    """The event has just entered the queue."""

    type = NotificationType.safety_check_requested

    def __init__(self, *, resubmitted: bool) -> None:
        self.resubmitted = resubmitted

    def message(self, event: Event) -> str:
        verb = "resubmitted" if self.resubmitted else "submitted"
        return f"{describe(event)} was {verb} for a Safety Check."


def was_sent_back_before(db: Session, event: Event) -> bool:
    """Whether the event has been in the queue and sent back to planning
    before -- so this submit is a resubmission."""
    return bool(
        db.scalar(
            select(
                exists().where(
                    EventStatusHistory.event_id == event.id,
                    EventStatusHistory.from_status == EventStatus.awaiting_safety_check,
                    EventStatusHistory.to_status == EventStatus.planning_event,
                )
            )
        )
    )
