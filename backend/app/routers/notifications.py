from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.models.notifications import Notification
from app.models.user import User
from app.schemas.notification import NotificationOut

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
    notifications = (
        db.query(Notification)
        .filter(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .all()
    )
    return [NotificationOut.model_validate(n) for n in notifications]


@router.patch("/{notification_id}/read", response_model=NotificationOut)
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NotificationOut:
    """Mark one of the caller's own notifications as read.

    A notification belonging to someone else returns 404, not 403 --
    same "not yours and does not exist are indistinguishable" reasoning
    as the events endpoints.
    """
    notification = db.get(Notification, notification_id)
    if notification is None or notification.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

    notification.is_read = True
    db.commit()
    db.refresh(notification)
    return NotificationOut.model_validate(notification)
