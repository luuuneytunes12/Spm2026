"""Technical Support marking part of an equipment item out of service (SCRUM-115).

    ConditionChange (abstract)  /  MarkOutOfService, ReturnToService
        One change of some units, in one condition. Each decides whether it is
        allowed and what it does to the counts.

    EquipmentConditionService
        Locks the item, applies a change and logs it.

Nothing here commits. The route commits, so the counts and their log line are
written together or not at all; and every rule is checked before anything is
changed, so a refusal leaves nothing behind.
"""

from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from app.domain.errors import Conflict, InvalidInput, NotFound
from app.models.enums import EquipmentOperationalStatus
from app.models.equipment import Equipment, EquipmentActivity
from app.models.user import User

_COUNT_OF = {
    EquipmentOperationalStatus.damaged: "damaged_quantity",
    EquipmentOperationalStatus.maintenance: "maintenance_quantity",
}
_LABEL_OF = {
    EquipmentOperationalStatus.damaged: "Damaged",
    EquipmentOperationalStatus.maintenance: "Under Maintenance",
}


class ConditionChange(ABC):
    def __init__(self, condition: EquipmentOperationalStatus, quantity: int) -> None:
        self.condition = condition
        self.quantity = quantity

    def apply(self, item: Equipment) -> str:
        """Change the item's count, or refuse. Returns the log note."""
        if self.quantity <= 0:
            raise InvalidInput("Enter a quantity greater than 0.", field="quantity")
        count = _COUNT_OF[self.condition]
        setattr(item, count, self._new_count(item, getattr(item, count)))
        return self._note()

    @abstractmethod
    def _new_count(self, item: Equipment, current: int) -> int:
        """The count after this change, or refuse."""

    @abstractmethod
    def _note(self) -> str:
        """What happened, in words, for the log."""


class MarkOutOfService(ConditionChange):
    def _new_count(self, item: Equipment, current: int) -> int:
        in_service = item.total_quantity - item.out_of_service_quantity
        if self.quantity > in_service:
            raise InvalidInput(
                f"Only {in_service} of {item.total_quantity} {item.name} can be marked; "
                f"{item.out_of_service_quantity} already out of service.",
                field="quantity",
            )
        return current + self.quantity

    def _note(self) -> str:
        return f"Marked {self.quantity} as {_LABEL_OF[self.condition]}."


class ReturnToService(ConditionChange):
    def _new_count(self, item: Equipment, current: int) -> int:
        if self.quantity > current:
            raise InvalidInput(
                f"Only {current} {item.name} marked {_LABEL_OF[self.condition]} can be returned.",
                field="quantity",
            )
        return current - self.quantity

    def _note(self) -> str:
        return f"Returned {self.quantity} from {_LABEL_OF[self.condition]} to service."


class EquipmentConditionService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def apply(self, equipment_id: int, actor: User, change: ConditionChange) -> Equipment:
        # Reserving locks this row too, so it and a change here go one at a time.
        item = self._db.get(Equipment, equipment_id, with_for_update=True, populate_existing=True)
        if item is None:
            raise NotFound("Equipment not found")
        # A status on the whole item already makes all of it unavailable, so
        # counting part of it would change nothing, and returning part of it
        # would not bring it back.
        if item.operational_status is not EquipmentOperationalStatus.available:
            raise Conflict(
                f"{item.name} is recorded as {item.operational_status} as a whole, "
                "so part of it cannot be marked or returned."
            )
        note = change.apply(item)
        self._db.add(EquipmentActivity(equipment_id=item.id, changed_by=actor.id, note=note))
        self._db.flush()
        return item
