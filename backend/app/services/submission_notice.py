"""Tell the Event Coordinator Lead a new Event Request is waiting.

A submitted request sits unassigned in the Lead's queue, so without this the
Lead would have to keep checking it. `SubmissionNotice` writes one
notification per Lead, in the submit transaction: if the submit rolls back
nobody is told, and a draft save or a blocked submit never reaches it.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.roles import Role
from app.models.enums import NotificationType
from app.models.events import Event
from app.models.user import User
from app.services.notifications import notify


class EventNotice:
    """Base: who is told, what it says, and how it is sent."""

    type: NotificationType

    def recipients(self, db: Session, event: Event) -> list[int]:
        raise NotImplementedError

    def message(self, event: Event) -> str:
        raise NotImplementedError

    def send(self, db: Session, event: Event) -> None:
        for user_id in self.recipients(db, event):
            notify(db, user_id=user_id, type=self.type, message=self.message(event), event_id=event.id)


class SubmissionNotice(EventNotice):
    """A new Event Request was submitted: every Lead gets name, Organiser, time."""

    type = NotificationType.event_submitted

    def recipients(self, db: Session, event: Event) -> list[int]:
        return list(db.scalars(select(User.id).where(User.role == Role.COORDINATOR_LEAD.value)))

    def message(self, event: Event) -> str:
        # Written into the text itself so the line still reads right if the
        # event is later renamed or the Organiser changes their name.
        when = event.submitted_at.strftime("%d %b %Y, %H:%M UTC")
        return (
            f"New Event Request '{event.name or 'Untitled event'}' from "
            f"{event.organiser.name}, submitted {when}."
        )
