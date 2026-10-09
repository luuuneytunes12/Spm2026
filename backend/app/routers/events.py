from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, joinedload

from app.core.db import get_db
from app.core.deps import get_current_user, require_permission, require_role
from app.core.roles import Permission, Role
from app.models.enums import (
    CHANGE_REQUEST_ALLOWED_STATUSES,
    BookingStatus,
    ChangeRequestStatus,
    EquipmentStatus,
    EventStatus,
    NotificationType,
    PLANNING_STATUSES,
)
from app.models.equipment import Equipment, EquipmentRequest
from app.models.events import Event, EventChangeRequest, EventStatusHistory
from app.models.notifications import Notification
from app.models.user import User
from app.models.venues import VenueBooking
from app.domain.event_readiness import can_enter_preparation, outstanding_arrangements
from app.services.equipment_lines import replace_equipment_lines
from app.schemas.event import (
    MANDATORY_FIELDS,
    ActivityEntry,
    AssignedEventDetail,
    EventChangeDecisionIn,
    EventChangeRequestIn,
    EventChangeRequestOut,
    EquipmentLineIn,
    EventIn,
    EventOut,
    EventSummary,
    OrganiserContact,
    RegistrationSettingsIn,
)
from app.services.notifications import notify
from app.services.submission_notice import SubmissionNotice

router = APIRouter(prefix="/events", tags=["events"])

REVIEWABLE_STATUSES = (EventStatus.submitted_awaiting_coordinator,)
IMPORTANT_CHANGE_FIELDS = {
    "proposed_start",
    "proposed_end",
    "expected_attendance",
    "venue_requirements",
    "room_layout_preference",
    "accessibility_needs",
    "equipment_requirements",
    "equipment_items",
}


def _get_own_event(
    event_id: int, user: User, db: Session, *, lock: bool = False
) -> Event:
    """Fetch an event the caller owns, or raise.

    `lock=True` takes a row lock (SELECT ... FOR UPDATE) for the rest of the
    transaction. Use it wherever the handler goes on to check the event's
    state and then change it: without the lock two overlapping requests --
    a double-clicked button -- both read the SAME state and both act on it.
    The second then waits, and reads what the first left behind. (SQLite,
    which the unit tests use, ignores the lock; the Postgres integration
    tests are what prove it.)

    Ownership is checked here rather than relying on the permission alone:
    EVENT_WRITE is granted to Coordinators as well as Organisers, so a
    permission check by itself would let one user open another's drafts.

    A row owned by someone else returns 404, not 403 -- "no such event" and
    "not yours" are deliberately indistinguishable, so this endpoint cannot
    be used to probe which event ids exist.
    """
    event = db.get(Event, event_id, with_for_update=lock)
    if event is None or event.organiser_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Event not found"
        )
    return event


def _get_assigned_event(
    event_id: int, user: User, db: Session, *, lock: bool = False
) -> Event:
    """Fetch an event ASSIGNED to the caller, or raise.

    `lock=True` locks the row -- see `_get_own_event`. A caller that goes on
    to check the event's state and then change it needs it, so two overlapping
    requests cannot both act on the same state.

    "Assigned to me" means `coordinator_id == user.id`. Being allowed to
    read events in general is not the same thing: EVENT_READ is held by
    every role in the system, so the permission alone would let any signed-in
    user open any event.

    Like `_get_own_event`, a row belonging to someone else returns 404 rather
    than 403 -- "no such event" and "not assigned to you" are deliberately
    indistinguishable, so this endpoint cannot be used to probe which event
    ids exist or who is coordinating them.
    """
    event = db.get(Event, event_id, with_for_update=lock)
    if event is None or event.coordinator_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Event not found"
        )
    return event


def _was_reassigned_from(db: Session, event: Event, user: User) -> bool:
    """True if the Lead moved `event` away from `user` (they were told so)."""
    return (
        db.scalar(
            select(Notification.id)
            .where(
                Notification.user_id == user.id,
                Notification.event_id == event.id,
                Notification.type == NotificationType.event_reassigned_away,
            )
            .limit(1)
        )
        is not None
    )


