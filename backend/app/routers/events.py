from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session, joinedload

from app.core.db import get_db
from app.core.deps import get_current_user, require_permission, require_role
from app.core.roles import Permission, Role
from app.models.enums import EventStatus, NotificationType
from app.models.events import Event, EventStatusHistory
from app.models.user import User
from app.services.equipment_lines import replace_equipment_lines
from app.schemas.event import (
    MANDATORY_FIELDS,
    ActivityEntry,
    AssignedEventDetail,
    EventIn,
    EventOut,
    EventSummary,
    OrganiserContact,
)
from app.services.assignment import ACTIVE_ASSIGNMENT_STATUSES, assign_coordinator, reassign_event
from app.services.notifications import notify

router = APIRouter(prefix="/events", tags=["events"])

REVIEWABLE_STATUSES = (EventStatus.submitted, EventStatus.under_review)


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


def _get_assigned_event(event_id: int, user: User, db: Session) -> Event:
    """Fetch an event ASSIGNED to the caller, or raise.

    "Assigned to me" means `coordinator_id == user.id`. Being allowed to
    read events in general is not the same thing: EVENT_READ is held by
    every role in the system, so the permission alone would let any signed-in
    user open any event.

    Like `_get_own_event`, a row belonging to someone else returns 404 rather
    than 403 -- "no such event" and "not assigned to you" are deliberately
    indistinguishable, so this endpoint cannot be used to probe which event
    ids exist or who is coordinating them.
    """
    event = db.get(Event, event_id)
    if event is None or event.coordinator_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event


def _get_reviewable_event(event_id: int, user: User, db: Session) -> Event:
    event = _get_assigned_event(event_id, user, db)
    if event.status not in REVIEWABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This request is already '{event.status}' and cannot be reviewed.",
        )
    return event


class RejectionRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Rejection reason cannot be blank")
        return value.strip()


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


def _event_activity(db: Session, event_id: int) -> list[ActivityEntry]:
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
            changed_by_name=entry.changed_by_user.name if entry.changed_by_user else None,
            created_at=entry.created_at,
        )
        for entry in history
    ]


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

    # Equipment lives in its own table, so it cannot ride along in the
    # Event(**data) splat -- pop it before that and write it through the
    # service once the event exists.
    data.pop("equipment_items", None)

    event = Event(**data, organiser_id=user.id, status=EventStatus.draft)
    db.add(event)

    if body.equipment_items:
        # flush, not commit: the lines need event.id, but a rejected line
        # must still roll the whole request back rather than leave an
        # event behind that the Organiser never got told about.
        db.flush()
        replace_equipment_lines(db, event, body.equipment_items)

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


@router.get("/assigned", response_model=list[EventSummary])
def list_assigned_events(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.EVENT_READ)),
) -> list[EventSummary]:
    """The events assigned to the caller as their Coordinator.

    Scoped by row rather than by role. EVENT_READ is held by every role, but
    only the user named in `coordinator_id` matches, so a caller who
    coordinates nothing gets an empty list -- which is the honest answer --
    rather than a 403.

    Declared before `/{event_id}` so that "assigned" is matched as this route
    and never captured as an event id.
    """
    events = (
        db.query(Event)
        .filter(Event.coordinator_id == user.id)
        .order_by(Event.updated_at.desc())
        .all()
    )
    return [EventSummary.model_validate(e) for e in events]


@router.get("/assigned/{event_id}", response_model=AssignedEventDetail)
def get_assigned_event(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.EVENT_READ)),
) -> AssignedEventDetail:
    """Full detail of one event assigned to the caller.

    Carries everything the Coordinator needs to plan it: the requirements
    the Organiser captured, who to contact about them, the current status,
    and every recorded status change.

    This is a separate route rather than a widening of `GET /events/{id}`.
    That one answers "my own request" for an Organiser and must keep
    returning 404 for anybody else's; this one answers "the request I am
    responsible for", and returns a different shape with it.
    """
    event = _get_assigned_event(event_id, user, db)

    return AssignedEventDetail(
        **EventOut.model_validate(event).model_dump(),
        organiser=OrganiserContact.model_validate(event.organiser),
        activity=_event_activity(db, event.id),
    )


