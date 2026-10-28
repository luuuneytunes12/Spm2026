from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.core.db import get_db
from app.core.deps import get_current_user, require_role
from app.core.roles import Role
from app.models.clarifications import EventClarification
from app.models.enums import EventStatus
from app.models.events import Event
from app.models.user import User
from app.schemas.clarification import ClarificationIn, ClarificationOut, ClarificationReplyIn
from app.services import clarifications as service

router = APIRouter(prefix="/events", tags=["clarifications"])


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")


@router.post(
    "/{event_id}/clarifications",
    response_model=ClarificationOut,
    status_code=status.HTTP_201_CREATED,
)
def request_clarification(
    event_id: int,
    body: ClarificationIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.COORDINATOR)),
) -> ClarificationOut:
    """The assigned Coordinator asks the Organiser a question (Under Review only)."""
    event = db.get(Event, event_id, with_for_update=True)
    if event is None:
        raise _not_found()
    if event.coordinator_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assigned Event Coordinator may request clarification.",
        )
    if event.status != EventStatus.under_review:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Clarification can only be requested on an event Under Review.",
        )
    row = service.request_clarification(db, event, user, body.message)
    db.commit()
    return service.to_out(row)


@router.post(
    "/{event_id}/clarifications/reply",
    response_model=ClarificationOut,
    status_code=status.HTTP_201_CREATED,
)
def reply_to_clarification(
    event_id: int,
    body: ClarificationReplyIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.ORGANISER)),
) -> ClarificationOut:
    """The Event's Organiser answers (Awaiting Organiser Reply only); an
    event that is someone else's is indistinguishable from a missing one."""
    event = db.get(Event, event_id, with_for_update=True)
    if event is None or event.organiser_id != user.id:
        raise _not_found()
    if event.status != EventStatus.awaiting_organiser_reply:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This event is not awaiting your reply.",
        )
    row = service.reply_to_clarification(db, event, user, body.message, body.updates)
    db.commit()
    return service.to_out(row)


@router.get("/{event_id}/clarifications", response_model=list[ClarificationOut])
def list_clarifications(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ClarificationOut]:
    """The exchange, oldest first, for the Event's Organiser, its assigned
    Coordinator, or the Coordinator Lead."""
    event = db.get(Event, event_id)
    allowed = event is not None and (
        event.organiser_id == user.id
        or event.coordinator_id == user.id
        or user.role == Role.COORDINATOR_LEAD.value
    )
    if not allowed:
        raise _not_found()
    rows = (
        db.query(EventClarification)
        .options(joinedload(EventClarification.author))
        .filter(EventClarification.event_id == event_id)
        .order_by(EventClarification.created_at, EventClarification.id)
        .all()
    )
    return [service.to_out(r) for r in rows]
