from collections.abc import AsyncIterable

from fastapi import APIRouter, Depends
from fastapi.sse import EventSourceResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.models.notifications import Notification
from app.models.user import User
from app.schemas.notification import NotificationOut
from app.services.notifications import broker

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
def list_my_notifications(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[NotificationOut]:
    """The caller's own notifications, newest first.

    Not gated by a Permission (unlike /events): every authenticated role
    can receive notifications, and there is nothing to distinguish
    between them here beyond "this is mine".
    """
    # id.desc() as a tiebreaker: two notifications created in the same
    # transaction can land on the identical `created_at` (SQLite's
    # CURRENT_TIMESTAMP has only 1-second resolution), and insertion order
    # is the only thing that still distinguishes "newest" between them.
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
