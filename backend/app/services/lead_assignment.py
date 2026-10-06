"""The Event Coordinator Lead assigns and reassigns Events.

Both actions are the same shape -- load and lock the Event, check it may be
changed, change who coordinates it, leave a trail, tell the people involved,
commit -- so `LeadAssignmentAction` holds those steps once and a subclass
supplies the two that differ (`check` and `change`). Nothing in
`app.services.assignment` is modified: this reuses its activity-log and
notification helpers, and the automatic assignment there stays for the
Coordinator "release" flow.
"""

from fastapi import status as http
from sqlalchemy.orm import Session

from app.core.roles import Role
from app.models.enums import EventStatus, NotificationType
from app.models.events import Event, EventStatusHistory
from app.models.user import User
from app.services.assignment import _notify, _notify_organiser, _record
from app.services.assignment_overview import ActiveAssignments, UnassignedQueue
from app.services.notifications import notify

# An Event in one of these states is finished and can no longer be moved.
FINISHED_STATUSES: tuple[EventStatus, ...] = (
    EventStatus.rejected,
    EventStatus.cancelled,
    EventStatus.completed,
)


class AssignmentRefused(Exception):
    """The action is not allowed. Carries the HTTP status the router returns;
    the Event is left exactly as it was."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class LeadAssignmentAction:
    """Template for a Lead's assign / reassign. Call `apply`."""

    def __init__(self, db: Session, lead: User) -> None:
        self.db = db
        self.lead = lead

    # --- the two steps a subclass supplies ---------------------------------

    def check(self, event: Event, coordinator: User) -> None:
        """Raise AssignmentRefused if this Event may not be changed."""
        raise NotImplementedError

    def change(self, event: Event, coordinator: User) -> None:
        """Move the Event to `coordinator` and write the activity-log line."""
        raise NotImplementedError

    # --- the shared steps --------------------------------------------------

    def apply(self, event_id: int, coordinator_id: int) -> Event:
        event = self._lock(event_id)
        coordinator = self._coordinator(coordinator_id)
        self.check(event, coordinator)
        self.change(event, coordinator)
        self.db.commit()
        self.db.refresh(event)
        return event

    def _lock(self, event_id: int) -> Event:
        # FOR UPDATE: two Leads acting on the same Event at once are serialised,
        # so the second sees the first's result and is refused by `check`.
        event = self.db.query(Event).filter(Event.id == event_id).with_for_update().first()
        if event is None:
            raise AssignmentRefused(http.HTTP_404_NOT_FOUND, "Event not found")
        return event

    def _coordinator(self, coordinator_id: int) -> User:
        coordinator = self.db.get(User, coordinator_id)
        if coordinator is None or coordinator.role != Role.COORDINATOR.value:
            raise AssignmentRefused(http.HTTP_422_UNPROCESSABLE_CONTENT, "Choose an Event Coordinator")
        return coordinator


class AssignEvent(LeadAssignmentAction):
    """Assign a request from the Unassigned Queue: it leaves the queue and
    becomes Under Review with the chosen Coordinator."""

    def check(self, event: Event, coordinator: User) -> None:
        if UnassignedQueue().find(self.db, event.id) is None:
            raise AssignmentRefused(
                http.HTTP_409_CONFLICT, "This request is not in the Unassigned Queue; its assignment is unchanged"
            )

    def change(self, event: Event, coordinator: User) -> None:
        previous = event.status
        event.coordinator_id = coordinator.id
        event.status = EventStatus.under_review
        self.db.add(
            EventStatusHistory(
                event_id=event.id,
                changed_by=self.lead.id,
                from_status=previous,
                to_status=event.status,
                note=f"Assigned to {coordinator.name}.",
            )
        )
        _notify(self.db, coordinator.id, event)
        _notify_organiser(self.db, event, coordinator)


class ReassignEvent(LeadAssignmentAction):
    """Move an active Event to another Coordinator. Status, details and the
    earlier activity log are untouched; one line is added."""

    def check(self, event: Event, coordinator: User) -> None:
        if event.status in FINISHED_STATUSES:
            raise AssignmentRefused(http.HTTP_409_CONFLICT, "A finished Event cannot be reassigned")
        if ActiveAssignments().find(self.db, event.id) is None:
            raise AssignmentRefused(http.HTTP_409_CONFLICT, "This Event is not an active assignment")
        if event.coordinator_id == coordinator.id:
            raise AssignmentRefused(http.HTTP_409_CONFLICT, "That Event Coordinator already has this Event")

    def change(self, event: Event, coordinator: User) -> None:
        outgoing = self.db.get(User, event.coordinator_id)
        event.coordinator_id = coordinator.id
        _record(self.db, event, self.lead.id, f"Reassigned from {outgoing.name} to {coordinator.name}.")
        _notify(self.db, coordinator.id, event)
        notify(
            self.db,
            user_id=outgoing.id,
            type=NotificationType.event_reassigned_away,
            message=(
                f"{coordinator.name} has taken over coordinating "
                f"'{event.name or 'an event'}' (previously assigned to you)."
            ),
            event_id=event.id,
        )
        _notify_organiser(self.db, event, coordinator)
