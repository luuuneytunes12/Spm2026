"""Read the shared, append-only Activity Log for an Event."""

from sqlalchemy.orm import Session, joinedload

from app.models.events import EventStatusHistory
from app.schemas.event import ActivityEntry


def event_activity(db: Session, event_id: int) -> list[ActivityEntry]:
    history = (
        db.query(EventStatusHistory)
        .options(joinedload(EventStatusHistory.changed_by_user))
        .filter(EventStatusHistory.event_id == event_id)
        .order_by(EventStatusHistory.created_at.desc(), EventStatusHistory.id.desc())
        .all()
    )
    return [
        ActivityEntry(
            from_status=entry.from_status,
            to_status=entry.to_status,
            note=entry.note,
            changed_by_name=entry.actor_name
            or (entry.changed_by_user.name if entry.changed_by_user else None),
            created_at=entry.created_at,
        )
        for entry in history
    ]
