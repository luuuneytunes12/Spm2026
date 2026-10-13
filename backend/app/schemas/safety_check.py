"""Schemas for the Safety Officer's Operational Safety Check."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, computed_field, Field, field_validator

from app.domain.venue_occupancy import occupied_window
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
    setup_minutes: int | None = None
    turnaround_minutes: int | None = None


class SafetyVenueBooking(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int
    status: BookingStatus
    start_time: datetime
    end_time: datetime
    safety_recheck_reason: str | None
    venue: SafetyVenue

    @computed_field  # type: ignore[prop-decorator]
    @property
    def setup_minutes(self) -> int:
        return self.venue.setup_minutes or 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def turnaround_minutes(self) -> int:
        return self.venue.turnaround_minutes or 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def occupied_start(self) -> datetime:
        return occupied_window(self.start_time, self.end_time, self.setup_minutes, 0).start

    @computed_field  # type: ignore[prop-decorator]
    @property
    def occupied_end(self) -> datetime:
        return occupied_window(self.start_time, self.end_time, 0, self.turnaround_minutes).end


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
    venue_bookings: list[SafetyVenueBooking]
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