def _get_reviewable_event(event_id: int, user: User, db: Session) -> Event:
    event = _get_assigned_event(event_id, user, db)
    if event.status not in REVIEWABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This request is already '{event.status}' and cannot be reviewed.",
        )
    pending_change = (
        db.query(EventChangeRequest)
        .filter(
            EventChangeRequest.event_id == event.id,
            EventChangeRequest.status == ChangeRequestStatus.pending,
        )
        .first()
    )
    if pending_change is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Resolve the pending change request before deciding this event.",
        )
    return event


def _utc(value: datetime) -> datetime:
    """Treat a naive datetime as UTC. SQLite (the test DB) hands back naive
    values; Postgres timestamptz hands back aware ones."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


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
            changed_by_name=entry.changed_by_user.name
            if entry.changed_by_user
            else None,
            created_at=entry.created_at,
        )
        for entry in history
    ]


def _change_request_out(
    db: Session, request: EventChangeRequest
) -> EventChangeRequestOut:
    changes = dict(request.proposed_changes or {})
    proposed_equipment = changes.get("equipment_items")
    if proposed_equipment:
        equipment_ids = {line["equipment_id"] for line in proposed_equipment}
        equipment_names = dict(
            db.query(Equipment.id, Equipment.name)
            .filter(Equipment.id.in_(equipment_ids))
            .all()
        )
        changes["equipment_items"] = [
            {
                **line,
                "equipment_name": equipment_names.get(
                    line["equipment_id"], f"Equipment #{line['equipment_id']}"
                ),
            }
            for line in proposed_equipment
        ]
    important = bool(IMPORTANT_CHANGE_FIELDS.intersection(changes))
    bookings = []
    reserved_equipment = []
    if important:
        bookings = (
            db.query(VenueBooking)
            .options(joinedload(VenueBooking.venue))
            .filter(
                VenueBooking.event_id == request.event_id,
                or_(
                    VenueBooking.status.in_(
                        (BookingStatus.pending, BookingStatus.approved)
                    ),
                    and_(
                        VenueBooking.status == BookingStatus.tentative_hold,
                        VenueBooking.expires_at > datetime.now(timezone.utc),
                    ),
                ),
            )
            .order_by(VenueBooking.id)
            .all()
        )
        reserved_equipment = (
            db.query(EquipmentRequest)
            .filter(
                EquipmentRequest.event_id == request.event_id,
                EquipmentRequest.status == EquipmentStatus.reserved,
            )
            .order_by(EquipmentRequest.id)
            .all()
        )
    return EventChangeRequestOut(
        id=request.id,
        event_id=request.event_id,
        requested_by=request.requested_by,
        description=request.description,
        proposed_changes=changes,
        status=request.status,
        review_notes=request.review_notes,
        created_at=request.created_at,
        reviewed_at=request.reviewed_at,
        important_change=important,
        safety_check_required=(
            "expected_attendance" in changes
            and request.event.status
            in (
                EventStatus.event_approved,
                EventStatus.planning_event,
                EventStatus.awaiting_safety_check,
                EventStatus.safety_check_passed,
            )
        ),
        venue_bookings_to_reconsider=[
            {
                "id": booking.id,
                "venue_name": booking.venue.name,
                "start_time": booking.start_time,
                "end_time": booking.end_time,
                "status": booking.status,
            }
            for booking in bookings
        ],
        equipment_reservations_to_reconsider=[
            {
                "id": line.id,
                "equipment_name": line.equipment.name,
                "quantity_requested": line.quantity_requested,
                "status": line.status,
            }
            for line in reserved_equipment
        ],
    )


def _get_change_request_for_coordinator(
    request_id: int, user: User, db: Session
) -> tuple[EventChangeRequest, Event]:
    change_request = db.get(EventChangeRequest, request_id)
    if change_request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Change request not found"
        )
    event = db.get(Event, change_request.event_id, with_for_update=True)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    if event.coordinator_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assigned Event Coordinator may review this change request.",
        )
    if change_request.status != ChangeRequestStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Change request is no longer pending.",
        )
    if event.status not in CHANGE_REQUEST_ALLOWED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This event can no longer be changed.",
        )
    return change_request, event


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
    ?status=draft or ?status=submitted_awaiting_coordinator.
    """
    query = db.query(Event).filter(Event.organiser_id == user.id)
    if status_filter is not None:
        query = query.filter(Event.status == status_filter)
    events = query.order_by(Event.updated_at.desc()).all()
    event_ids = [event.id for event in events]
    pending_event_ids = set()
    if event_ids:
        pending_event_ids = {
            event_id
            for (event_id,) in db.query(EventChangeRequest.event_id)
            .filter(
                EventChangeRequest.event_id.in_(event_ids),
                EventChangeRequest.status == ChangeRequestStatus.pending,
            )
            .distinct()
            .all()
        }
    return [
        EventSummary.model_validate(event).model_copy(
            update={"has_pending_change_request": event.id in pending_event_ids}
        )
        for event in events
    ]


