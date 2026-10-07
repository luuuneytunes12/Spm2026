"""Schemas for the Safety Officer's Operational Safety Check."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import BookingStatus, EquipmentStatus, EventStatus
from app.schemas.event import ActivityEntry, OrganiserContact


class SafetyCheckSummary(BaseModel):
    """One row of the Safety Checks queue."""

    id: int
    name: str | None
    proposed_start: datetime | None
    proposed_end: datetime | None
    coordinator: OrganiserContact | None


class SafetyVenue(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    location: str
    capacity: int
    supported_layouts: list[str]
    accessibility_features: list[str]
    emergency_access: str | None
    known_restrictions: str | None


class SafetyVenueBooking(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: BookingStatus
    start_time: datetime
    end_time: datetime
    safety_recheck_reason: str | None
    venue: SafetyVenue


class SafetyEquipmentLine(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    equipment_name: str
    equipment_category: str | None
    quantity_requested: int
    status: EquipmentStatus
    placement_notes: str | None
    safety_recheck_reason: str | None


class SafetyCheckDetail(BaseModel):
    """Everything a Safety Officer needs to judge an event's arrangement."""

    id: int
    name: str | None
    status: EventStatus
    proposed_start: datetime | None
    proposed_end: datetime | None
    expected_attendance: int | None
    room_layout_preference: str | None
    accessibility_needs: str | None
    special_arrangements: str | None
    organiser: OrganiserContact
    coordinator: OrganiserContact | None
    venue_booking: SafetyVenueBooking | None
    equipment: list[SafetyEquipmentLine]
    activity: list[ActivityEntry]


class SafetyReasonIn(BaseModel):
    """A rejection: the reason is mandatory, so a blank one is never saved."""

    reason: str = Field(..., max_length=2000)

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A reason is required.")
        return value.strip()


class SafetyChangesIn(SafetyReasonIn):
    """A change request: the reason plus the bookings / lines to look at again."""

    venue_booking_ids: list[int] = []
    equipment_request_ids: list[int] = []
