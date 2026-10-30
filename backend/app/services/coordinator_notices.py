"""Tell the Event Coordinator about the Events they are responsible for.

Only the Coordinator the Event is assigned to NOW is told: once it is
reassigned away, nothing more about it reaches them, and an Event nobody is
assigned to tells nobody. Every notice is written in the caller's
transaction (see notify), so a save that rolls back tells nobody. Nothing
here commits.

    CoordinatorNotice                    base: an EventNotice sent to the Event's Coordinator
      CoordinatorVenueDecisionNotice       Venue Staff approved or rejected ONE booking
      CoordinatorEquipmentOutcomeNotice    Technical Support reserved a requirement in
                                           full, or marked it unavailable
      ChangeRequestSubmittedNotice         the Organiser asked for changes

The Venue and equipment notices say the same thing the Organiser is told
(organiser_notices), so they take that wording and change only who hears it.
Assignment, reassignment and a clarification reply are already notified
where they happen (assignment, lead_assignment, clarifications).
"""

from sqlalchemy.orm import Session

from app.models.enums import NotificationType
from app.models.events import Event, EventChangeRequest
from app.services.organiser_notices import EquipmentOutcomeNotice, VenueBookingDecisionNotice
from app.services.submission_notice import EventNotice


class CoordinatorNotice(EventNotice):
    """Base: sent to the Coordinator the Event is assigned to, and nobody else."""

    def recipients(self, db: Session, event: Event) -> list[int]:
        return [event.coordinator_id] if event.coordinator_id is not None else []


class CoordinatorVenueDecisionNotice(CoordinatorNotice, VenueBookingDecisionNotice):
    """The Venue, the decision, and the reason or alternative when given."""


class CoordinatorEquipmentOutcomeNotice(CoordinatorNotice, EquipmentOutcomeNotice):
    """The Event and the equipment, reserved in full or unavailable."""


class ChangeRequestSubmittedNotice(CoordinatorNotice):
    """The Organiser submitted a Change Request: who, for what, and why.

    Named from the Event's Organiser, the only one who can submit one: the
    signed-in user a route is given is built from the token and has no name.
    """

    type = NotificationType.change_request_submitted

    def __init__(self, change_request: EventChangeRequest) -> None:
        self.change_request = change_request

    def message(self, event: Event) -> str:
        return (
            f"{event.organiser.name} submitted a change request for "
            f"'{event.name or 'Untitled event'}': {self.change_request.description}"
        )
