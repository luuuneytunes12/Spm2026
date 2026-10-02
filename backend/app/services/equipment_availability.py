"""How many units of an equipment item are free for a time window.

A reservation is an equipment_requests row in status `reserved` -- request,
review and reservation are one row moving through its lifecycle. It has no
window of its own: it holds its units for its EVENT's proposed_start to
proposed_end, and frees them at the event's end time. If the event's times
change, the reservation moves with them.
"""

from datetime import datetime

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from app.models.enums import EquipmentOperationalStatus, EquipmentStatus
from app.models.equipment import Equipment, EquipmentRequest
from app.models.events import Event


def held_after(moment: datetime) -> ColumnElement[bool]:
    """Reserved stock still held after `moment`: it is freed at its event's
    end time. The one rule every screen uses for when kit comes back."""
    return Event.proposed_end > moment


def reserved_units(db: Session, equipment_id: int, start: datetime, end: datetime) -> int:
    """Units of one item reserved for any event whose window overlaps
    [start, end).

    Two periods overlap when each starts before the other ends. Strict
    comparisons, so back-to-back is not an overlap: kit freed at an event's
    12:00 end is available to one starting at 12:00. The same rule venue
    search uses.
    """
    return db.scalar(
        select(func.coalesce(func.sum(EquipmentRequest.quantity_requested), 0))
        .join(Event, Event.id == EquipmentRequest.event_id)
        .where(
            EquipmentRequest.equipment_id == equipment_id,
            EquipmentRequest.status == EquipmentStatus.reserved,
            Event.proposed_start < end,
            held_after(start),
        )
    )


def available_quantity(item: Equipment, reserved: int) -> int:
    """How many units can actually be used.

    An item that is not operational reports 0 regardless of the
    arithmetic: two damaged mixers are not two available mixers. The Week 1
    briefing is explicit that equipment recorded as unavailable must not be
    treated as freely available.

    Clamped at 0 so over-reservation (more reserved than owned, possible if
    stock is reduced after the fact) reports "none left" rather than a
    negative count.
    """
    if item.operational_status is not EquipmentOperationalStatus.available:
        return 0
    return max(item.total_quantity - reserved, 0)
