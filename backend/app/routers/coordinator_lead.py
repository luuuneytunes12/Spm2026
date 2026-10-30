from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_role
from app.core.roles import Role
from app.models.enums import ChangeRequestStatus
from app.models.events import EventChangeRequest
from app.models.user import User
from app.schemas.event import (
    LeadAssignIn,
    LeadChangeRequestOut,
    LeadCoordinatorOut,
    LeadEventDetail,
    LeadEventOut,
)
from app.services.event_activity import event_activity
from app.services.lead_assignment import AssignEvent, AssignmentRefused, ReassignEvent
from app.services.assignment_overview import (
    ActiveAssignments,
    CoordinatorWorkload,
    UnassignedQueue,
    UnassignedRequests,
)

router = APIRouter(prefix="/lead", tags=["coordinator-lead"])

# Identity-based, like the other role-specific routers: only the Lead.
_lead = require_role(Role.COORDINATOR_LEAD)


def _lead_event_outs(db: Session, events) -> list[LeadEventOut]:
    events = list(events)
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
        LeadEventOut.model_validate(event).model_copy(
            update={"has_pending_change_request": event.id in pending_event_ids}
        )
        for event in events
    ]


def _event_change_requests(db: Session, event_id: int) -> list[LeadChangeRequestOut]:
    requests = (
        db.query(EventChangeRequest)
        .filter(EventChangeRequest.event_id == event_id)
        .order_by(EventChangeRequest.created_at.desc(), EventChangeRequest.id.desc())
        .all()
    )
    return [
        LeadChangeRequestOut(
            id=request.id,
            description=request.description,
            proposed_changes=request.proposed_changes or {},
            status=request.status,
            created_at=request.created_at,
        )
        for request in requests
    ]


@router.get("/unassigned-requests", response_model=list[LeadEventOut])
def list_unassigned_requests(
    db: Session = Depends(get_db),
    _lead_user: User = Depends(_lead),
) -> list[LeadEventOut]:
    """Active Event Requests that have no Coordinator yet. Its length is the
    number shown on the Lead's landing-page shortcut."""
    return _lead_event_outs(db, UnassignedRequests().rows(db))


@router.get("/assignments", response_model=list[LeadEventOut])
def list_coordinator_assignments(
    coordinator_id: int | None = None,
    db: Session = Depends(get_db),
    _lead_user: User = Depends(_lead),
) -> list[LeadEventOut]:
    """Every active Event that has a Coordinator, with who it is. With
    `coordinator_id`, only that Coordinator's; the number of Events is the
    length of the list."""
    return _lead_event_outs(db, ActiveAssignments(coordinator_id).rows(db))


@router.get("/assignments/{event_id}", response_model=LeadEventDetail)
def get_assigned_event(
    event_id: int,
    db: Session = Depends(get_db),
    _lead_user: User = Depends(_lead),
) -> LeadEventDetail:
    """One active Event in full, for review. Read-only. 404 for anything
    that is not an active assignment (unassigned, finished, or unknown)."""
    event = ActiveAssignments().find(db, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found in the assignments")
    return LeadEventDetail.model_validate(event).model_copy(
        update={
            "activity": event_activity(db, event.id),
            "change_requests": _event_change_requests(db, event.id),
        }
    )


@router.get("/coordinators", response_model=list[LeadCoordinatorOut])
def list_coordinator_workload(
    db: Session = Depends(get_db),
    _lead_user: User = Depends(_lead),
) -> list[LeadCoordinatorOut]:
    """Every Coordinator and their number of active Events."""
    return [LeadCoordinatorOut(**vars(row)) for row in CoordinatorWorkload().rows(db)]


@router.get("/unassigned-queue", response_model=list[LeadEventOut])
def list_unassigned_queue(
    db: Session = Depends(get_db),
    _lead_user: User = Depends(_lead),
) -> list[LeadEventOut]:
    """The Unassigned Queue: submitted requests awaiting a Coordinator,
    oldest first. Drafts and already-assigned requests are not listed."""
    return _lead_event_outs(db, UnassignedQueue().rows(db))


@router.get("/unassigned-queue/{event_id}", response_model=LeadEventDetail)
def get_queued_request(
    event_id: int,
    db: Session = Depends(get_db),
    _lead_user: User = Depends(_lead),
) -> LeadEventDetail:
    """One queued request in full, for review. Read-only. 404 for anything
    not in the queue (a draft, an assigned request, or an unknown id)."""
    event = UnassignedQueue().find(db, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found in the queue")
    return LeadEventDetail.model_validate(event).model_copy(
        update={
            "activity": event_activity(db, event.id),
            "change_requests": _event_change_requests(db, event.id),
        }
    )


def _refuse(exc: AssignmentRefused) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.post("/unassigned-queue/{event_id}/assign", response_model=LeadEventOut)
def assign_event(
    event_id: int,
    body: LeadAssignIn,
    db: Session = Depends(get_db),
    lead_user: User = Depends(_lead),
) -> LeadEventOut:
    """Assign a request from the Unassigned Queue to a Coordinator. Refused
    (409) if it is no longer in the queue; the existing assignment stands."""
    try:
        event = AssignEvent(db, lead_user).apply(event_id, body.coordinator_id)
    except AssignmentRefused as exc:
        db.rollback()
        raise _refuse(exc) from None
    return LeadEventOut.model_validate(event)


@router.post("/assignments/{event_id}/reassign", response_model=LeadEventOut)
def reassign_event(
    event_id: int,
    body: LeadAssignIn,
    db: Session = Depends(get_db),
    lead_user: User = Depends(_lead),
) -> LeadEventOut:
    """Move an active Event to another Coordinator. Refused (409) for a
    finished or unassigned Event, or the Coordinator who already has it."""
    try:
        event = ReassignEvent(db, lead_user).apply(event_id, body.coordinator_id)
    except AssignmentRefused as exc:
        db.rollback()
        raise _refuse(exc) from None
    return LeadEventOut.model_validate(event)
