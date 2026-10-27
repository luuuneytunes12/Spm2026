"""A confirmed Event goes back to planning when a replacement venue is approved (SCRUM-95).

When an Event is 'Safety Check Passed (Event Confirmed)' and a replacement for
one of its Venue Bookings is approved, the arrangement the Safety Officer
passed no longer stands. The Event returns to 'Planning Event' (it is NOT
cancelled), the Activity Log records it, and the Event Coordinator is told.
Registration is gated on the status, so it is blocked until the Event passes
the Safety Check again.

Any other status is left alone. The caller commits.
"""

from sqlalchemy.orm import Session

from app.models.enums import EventStatus, NotificationType
from app.models.events import Event, EventStatusHistory
from app.models.user import User
from app.services.notifications import notify


class SafetyCheckReopen:
    def __init__(self, db: Session) -> None:
        self.db = db

    def apply(self, event: Event, actor: User, cause: str) -> bool:
        """`cause` completes "... because <cause>". True if the Event moved."""
        if event.status != EventStatus.safety_check_passed:
            return False
        name = event.name or "Untitled event"
        self.db.add(
            EventStatusHistory(
                event_id=event.id,
                changed_by=actor.id,
                from_status=event.status,
                to_status=EventStatus.planning_event,
                note=f"Returned to Planning Event because {cause}. The Event is not cancelled.",
            )
        )
        event.status = EventStatus.planning_event
        message = (
            f"'{name}' is back in Planning Event because {cause}. The Event is not cancelled; "
            "it needs a new Safety Check and registration is blocked until it passes."
        )
        if event.coordinator_id is not None:
            notify(
                self.db,
                user_id=event.coordinator_id,
                event_id=event.id,
                type=NotificationType.event_returned_to_planning,
                message=message,
            )
        return True