@router.get("/queue", response_model=list[EventSummary])
def review_queue(
    db: Session = Depends(get_db),
    user: User = Depends(
        require_permission(Permission.EVENT_READ, Permission.EVENT_WRITE)
    ),
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
        .filter(Event.status == EventStatus.submitted_awaiting_coordinator)
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
    event_ids = [event.id for event in events]
    pending_event_ids = set()
    if event_ids:
        pending_event_ids = {
            event_id
            for (event_id,) in db.query(EventChangeRequest.event_id)
            .filter(
                EventChangeRequest.event_id.in_(event_ids),
                EventChangeRequest.status == ChangeRequestStatus.pending,
            )
            .distinct()
            .all()
        }
    return [
        EventSummary.model_validate(event).model_copy(
            update={"has_pending_change_request": event.id in pending_event_ids}
        )
        for event in events
    ]


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
    event = db.get(Event, event_id)
    if (
        event is not None
        and event.coordinator_id not in (None, user.id)
        and _was_reassigned_from(db, event, user)
    ):
        # Only the Coordinator the Lead took it from learns who has it now;
        # everyone else still gets the indistinguishable 404 below.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"'{event.name or 'This event'}' that was initially assigned to you by the "
                f"Event Coordinator Lead has been reassigned to {event.coordinator.name}."
            ),
        )
    event = _get_assigned_event(event_id, user, db)

    return AssignedEventDetail(
        **EventOut.model_validate(event).model_dump(),
        organiser=OrganiserContact.model_validate(event.organiser),
        activity=_event_activity(db, event.id),
        confirmation_outstanding=(
            outstanding_arrangements(db, event)
            if event.status in PLANNING_STATUSES
            else []
        ),
        change_requests=[
            _change_request_out(db, request)
            for request in db.query(EventChangeRequest)
            .filter(EventChangeRequest.event_id == event.id)
            .order_by(
                EventChangeRequest.created_at.desc(), EventChangeRequest.id.desc()
            )
            .all()
        ],
    )


@router.post(
    "/{event_id}/change-requests",
    response_model=EventChangeRequestOut,
    status_code=status.HTTP_201_CREATED,
)
def request_event_changes(
    event_id: int,
    body: EventChangeRequestIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.EVENT_WRITE)),
) -> EventChangeRequestOut:
    event = _get_own_event(event_id, user, db)
    if event.status not in CHANGE_REQUEST_ALLOWED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This event can no longer be changed.",
        )
    pending = (
        db.query(EventChangeRequest)
        .filter(
            EventChangeRequest.event_id == event.id,
            EventChangeRequest.status == ChangeRequestStatus.pending,
        )
        .first()
    )
    if pending is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A change request is already pending.",
        )

    proposed = body.proposed_changes
    proposed_start = (
        proposed.proposed_start
        if "proposed_start" in proposed.model_fields_set
        else event.proposed_start
    )
    proposed_end = (
        proposed.proposed_end
        if "proposed_end" in proposed.model_fields_set
        else event.proposed_end
    )
    start_for_comparison = (
        proposed_start.replace(tzinfo=timezone.utc)
        if proposed_start is not None and proposed_start.tzinfo is None
        else proposed_start
    )
    end_for_comparison = (
        proposed_end.replace(tzinfo=timezone.utc)
        if proposed_end is not None and proposed_end.tzinfo is None
        else proposed_end
    )
    if (
        start_for_comparison is not None
        and end_for_comparison is not None
        and end_for_comparison <= start_for_comparison
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The proposed event end must be after its proposed start.",
        )

    change_request = EventChangeRequest(
        event_id=event.id,
        requested_by=user.id,
        description=body.description.strip(),
        proposed_changes=body.proposed_changes.model_dump(
            mode="json", exclude_unset=True
        ),
    )
    db.add(change_request)
    db.flush()
    db.commit()
    db.refresh(change_request)
    return _change_request_out(db, change_request)


