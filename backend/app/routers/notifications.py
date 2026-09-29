from collections.abc import AsyncIterable

from fastapi import APIRouter, Depends
from fastapi.sse import EventSourceResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.models.notifications import Notification
from app.models.user import User
from app.schemas.notification import MarkReadIn, MarkReadOut, NotificationOut
from app.services.notifications import broker

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
def list_my_notifications(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[NotificationOut]:
    """The signed-in user's own notifications, newest first.

    Scoped by row (`user_id == caller`), same principle as the assigned-events
    routes: everyone can hold this endpoint, but only your own rows come back.
    """
    notifications = (
        db.query(Notification)
        .filter(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .all()
    )
    return [NotificationOut.model_validate(n) for n in notifications]


@router.post("/read", response_model=MarkReadOut)
def mark_notifications_read(
    body: MarkReadIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MarkReadOut:
    """Mark the given notifications as read -- single, multi-select and
    select-all all come through here.

    Ids that are not the caller's (or do not exist) are skipped rather than
    404'd: the `user_id` filter is what makes that safe, and staying silent
    means the endpoint cannot be used to probe which ids exist. `updated`
    counts only rows that actually went from unread to read.
    """
    updated = (
        db.query(Notification)
        .filter(
            Notification.user_id == user.id,
            Notification.id.in_(body.ids),
            Notification.is_read.is_(False),
        )
        .update({Notification.is_read: True}, synchronize_session=False)
    )
    db.commit()
    return MarkReadOut(updated=updated)


@router.post("/read-all", response_model=MarkReadOut)
def mark_all_notifications_read(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MarkReadOut:
    """Mark every unread notification of the caller's as read -- including
    ones the client never loaded, which is why this takes no ids."""
    updated = (
        db.query(Notification)
        .filter(Notification.user_id == user.id, Notification.is_read.is_(False))
        .update({Notification.is_read: True}, synchronize_session=False)
    )
    db.commit()
    return MarkReadOut(updated=updated)


@router.get("/stream", response_class=EventSourceResponse)
async def stream_my_notifications(
    user: User = Depends(get_current_user),
) -> AsyncIterable[NotificationOut]:
    """Server-sent events: the signed-in user's new notifications, live.

    Scoped the same way as the list above -- the user comes from the access
    token, never from the URL. Only notifications created after the stream
    opens arrive here; GET /notifications is still where history comes from.
    Idle streams get keep-alive pings from EventSourceResponse itself.
    """
    async with broker.subscribe(user.id) as queue:
        while True:
            yield NotificationOut(**await queue.get())
