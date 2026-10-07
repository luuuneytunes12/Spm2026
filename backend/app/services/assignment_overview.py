"""The Event Coordinator Lead's queue and assignment overview.

Each view is a small class: `EventListing` holds the shared behaviour (what
"active" means, ordering, running the query) and a subclass narrows it with
one filter. Nothing here changes an event -- assigning and reassigning are
separate actions; the active statuses are shared with the assignment workload.
"""

from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Query, Session

from app.models.enums import EventStatus
from app.core.roles import Role
from app.models.events import Event
from app.models.user import User
from app.services.assignment import ACTIVE_ASSIGNMENT_STATUSES


class EventListing:
    """Active Event Requests, newest activity first. Subclasses narrow it
    (`narrow`) and may change the order (`order`)."""

    def narrow(self, query: Query) -> Query:
        return query

    def order(self, query: Query) -> Query:
        return query.order_by(Event.updated_at.desc(), Event.id.desc())

    def query(self, db: Session) -> Query:
        base = db.query(Event).filter(Event.status.in_(ACTIVE_ASSIGNMENT_STATUSES))
        return self.order(self.narrow(base))

    def rows(self, db: Session) -> list[Event]:
        return self.query(db).all()


class UnassignedRequests(EventListing):
    """Active requests with no Coordinator yet -- the Lead's assignment queue."""

    def narrow(self, query: Query) -> Query:
        return query.filter(Event.coordinator_id.is_(None))


class CoordinatorAssignments(EventListing):
    """Active requests that do have a Coordinator: who holds what."""

    def narrow(self, query: Query) -> Query:
        return query.filter(Event.coordinator_id.is_not(None))


class UnassignedQueue(UnassignedRequests):
    """The Lead's Unassigned Queue: submitted requests still awaiting a
    Coordinator, oldest submission first. Drafts never appear (they are not
    an active status), and neither does anything already assigned."""

    def narrow(self, query: Query) -> Query:
        return super().narrow(query).filter(Event.status == EventStatus.submitted_awaiting_coordinator)

    def order(self, query: Query) -> Query:
        return query.order_by(Event.submitted_at.asc(), Event.id.asc())

    def find(self, db: Session, event_id: int) -> Event | None:
        """One request, but only if it is currently in the queue."""
        return self.query(db).filter(Event.id == event_id).first()


# What the Lead's overview calls an "active" Event. Submitted requests only
# appear here once assigned; unassigned submitted requests stay in the queue.
LEAD_ACTIVE_STATUSES: tuple[EventStatus, ...] = (
    EventStatus.submitted_awaiting_coordinator,
    EventStatus.under_review,
    EventStatus.awaiting_organiser_reply,
    EventStatus.event_approved,
    EventStatus.planning_event,
    EventStatus.awaiting_safety_check,
    EventStatus.safety_check_passed,
)


class ActiveAssignments(CoordinatorAssignments):
    """The Coordinator Assignments overview: active Events that have a
    Coordinator, optionally only one Coordinator's."""

    def __init__(self, coordinator_id: int | None = None) -> None:
        self.coordinator_id = coordinator_id

    def narrow(self, query: Query) -> Query:
        query = super().narrow(query).filter(Event.status.in_(LEAD_ACTIVE_STATUSES))
        if self.coordinator_id is not None:
            query = query.filter(Event.coordinator_id == self.coordinator_id)
        return query

    def find(self, db: Session, event_id: int) -> Event | None:
        """One Event, but only if it is currently an active assignment."""
        return self.query(db).filter(Event.id == event_id).first()


@dataclass(frozen=True)
class CoordinatorLoad:
    id: int
    name: str
    email: str
    active_events: int


class CoordinatorWorkload:
    """Every Coordinator with how many active Events they hold, so the Lead
    can balance work. Counts use the same definition of active as
    `ActiveAssignments`, so the number beside a name always equals the length
    of the list filtered to that name."""

    def rows(self, db: Session) -> list[CoordinatorLoad]:
        counts = (
            db.query(Event.coordinator_id, func.count(Event.id))
            .filter(Event.status.in_(LEAD_ACTIVE_STATUSES), Event.coordinator_id.is_not(None))
            .group_by(Event.coordinator_id)
            .all()
        )
        held = dict(counts)
        coordinators = db.query(User).filter(User.role == Role.COORDINATOR.value).order_by(User.name, User.id).all()
        return [CoordinatorLoad(c.id, c.name, c.email, held.get(c.id, 0)) for c in coordinators]