@router.post("/assigned/{event_id}/release", response_model=EventOut)
def release_assigned_event(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.EVENT_WRITE)),
) -> EventOut:
    """Hand ONE event off to another available Coordinator.

    Distinct from PATCH /coordinators/me/availability, which takes the
    caller fully out of the pool and moves every active event they hold.
    This touches only `event_id` -- everything else assigned to the
    caller, and their general eligibility for new work, is untouched. For
    "I can't do this particular one" rather than "I'm away".

    404s for an event that is not assigned to the caller, exactly like
    GET /events/assigned/{id} -- same reasoning: "not yours" and "does not
    exist" should be indistinguishable.
    """
    event = _get_assigned_event(event_id, user, db)
    if event.status not in ACTIVE_ASSIGNMENT_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{event.status}' is not active, so it cannot be reassigned.",
        )

    # _get_assigned_event only needed user.id (present on the transient
    # JWT-claims object get_current_user returns); the real row -- with a
    # name -- is what reassign_event's log entry and notification need.
    outgoing = db.get(User, user.id)
    if outgoing is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

    reassign_event(db, event, outgoing=outgoing, reason="declined")

    db.commit()
    db.refresh(event)
    return EventOut.model_validate(event)


@router.post("/{event_id}/approve", response_model=EventOut)
def approve_event(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.COORDINATOR)),
) -> EventOut:
    """Approve a request assigned to the current Coordinator."""
    event = _get_reviewable_event(event_id, user, db)
    previous_status = event.status
    event.status = EventStatus.approved
    db.add(
        EventStatusHistory(
            event_id=event.id,
            changed_by=user.id,
            from_status=previous_status,
            to_status=event.status,
            note="Approved by the Event Coordinator.",
        )
    )
    notify(
        db,
        user_id=event.organiser_id,
        type=NotificationType.event_approved,
        message=f"Your event '{event.name or 'request'}' has been approved.",
        event_id=event.id,
    )
    db.commit()
    db.refresh(event)
    return EventOut.model_validate(event)


@router.post("/{event_id}/reject", response_model=EventOut)
def reject_event(
    event_id: int,
    body: RejectionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.COORDINATOR)),
) -> EventOut:
    """Reject an assigned request and retain the Coordinator's reason."""
    event = _get_reviewable_event(event_id, user, db)
    previous_status = event.status
    event.status = EventStatus.rejected
    db.add(
        EventStatusHistory(
            event_id=event.id,
            changed_by=user.id,
            from_status=previous_status,
            to_status=event.status,
            note=body.reason,
        )
    )
    notify(
        db,
        user_id=event.organiser_id,
        type=NotificationType.event_rejected,
        message=f"Your event '{event.name or 'request'}' was rejected: {body.reason}",
        event_id=event.id,
    )
    db.commit()
    db.refresh(event)
    return EventOut.model_validate(event)


@router.get("/{event_id}", response_model=EventOut)
def get_event(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.EVENT_READ)),
) -> EventOut:
    """Reopen one request, with every previously entered value intact."""
    return EventOut.model_validate(_get_own_event(event_id, user, db))


@router.get("/{event_id}/activity", response_model=list[ActivityEntry])
def get_own_event_activity(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.EVENT_READ)),
) -> list[ActivityEntry]:
    """The signed-in Organiser's own event history, newest first."""
    event = _get_own_event(event_id, user, db)
    return _event_activity(db, event.id)


@router.patch("/{event_id}", response_model=EventOut)
def update_event(
    event_id: int,
    body: EventIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.EVENT_WRITE)),
) -> EventOut:
    """Edit a draft or correct a request before the Coordinator decides.

    Submitted and under-review requests remain editable until approval or
    rejection. A same-status history entry makes each correction visible
    to the assigned Coordinator.
    """
    event = _get_own_event(event_id, user, db)
    if event.status not in (EventStatus.draft, *REVIEWABLE_STATUSES):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This request can no longer be edited; it is '{event.status}'.",
        )

    # exclude_unset so a PATCH that omits a field leaves it alone, rather
    # than nulling it out. Sending an explicit null still clears it.
    changes = body.model_dump(exclude_unset=True)

    # Same rule, applied to the child rows: omitted means "leave them
    # alone", an explicit [] clears them, and a list replaces them. It has
    # to be handled before the loop because setattr would put raw dicts
    # into the relationship.
    if "equipment_items" in changes:
        changes.pop("equipment_items")
        replace_equipment_lines(db, event, body.equipment_items or [])

    for field, value in changes.items():
        if field == "registration_enabled" and value is None:
            continue  # non-null column; ignore an explicit null
        setattr(event, field, value)

    if event.status in REVIEWABLE_STATUSES:
        db.add(
            EventStatusHistory(
                event_id=event.id,
                changed_by=user.id,
                from_status=event.status,
                to_status=event.status,
                note="Updated by the Organiser before review was decided.",
            )
        )

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

    # AC1 of "Mark myself unavailable": a submitted request is handed to an
    # available Coordinator automatically. Left unassigned (silently) if
    # nobody is available right now -- see assign_coordinator.
    assign_coordinator(db, event, actor_id=user.id)

    db.commit()
    db.refresh(event)
    return EventOut.model_validate(event)
