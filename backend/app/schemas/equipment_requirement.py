"""Schemas for the Coordinator's equipment requirements.

Two audiences, two shapes. The Coordinator who wrote a requirement gets all
of it; Technical Support gets only what they need to review it. Sharing one
response schema would mean every field added for one reader reaches the
other.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import EquipmentStatus, EventStatus
from app.schemas.event import OrganiserContact


class EquipmentRequirementIn(BaseModel):
    """A new requirement.

    `category` is checked against the catalogue by the domain, not here:
    which categories exist is data, not a property of the request's shape.
    """

    category: str
    # gt=0 mirrors the database CHECK, so a bad quantity is a 422 naming the
    # field rather than an IntegrityError.
    quantity_needed: int = Field(gt=0)
    technical_notes: str | None = None
    # Which of the Organiser's picks this was based on, if any. Set once, here.
    organiser_equipment_request_id: int | None = None


class EquipmentRequirementUpdate(BaseModel):
    """An edit. Every field is optional; only those sent are changed.

    There is no `organiser_equipment_request_id`: where a requirement came
    from is not something to retarget, and one sent anyway is ignored.
    """

    category: str | None = None
    quantity_needed: int | None = Field(default=None, gt=0)
    technical_notes: str | None = None


class EquipmentRequirementOut(BaseModel):
    """A requirement as its Coordinator sees it."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int
    organiser_equipment_request_id: int | None
    category: str
    quantity_needed: int
    technical_notes: str | None
    status: EquipmentStatus
    created_at: datetime
    updated_at: datetime


class SupportRequirementOut(BaseModel):
    """A requirement as Technical Support sees it.

    No author and no link to the Organiser's pick: that is the Coordinator's
    own bookkeeping.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    quantity_needed: int
    technical_notes: str | None
    status: EquipmentStatus


class SupportEventSummary(BaseModel):
    """One row of Technical Support's list."""

    id: int
    name: str | None
    event_type: str | None
    proposed_start: datetime | None
    proposed_end: datetime | None
    expected_attendance: int | None
    status: EventStatus
    requirement_count: int


class SupportEventRecord(BaseModel):
    """The event as Technical Support sees it: enough to judge what the
    equipment is for, and the requirements themselves."""

    id: int
    name: str | None
    event_type: str | None
    proposed_start: datetime | None
    proposed_end: datetime | None
    expected_attendance: int | None
    venue_requirements: str | None
    status: EventStatus
    coordinator: OrganiserContact | None
    requirements: list[SupportRequirementOut]
