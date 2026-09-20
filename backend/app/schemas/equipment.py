"""Schemas for the equipment catalogue.

Read-only: this module describes what the catalogue *shows*, not what can
be changed. Creating, editing and retiring items is EQUIPMENT_MANAGE and a
separate story.
"""

from pydantic import BaseModel, ConfigDict

from app.models.enums import EquipmentOperationalStatus

# How each operational status reads to a person. Kept here rather than in
# the frontend alone so the API and the UI cannot drift apart.
OPERATIONAL_STATUS_LABELS: dict[EquipmentOperationalStatus, str] = {
    EquipmentOperationalStatus.available: "Available",
    EquipmentOperationalStatus.maintenance: "Under maintenance",
    EquipmentOperationalStatus.damaged: "Damaged",
    EquipmentOperationalStatus.retired: "Retired",
}


class EquipmentOut(BaseModel):
    """One catalogue row.

    `operational_status` and `available_quantity` are two different facts
    and the acceptance criterion asks for both:

      * operational_status -- the CONDITION of the item. A stored column.
      * available_quantity -- how many units are free to reserve right now.
        Computed per request; never stored, because it changes whenever a
        reservation is made or released.
    """

    id: int
    name: str
    category: str | None
    description: str | None
    total_quantity: int
    location: str | None
    operational_status: EquipmentOperationalStatus
    available_quantity: int
    technical_specs: str | None


class EquipmentCatalogueOut(BaseModel):
    """The catalogue, plus every type it contains.

    `types` is deliberately part of this response rather than derived from
    `items` by the caller: `items` may be filtered, and a type dropdown
    built from a filtered list collapses to the one type already selected,
    leaving no way back. These are the types in the WHOLE catalogue,
    whatever filter is applied.
    """

    items: list[EquipmentOut]
    types: list[str]


class EquipmentOption(BaseModel):
    """One pickable item, for the equipment picker on an event request.

    Three fields and no more, deliberately.

    The catalogue response (EquipmentOut) carries storage location,
    operational condition and live stock levels. An Event Organiser is an
    EXTERNAL client -- the Week 1 briefing is explicit that external users
    should not see internal planning information -- and a picker that simply
    declines to *render* those fields would still *ship* them over the wire.
    Enough to choose the right item, nothing about how ConnectSphere keeps
    it.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: str | None