@router.get("/{event_id}/change-requests", response_model=list[EventChangeRequestOut])
def list_own_change_requests(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.EVENT_READ)),
) -> list[EventChangeRequestOut]:
    event = _get_own_event(event_id, user, db)
    requests = (
        db.query(EventChangeRequest)
        .filter(EventChangeRequest.event_id == event.id)
        .order_by(EventChangeRequest.created_at.desc(), EventChangeRequest.id.desc())
        .all()
    )
    return [_change_request_out(db, request) for request in requests]


@router.post(
    "/change-requests/{request_id}/approve", response_model=EventChangeRequestOut
)
def approve_change_request(
    request_id: int,
    body: EventChangeDecisionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.COORDINATOR)),
) -> EventChangeRequestOut:
    change_request, event = _get_change_request_for_coordinator(request_id, user, db)
    changes = dict(change_request.proposed_changes or {})
    equipment_items = changes.pop("equipment_items", None)
    if equipment_items is not None:
        replace_equipment_lines(
            db,
            event,
            [EquipmentLineIn.model_validate(line) for line in equipment_items],
        )
    for field, value in changes.items():
        setattr(event, field, value)

    attendance_changed_after_approval = (
        "expected_attendance" in (change_request.proposed_changes or {})
        and event.status
        in (
            EventStatus.event_approved,
            EventStatus.planning_event,
            EventStatus.awaiting_safety_check,
            EventStatus.safety_check_passed,
        )
    )
    if attendance_changed_after_approval:
        previous_status = event.status
        event.status = EventStatus.planning_event
        db.add(
            EventStatusHistory(
                event_id=event.id,
                changed_by=user.id,
                from_status=previous_status,
                to_status=event.status,
                note="Attendance changed; a new safety check is required.",
            )
        )

    change_request.status = ChangeRequestStatus.approved
    change_request.reviewed_by = user.id
    change_request.reviewed_at = datetime.now(timezone.utc)
    change_request.review_notes = (
        body.review_notes.strip() if body.review_notes else None
    )
    db.add(
        Notification(
            user_id=event.organiser_id,
            event_id=event.id,
            type="event_change_approved",
            message=f"Your requested changes for '{event.name or 'your event'}' were approved.",
        )
    )
    if attendance_changed_after_approval:
        notify(
            db,
            user_id=user.id,
            type=NotificationType.safety_changes_requested,
            message=(
                f"Attendance for '{event.name or 'Event'}' changed. "
                "Review venue capacity and submit it for a new safety check."
            ),
            event_id=event.id,
        )
    db.commit()
    db.refresh(change_request)
    return _change_request_out(db, change_request)


@router.post(
    "/change-requests/{request_id}/reject", response_model=EventChangeRequestOut
)
def reject_change_request(
    request_id: int,
    body: EventChangeDecisionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.COORDINATOR)),
) -> EventChangeRequestOut:
    change_request, event = _get_change_request_for_coordinator(request_id, user, db)
    change_request.status = ChangeRequestStatus.rejected
    change_request.reviewed_by = user.id
    change_request.reviewed_at = datetime.now(timezone.utc)
    change_request.review_notes = (
        body.review_notes.strip() if body.review_notes else None
    )
    db.add(
        Notification(
            user_id=event.organiser_id,
            event_id=event.id,
            type="event_change_rejected",
            message=(
                f"Your requested changes for '{event.name or 'your event'}' were rejected."
                + (
                    f" Reason: {change_request.review_notes}"
                    if change_request.review_notes
                    else ""
                )
            ),
        )
    )
    db.commit()
    db.refresh(change_request)
    return _change_request_out(db, change_request)


