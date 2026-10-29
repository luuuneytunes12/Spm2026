"""Tell Technical Support Staff about equipment they have to review or reserve.

Equipment is not assigned to one Technical Support Staff member, so every one
of them is told, in the transaction that made the change: if it rolls back
nobody is notified. Each line carries what they need without opening the
Event -- its name, its date and time, and the equipment.

    TechSupportNotice                  base: every Technical Support Staff member
      EquipmentRequiredNotice            a requirement was recorded (AC1)
      EquipmentRequirementChangedNotice  its type, quantity or notes changed (AC2)
      EquipmentRequirementRemovedNotice  it was removed (AC2)
      EventRescheduledNotice             the Event moved; old and new date/time (AC3)

`notify_if_rescheduled` is the one entry point for AC3: call it after an
Event's fields are applied, with the times it had before.
"""

from datetime import datetime

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.datetimes import as_utc
from app.core.roles import Role
from app.models.enums import EquipmentStatus, NotificationType
from app.models.equipment import CoordinatorEquipmentRequirement, EquipmentRequest
from app.models.events import Event
from app.models.user import User
from app.services.submission_notice import EventNotice


def when(start: datetime | None, end: datetime | None) -> str:
    """'2 Nov 2026, 09:00-17:00 UTC', or both dates when it spans days."""
    if start is None:
        return "no date set"
    start = as_utc(start)
    day = f"{start.day} {start:%b %Y}"
    if end is None:
        return f"{day}, {start:%H:%M} UTC"
    end = as_utc(end)
    if end.date() == start.date():
        return f"{day}, {start:%H:%M}-{end:%H:%M} UTC"
    return f"{day} {start:%H:%M} - {end.day} {end:%b %Y} {end:%H:%M} UTC"


def _event(event: Event) -> str:
    return f"'{event.name or 'Untitled event'}' ({when(event.proposed_start, event.proposed_end)})"


class TechSupportNotice(EventNotice):
    """Base: sent to every Technical Support Staff member."""

    def recipients(self, db: Session, event: Event) -> list[int]:
        return list(db.scalars(select(User.id).where(User.role == Role.TECH_SUPPORT.value).order_by(User.id)))


class EquipmentRequiredNotice(TechSupportNotice):
    """A new equipment requirement for the Event."""

    type = NotificationType.equipment_required

    def __init__(self, requirement: CoordinatorEquipmentRequirement) -> None:
        self.requirement = requirement

    def message(self, event: Event) -> str:
        r = self.requirement
        notes = f" Notes: {r.technical_notes}" if r.technical_notes else ""
        return f"Equipment required for {_event(event)}: {r.quantity_needed} x {r.category}.{notes}"


class EquipmentRequirementChangedNotice(TechSupportNotice):
    """What changed on a requirement, and what is already reserved for it."""

    type = NotificationType.equipment_requirement_changed

    def __init__(self, category: str, changes: list[str], reserved: int) -> None:
        self.category = category
        self.changes = changes
        self.reserved = reserved

    def message(self, event: Event) -> str:
        text = f"Equipment requirement changed for {_event(event)}: {self.category} - {'; '.join(self.changes)}."
        if self.reserved:
            text += f" {self.reserved} already reserved for it: check the reservation still fits."
        return text


class EquipmentRequirementRemovedNotice(TechSupportNotice):
    type = NotificationType.equipment_requirement_removed

    def __init__(self, category: str, quantity: int) -> None:
        self.category = category
        self.quantity = quantity

    def message(self, event: Event) -> str:
        return (
            f"Equipment requirement removed for {_event(event)}: {self.quantity} x {self.category} "
            "is no longer needed."
        )


class EventRescheduledNotice(TechSupportNotice):
    type = NotificationType.equipment_event_rescheduled

    def __init__(self, old_start: datetime | None, old_end: datetime | None) -> None:
        self.old = when(old_start, old_end)

    def message(self, event: Event) -> str:
        return (
            f"'{event.name or 'Untitled event'}' has moved from {self.old} to "
            f"{when(event.proposed_start, event.proposed_end)}. Check its equipment requirements "
            "and reservations for the new date and time."
        )


def describe_changes(
    before: tuple[str, int, str | None], after: tuple[str, int, str | None]
) -> list[str]:
    """'type Audio -> Projection', 'quantity 2 -> 4', notes added/changed/removed."""
    (old_type, old_qty, old_notes), (new_type, new_qty, new_notes) = before, after
    changes: list[str] = []
    if new_type != old_type:
        changes.append(f"type {old_type} -> {new_type}")
    if new_qty != old_qty:
        changes.append(f"quantity {old_qty} -> {new_qty}")
    if new_notes != old_notes:
        if old_notes is None:
            changes.append(f"technical notes added: {new_notes}")
        elif new_notes is None:
            changes.append("technical notes removed")
        else:
            changes.append(f"technical notes changed to: {new_notes}")
    return changes


def has_equipment(db: Session, event: Event) -> bool:
    """A requirement recorded, or equipment reserved, for the Event."""
    return bool(
        db.scalar(
            select(
                exists().where(CoordinatorEquipmentRequirement.event_id == event.id)
                | exists().where(
                    EquipmentRequest.event_id == event.id,
                    EquipmentRequest.status == EquipmentStatus.reserved,
                )
            )
        )
    )


def notify_if_rescheduled(
    db: Session, event: Event, old_start: datetime | None, old_end: datetime | None
) -> bool:
    """AC3: tell Technical Support when the Event's date or time changed and it
    has equipment to look after. Returns whether anyone was told."""
    def same(a: datetime | None, b: datetime | None) -> bool:
        return (a is None and b is None) or (a is not None and b is not None and as_utc(a) == as_utc(b))

    if same(old_start, event.proposed_start) and same(old_end, event.proposed_end):
        return False
    db.flush()
    if not has_equipment(db, event):
        return False
    EventRescheduledNotice(old_start, old_end).send(db, event)
    return True
