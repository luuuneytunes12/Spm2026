from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_permission
from app.core.roles import Permission
from app.models.enums import EventStatus
from app.models.events import Event, EventStatusHistory
from app.models.user import User
from app.schemas.event import MANDATORY_FIELDS, EventIn, EventOut, EventSummary

router = APIRouter(prefix="/events", tags=["events"])


def _get_own_event(event_id: int, user: User, db: Session) -> Event:
    """Fetch an event the caller owns, or raise.

    Ownership is checked here rather than relying on the permission alone:
    EVENT_WRITE is granted to Coordinators as well as Organisers, so a
    permission check by itself would let one user open another's drafts.

    A row owned by someone else returns 404, not 403 -- "no such event" and
    "not yours" are deliberately indistinguishable, so this endpoint cannot
    be used to probe which event ids exist.
    """
    event = db.get(Event, event_id)
    if event is None or event.organiser_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event


def _missing_mandatory(event: Event) -> list[tuple[str, str]]:
    """Return the (field, label) pairs still empty on `event`.

    Blank/whitespace-only strings count as missing: a text input that was
    focused and left empty submits "" rather than null, and the user would
    not call that "filled in".
    """
    missing: list[tuple[str, str]] = []
    for field, label in MANDATORY_FIELDS:
        value = getattr(event, field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append((field, label))
    return missing


@router.post("", response_model=EventOut, status_code=status.HTTP_201_CREATED)
def create_event(
    body: EventIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.EVENT_WRITE)),
) -> EventOut:
    """Create a new event request as a DRAFT.

    Always starts at `draft` regardless of what the client sends -- there
    is no way to create something already submitted, so the submit
    endpoint stays the single place where that transition (and its
    validation) happens.
    """
    data = body.model_dump(exclude_unset=True)
    # A brand-new draft needs a concrete value for the non-null column.
    data.setdefault("registration_enabled", False)
    if data.get("registration_enabled") is None:
        data["registration_enabled"] = False

    event = Event(**data, organiser_id=user.id, status=EventStatus.draft)
    db.add(event)
    db.commit()
    db.refresh(event)
    return EventOut.model_validate(event)


@router.get("", response_model=list[EventSummary])
def list_my_events(
    status_filter: EventStatus | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.EVENT_READ)),
) -> list[EventSummary]:
    """List the caller's OWN event requests, newest first.

    Scoped to `organiser_id == user.id`, which is what backs both the
    "Drafts" and "Submitted Requests" tabs -- the caller passes
    ?status=draft or ?status=submitted.
    """
    query = db.query(Event).filter(Event.organiser_id == user.id)
    if status_filter is not None:
        query = query.filter(Event.status == status_filter)
    events = query.order_by(Event.updated_at.desc()).all()
    return [EventSummary.model_validate(e) for e in events]


@router.get("/queue", response_model=list[EventSummary])
def review_queue(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.EVENT_READ, Permission.EVENT_WRITE)),
) -> list[EventSummary]:
    """The reviewer-facing queue of SUBMITTED requests.

    Deliberately minimal -- the Event Coordinator's review story will own
    and extend this. It exists now because the draft story's acceptance
    criteria require that a draft *not* appear here, and that is only
    demonstrable if the queue exists.

    The status filter is hardcoded, not a parameter: no caller should ever
    be able to widen this to include drafts.
    """
    events = (
        db.query(Event)
        .filter(Event.status == EventStatus.submitted)
        .order_by(Event.submitted_at.desc())
        .all()
    )
    return [EventSummary.model_validate(e) for e in events]


@router.get("/{event_id}", response_model=EventOut)
def get_event(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.EVENT_READ)),
) -> EventOut:
    """Reopen one request, with every previously entered value intact."""
    return EventOut.model_validate(_get_own_event(event_id, user, db))


@router.patch("/{event_id}", response_model=EventOut)
def update_event(
    event_id: int,
    body: EventIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.EVENT_WRITE)),
) -> EventOut:
    """Continue editing a draft.

    Only drafts are editable through this route. Once submitted, an event
    is under ConnectSphere's control and further changes go through the
    change-request process (a separate story) -- otherwise an Organiser
    could silently move the date out from under a Coordinator who is
    already reviewing it.
    """
    event = _get_own_event(event_id, user, db)
    if event.status != EventStatus.draft:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Only a draft can be edited; this request is '{event.status}'.",
        )

    # exclude_unset so a PATCH that omits a field leaves it alone, rather
    # than nulling it out. Sending an explicit null still clears it.
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "registration_enabled" and value is None:
            continue  # non-null column; ignore an explicit null
        setattr(event, field, value)

    db.commit()
    db.refresh(event)
    return EventOut.model_validate(event)


@router.post("/{event_id}/submit", response_model=EventOut)
def submit_event(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.EVENT_WRITE)),
) -> EventOut:
    """Submit a completed request for review.

    Blocks submission when mandatory fields are empty and reports WHICH
    ones, so the form can flag each field rather than showing a single
    generic error. The `loc` shape matches FastAPI's own 422 body, so the
    frontend parses server-side and client-side validation errors with the
    same code path.
    """
    event = _get_own_event(event_id, user, db)

    if event.status != EventStatus.draft:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Only a draft can be submitted; this request is already '{event.status}'.",
        )

    missing = _missing_mandatory(event)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[
                {"loc": ["body", field], "msg": f"{label} is required before submitting."}
                for field, label in missing
            ],
        )

    previous = event.status
    event.status = EventStatus.submitted
    event.submitted_at = datetime.now(timezone.utc)

    # Record the transition. Cheap to do now, and it is what makes "who
    # changed this, and when?" answerable later -- the briefing asks for
    # exactly that under Activity History.
    db.add(
        EventStatusHistory(
            event_id=event.id,
            changed_by=user.id,
            from_status=previous,
            to_status=EventStatus.submitted,
            note="Submitted by organiser.",
        )
    )

    db.commit()
    db.refresh(event)
    return EventOut.model_validate(event)
