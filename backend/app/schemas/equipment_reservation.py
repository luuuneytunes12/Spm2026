"""Schemas for checking equipment availability and reserving it
(Technical Support Staff)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import EquipmentOperationalStatus, EquipmentStatus, EventStatus
from app.schemas.venue_booking import BookingEventRef, BookingPerson


class RequiredEquipment(BaseModel):
    """One line of what an event asked for -- the quantity it REQUIRES."""

    model_config = ConfigDict(from_attributes=True)

    equipment_id: int
    equipment_name: str
    equipment_category: str | None
    quantity_requested: int
    status: EquipmentStatus


class ReservableEvent(BaseModel):
    """An event Technical Support may reserve equipment for."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None
    status: EventStatus
    proposed_start: datetime
    proposed_end: datetime
    equipment_items: list[RequiredEquipment]


class EquipmentAvailabilityOut(BaseModel):
    """Availability of one item for one window.

    `required_quantity` and `sufficient` are only filled in when the check
    is made for an event that asked for this item; otherwise there is
    nothing to compare against and both are null.
    """

    equipment_id: int
    equipment_name: str
    equipment_category: str | None
    operational_status: EquipmentOperationalStatus
    total_quantity: int
    reserved_quantity: int
    available_quantity: int
    start_time: datetime
    end_time: datetime
    required_quantity: int | None
    sufficient: bool | None


class EquipmentReservationCreate(BaseModel):
    """Reserve `equipment_id` for `event_id`, for the event's own date and
    time.

    If the event requested the item, its whole requested quantity is
    reserved and `quantity` may be left out. If it did not, Technical
    Support adds the item themselves and `quantity` says how many.
    """

    event_id: int
    equipment_id: int
    quantity: int | None = Field(default=None, ge=1)


class EquipmentReservationOut(BaseModel):
    """A reservation as recorded: equipment, quantity, event, date and
    window, and who made it when."""

    id: int
    event: BookingEventRef
    equipment_id: int
    equipment_name: str
    equipment_category: str | None
    quantity: int
    start_time: datetime
    end_time: datetime
    reserved_by: BookingPerson
    reserved_at: datetime