@router.post("/{event_id}/confirm", response_model=EventOut)
def submit_for_safety_check(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.COORDINATOR)),
) -> EventOut:
    """Send a planned event to the Safety Officer once its venue and
    equipment are arranged.

    Blocked -- with the outstanding items named -- while the venue booking
    is not approved, any equipment line is not reserved, or anything is
    still flagged for safety re-review. The event is confirmed only when a
    Safety Officer passes it (routers/safety_checks.py).
    """
    # Locked: two overlapping confirms must not both see "approved" and both
    # log a transition and notify the Organiser.
    event = _get_assigned_event(event_id, user, db, lock=True)
    if event.status not in PLANNING_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Only an event in planning can be sent for a safety check; this one is '{event.status}'.",
        )

    outstanding = outstanding_arrangements(db, event)
    if outstanding:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot submit yet. Outstanding: " + "; ".join(outstanding) + ".",
        )

    previous_status = event.status
    event.status = EventStatus.awaiting_safety_check
    db.add(
        EventStatusHistory(
            event_id=event.id,
            changed_by=user.id,
            from_status=previous_status,
            to_status=event.status,
            note="Submitted for safety check by the Event Coordinator.",
        )
    )
    db.commit()
    db.refresh(event)
    return EventOut.model_validate(event)


@router.put("/assigned/{event_id}/registration", response_model=EventOut)
def set_event_registration(
    event_id: int,
    body: RegistrationSettingsIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.COORDINATOR)),
) -> EventOut:
    """Open or close registration on a confirmed event, and set its dates.

    Enabling needs a confirmed event ('Safety Check Passed (Event Confirmed)')
    whose venue and equipment are still arranged, and both an open and a
    close date. The close must not be before the open, nor after the event
    starts. Each offending field is reported the way the submit endpoint
    reports missing ones, so the form can flag it. Switching registration off
    is always allowed.
    """
    event = _get_assigned_event(event_id, user, db, lock=True)

    if body.registration_enabled:
        if event.status != EventStatus.safety_check_passed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Registration cannot be opened yet: the Safety Officer must approve this "
                    f"event first. It is '{event.status}'."
                ),
            )
        outstanding = outstanding_arrangements(db, event)
        if outstanding:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Registration cannot be opened. Outstanding: " + "; ".join(outstanding) + ".",
            )
        problems = []
        if body.registration_opens_at is None:
            problems.append(("registration_opens_at", "Registration open date is required."))
        if body.registration_closes_at is None:
            problems.append(("registration_closes_at", "Registration close date is required."))
        if (
            body.registration_opens_at is not None
            and body.registration_closes_at is not None
            and _utc(body.registration_closes_at) < _utc(body.registration_opens_at)
        ):
            # Two sentences, one per field: shown together they read as
            # "what is wrong. what to do about it."
            problems.append(
                ("registration_opens_at", "Registration cannot close before it opens."),
            )
            problems.append(
                (
                    "registration_closes_at",
                    "Ensure the registration close date is later than the open date.",
                ),
            )
        if (
            body.registration_closes_at is not None
            and event.proposed_start is not None
            and _utc(body.registration_closes_at) > _utc(event.proposed_start)
        ):
            problems.append(
                (
                    "registration_closes_at",
                    "Registration cannot close after the event starts. Choose a close date "
                    "on or before the event's start.",
                ),
            )
        if problems:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=[{"loc": ["body", field], "msg": msg} for field, msg in problems],
            )
        event.registration_opens_at = body.registration_opens_at
        event.registration_closes_at = body.registration_closes_at

    event.registration_enabled = body.registration_enabled
    db.commit()
    db.refresh(event)
    return EventOut.model_validate(event)


