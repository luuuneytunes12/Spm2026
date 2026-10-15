"""The Event's Activity Log: who did what, and when.

    ActivityLog (abstract)   where a record goes
    EventHistoryLog          the real one: the Event's status history

A domain service is handed an ActivityLog and records through it, so the rule
that something is recorded is tested without the database it is recorded in,
and a different record-keeper is a different subclass.

The real log writes the Event's status history with the SAME status before and
after: what happened is not a change of the Event's status (DoD 11a: a change
to one Venue Booking or Equipment Requirement does not change the Event status
by itself). Entries are only ever added, never edited.
"""

from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from app.models.events import Event, EventStatusHistory
from app.models.user import User


class ActivityLog(ABC):
    """The record of who did what, and when."""

    @abstractmethod
    def record(self, event: Event, actor: User, note: str) -> None:
        """Add one entry for `event`, made by `actor`."""


class EventHistoryLog(ActivityLog):
    """The Event's Activity Log: its status history, written with no change
    of status."""

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
