"""Notifications: the one place every router/service goes to notify a user.

Call `notify(db, ...)` from inside the work that causes the notification,
before the caller's own `db.commit()`. The row is written in the same
transaction as that work, and the live push to the user's open streams
(GET /notifications/stream) only happens once that commit succeeds -- so a
request that fails and rolls back never notifies anyone.

A message is stored as finished text, so a time in it cannot follow the
reader's timezone. Write every one with `format_time`, `format_time_range` or
`format_date`, which give Singapore time whatever the stored value's zone.

The live side is an in-memory broker: one asyncio.Queue per open stream,
keyed by user id. That holds for a single uvicorn process; running several
workers would need a shared channel (e.g. Redis pub/sub) in its place.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.datetimes import as_utc
from app.domain.venue_operating_hours import VENUE_TIMEZONE
from app.models.enums import NotificationType
from app.models.notifications import Notification
from app.schemas.notification import NotificationOut

logger = logging.getLogger(__name__)

# Key on Session.info holding notifications staged by `notify` and not yet
# pushed -- they wait here until the transaction commits (or is discarded).
_PENDING_KEY = "pending_notifications"


class NotificationBroker:
    """Fans published notifications out to each user's open streams."""

    def __init__(self) -> None:
        self._subscribers: dict[int, set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = {}

    @asynccontextmanager
    async def subscribe(self, user_id: int) -> AsyncIterator[asyncio.Queue]:
        """A queue receiving `user_id`'s notifications while the block runs.

        One per open stream, so two tabs each get their own copy. Leaving
        the block -- including the client disconnecting -- unsubscribes.
        """
        entry = (asyncio.get_running_loop(), asyncio.Queue())
        self._subscribers.setdefault(user_id, set()).add(entry)
        logger.info("Notification stream opened for user %s", user_id)
        try:
            yield entry[1]
        finally:
            subscribers = self._subscribers.get(user_id)
            if subscribers is not None:
                subscribers.discard(entry)
                if not subscribers:
                    del self._subscribers[user_id]
            logger.info("Notification stream closed for user %s", user_id)

    def publish(self, user_id: int, payload: dict[str, Any]) -> None:
        """Push `payload` to every open stream of `user_id`; no-op if none.

        Safe to call from any thread: most routes are sync `def`s running in
        FastAPI's threadpool, while the queues belong to the event loop.
        """
        for loop, queue in list(self._subscribers.get(user_id, ())):
            loop.call_soon_threadsafe(queue.put_nowait, payload)


broker = NotificationBroker()


def _singapore(moment: datetime) -> datetime:
    return as_utc(moment).astimezone(VENUE_TIMEZONE)


def format_date(moment: datetime) -> str:
    """'2 Nov 2026'"""
    local = _singapore(moment)
    return f"{local.day} {local:%b %Y}"


def format_time(moment: datetime) -> str:
    """'2 Nov 2026, 09:00 SGT'"""
    return f"{format_date(moment)}, {_singapore(moment):%H:%M} SGT"


def format_time_range(start: datetime | None, end: datetime | None) -> str:
    """'2 Nov 2026, 09:00-17:00 SGT', or both dates when it spans days."""
    if start is None:
        return "no date set"
    if end is None:
        return format_time(start)
    local_start, local_end = _singapore(start), _singapore(end)
    if local_end.date() == local_start.date():
        return f"{format_date(start)}, {local_start:%H:%M}-{local_end:%H:%M} SGT"
    return f"{format_date(start)} {local_start:%H:%M} - {format_date(end)} {local_end:%H:%M} SGT"


def notify(
    db: Session,
    *,
    user_id: int,
    type: NotificationType,
    message: str,
    event_id: int | None = None,
) -> Notification:
    """Record a notification for `user_id`, pushed live once `db` commits.

    Does not commit -- the caller's own commit keeps the notification
    atomic with whatever caused it.
    """
    notification = Notification(user_id=user_id, event_id=event_id, type=type, message=message)
    db.add(notification)
    # Flush + refresh so the pushed payload carries the real id and the
    # server-generated created_at, same as GET /notifications would return.
    db.flush()
    db.refresh(notification)
    payload = NotificationOut.model_validate(notification).model_dump(mode="json")
    db.info.setdefault(_PENDING_KEY, []).append((user_id, payload))
    return notification


@event.listens_for(Session, "after_commit")
def _publish_pending(session: Session) -> None:
    for user_id, payload in session.info.pop(_PENDING_KEY, []):
        broker.publish(user_id, payload)


@event.listens_for(Session, "after_rollback")
def _discard_pending(session: Session) -> None:
    session.info.pop(_PENDING_KEY, None)