@router.post("/{event_id}/approve", response_model=EventOut)
def approve_event(
    event_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.COORDINATOR)),
) -> EventOut:
    """Approve an assigned Submitted request; Leads only assign.

    TODO(confirm): Coordinator Leads remain view-only for this decision.
    """
    event = db.get(Event, event_id, with_for_update=True)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    if event.coordinator_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An event must be assigned to a Coordinator before it can be approved.",
        )
    if event.coordinator_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assigned Event Coordinator may approve this event.",
        )
    if event.status != EventStatus.submitted_awaiting_coordinator:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only a Submitted event can be approved.",
        )
    pending_change = (
        db.query(EventChangeRequest)
        .filter(
            EventChangeRequest.event_id == event.id,
            EventChangeRequest.status == ChangeRequestStatus.pending,
        )
        .first()
    )
    if pending_change:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Resolve the pending change request before deciding this event.",
        )
    previous_status = event.status
    event.status = EventStatus.event_approved
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
    """Reject an assigned request and retain the Coordinator's reason.

    TODO(confirm): Coordinator Leads remain view-only for this decision.
    """
    event = db.get(Event, event_id, with_for_update=True)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    if event.coordinator_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An event must be assigned to a Coordinator before it can be rejected.",
        )
    if event.coordinator_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assigned Event Coordinator may reject this event.",
        )
    if event.status != EventStatus.submitted_awaiting_coordinator:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only a Submitted event can be rejected.",
        )
    previous_status = event.status
    event.status = EventStatus.event_rejected
    # TODO(confirm): Rejection releases all live venue bookings and tentative holds.
    live_bookings = (
        db.query(VenueBooking)
        .filter(
            VenueBooking.event_id == event.id,
            VenueBooking.status.in_(
                (
                    BookingStatus.pending,
                    BookingStatus.tentative_hold,
                    BookingStatus.approved,
                )
            ),
        )
        .all()
    )
    for booking in live_bookings:
        booking.status = BookingStatus.cancelled
        booking.expires_at = None
        booking.decision_notes = f"Released because the event was rejected: {body.reason}"
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
    """Edit a draft. Submitted requests use POST /change-requests instead."""
    event = _get_own_event(event_id, user, db)
    if event.status != EventStatus.draft:
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

    db.commit()
    db.refresh(event)
    return EventOut.model_validate(event)


def _after_submit(db: Session, event: Event, user: User) -> None:
    """Runs inside the submit transaction, after the status change is logged.

    Deliberately does nothing: a submitted request is NOT auto-assigned. It
    waits in the Event Coordinator Lead's Unassigned Queue as "submitted_awaiting_coordinator"
    with no Coordinator, and only the Lead assigns one (see
    app/services/assignment_overview.py). Older coordinator-workflow tests
    swap this for `assign_coordinator` -- see `coordinator_auto_assign` in
    tests/conftest.py -- because they need an already-assigned event.
    """


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
    # Locked: two overlapping submits must not both see a draft and both go
    # on to assign a Coordinator and notify everyone.
    event = _get_own_event(event_id, user, db, lock=True)

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
                {
                    "loc": ["body", field],
                    "msg": f"{label} is required before submitting.",
                }
                for field, label in missing
            ],
        )

    previous = event.status
    event.status = EventStatus.submitted_awaiting_coordinator
    event.submitted_at = datetime.now(timezone.utc)

    # Record the transition. Cheap to do now, and it is what makes "who
    # changed this, and when?" answerable later -- the briefing asks for
    # exactly that under Activity History.
    db.add(
        EventStatusHistory(
            event_id=event.id,
            changed_by=user.id,
            from_status=previous,
            to_status=EventStatus.submitted_awaiting_coordinator,
            note="Submitted by organiser.",
        )
    )

    _after_submit(db, event, user)
    # Outside _after_submit on purpose: tests swap that hook out, and the Lead
    # must be told whatever it does.
    SubmissionNotice().send(db, event)

    db.commit()
    db.refresh(event)
    return EventOut.model_validate(event)
