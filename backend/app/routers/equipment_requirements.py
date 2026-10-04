from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_role
from app.core.roles import Role
from app.domain.equipment_fulfillment import EquipmentRequirementFulfillmentService
from app.domain.equipment_requirements import (
    EquipmentRequirementService,
    TechSupportRequirementReader,
)
from app.domain.requirement_progress import RequirementReservationLinks
from app.models.user import User
from app.schemas.equipment_requirement import (
    EquipmentRequirementIn,
    EquipmentRequirementOut,
    EquipmentRequirementUpdate,
    ReservationRequest,
    SupportEventRecord,
    SupportEventSummary,
    SupportRequirementOut,
    SupportRequirementUpdate,
)
from app.services.reservation_gateway import ErcongReservationGateway

# Thin on purpose. Every rule -- who may record what, and when -- lives in
# app/domain/equipment_requirements.py, and Technical Support's side of a
# requirement in app/domain/equipment_fulfillment.py. These handlers parse
# the request, call a method, commit, and shape the reply. Domain errors are turned into
# HTTP responses by one handler (app/core/error_handlers.py), so nothing
# here raises HTTPException for a business rule.
router = APIRouter(prefix="/equipment-requirements", tags=["equipment-requirements"])

# Gated on role, not permission. COORDINATOR and TECH_SUPPORT both hold
# EQUIPMENT_READ, so a permission check could not tell them apart -- and
# these two audiences have different views and different powers.
_coordinator = require_role(Role.COORDINATOR)
_tech_support = require_role(Role.TECH_SUPPORT)


def get_requirement_service(db: Session = Depends(get_db)) -> EquipmentRequirementService:
    return EquipmentRequirementService(db)


def get_requirement_reader(db: Session = Depends(get_db)) -> TechSupportRequirementReader:
    return TechSupportRequirementReader(db)


def get_links(db: Session = Depends(get_db)) -> RequirementReservationLinks:
    return RequirementReservationLinks(db)


def get_fulfillment_service(
    db: Session = Depends(get_db),
) -> EquipmentRequirementFulfillmentService:
    # The gateway is the one place Ercong's reservation is reached; swap it
    # here and the service is none the wiser.
    return EquipmentRequirementFulfillmentService(db, ErcongReservationGateway(db))


# ---------------------------------------------------------------------------
# Technical Support -- declared first so "support" is never read as an id
# ---------------------------------------------------------------------------


@router.get("/support/events", response_model=list[SupportEventSummary])
def list_events_with_requirements(
    reader: TechSupportRequirementReader = Depends(get_requirement_reader),
    _: User = Depends(_tech_support),
) -> list[SupportEventSummary]:
    """Events with equipment to review: approved, planning or confirmed,
    with at least one requirement. Never drafts."""
    return [
        SupportEventSummary(
            id=event.id,
            name=event.name,
            event_type=event.event_type,
            proposed_start=event.proposed_start,
            proposed_end=event.proposed_end,
            expected_attendance=event.expected_attendance,
            status=event.status,
            requirement_count=count,
        )
        for event, count in reader.events()
    ]


@router.get("/support/events/{event_id}", response_model=SupportEventRecord)
def get_event_record(
    event_id: int,
    reader: TechSupportRequirementReader = Depends(get_requirement_reader),
    links: RequirementReservationLinks = Depends(get_links),
    _: User = Depends(_tech_support),
) -> SupportEventRecord:
    """The event record: what the event is, what equipment it needs, and how
    far each requirement has got."""
    event, requirements = reader.event(event_id)
    progress = links.progress_of(requirements)
    return SupportEventRecord(
        id=event.id,
        name=event.name,
        event_type=event.event_type,
        proposed_start=event.proposed_start,
        proposed_end=event.proposed_end,
        expected_attendance=event.expected_attendance,
        venue_requirements=event.venue_requirements,
        status=event.status,
        coordinator=event.coordinator,
        requirements=[SupportRequirementOut.of(r, progress[r.id]) for r in requirements],
    )


@router.patch("/support/requirements/{requirement_id}", response_model=SupportRequirementOut)
def update_requirement(
    requirement_id: int,
    body: SupportRequirementUpdate,
    db: Session = Depends(get_db),
    service: EquipmentRequirementFulfillmentService = Depends(get_fulfillment_service),
    _: User = Depends(_tech_support),
) -> SupportRequirementOut:
    """Update the status and quantity Technical Support owns. The Coordinator
    reads the result on the event record."""
    requirement, progress = service.update(requirement_id, **body.model_dump(exclude_unset=True))
    db.commit()
    return SupportRequirementOut.of(requirement, progress)


@router.post("/{requirement_id}/reservations", response_model=SupportRequirementOut)
def reserve_for_requirement(
    requirement_id: int,
    body: ReservationRequest,
    db: Session = Depends(get_db),
    service: EquipmentRequirementFulfillmentService = Depends(get_fulfillment_service),
    user: User = Depends(_tech_support),
) -> SupportRequirementOut:
    """Reserve an item for a requirement, through the Equipment Reservations
    capability. The stock and overlap rules are that capability's, not
    repeated here; this only says which requirement the reservation is for."""
    requirement, progress = service.reserve(requirement_id, body.equipment_id, body.quantity, user)
    db.commit()
    return SupportRequirementOut.of(requirement, progress)


# ---------------------------------------------------------------------------
# Event Coordinator
# ---------------------------------------------------------------------------


@router.post(
    "/events/{event_id}",
    response_model=EquipmentRequirementOut,
    status_code=status.HTTP_201_CREATED,
)
def add_requirement(
    event_id: int,
    body: EquipmentRequirementIn,
    db: Session = Depends(get_db),
    service: EquipmentRequirementService = Depends(get_requirement_service),
    links: RequirementReservationLinks = Depends(get_links),
    user: User = Depends(_coordinator),
) -> EquipmentRequirementOut:
    """Record equipment an assigned event needs."""
    requirement = service.add(event_id, user.id, **body.model_dump())
    db.commit()
    db.refresh(requirement)
    return EquipmentRequirementOut.of(requirement, links.progress_for(requirement))


@router.get("/events/{event_id}", response_model=list[EquipmentRequirementOut])
def list_requirements(
    event_id: int,
    service: EquipmentRequirementService = Depends(get_requirement_service),
    links: RequirementReservationLinks = Depends(get_links),
    user: User = Depends(_coordinator),
) -> list[EquipmentRequirementOut]:
    requirements = service.list_for_coordinator(event_id, user.id)
    progress = links.progress_of(requirements)
    return [EquipmentRequirementOut.of(r, progress[r.id]) for r in requirements]


@router.patch("/{requirement_id}", response_model=EquipmentRequirementOut)
def edit_requirement(
    requirement_id: int,
    body: EquipmentRequirementUpdate,
    db: Session = Depends(get_db),
    service: EquipmentRequirementService = Depends(get_requirement_service),
    links: RequirementReservationLinks = Depends(get_links),
    user: User = Depends(_coordinator),
) -> EquipmentRequirementOut:
    # exclude_unset: a field left out of the request is left alone, while an
    # explicit null still clears the notes.
    requirement = service.edit(requirement_id, user.id, **body.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(requirement)
    return EquipmentRequirementOut.of(requirement, links.progress_for(requirement))


@router.delete("/{requirement_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_requirement(
    requirement_id: int,
    db: Session = Depends(get_db),
    service: EquipmentRequirementService = Depends(get_requirement_service),
    user: User = Depends(_coordinator),
) -> Response:
    service.remove(requirement_id, user.id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
