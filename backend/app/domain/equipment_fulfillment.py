"""Technical Support fulfilling a Coordinator's equipment requirements.

    EquipmentRequirementFulfillmentService
        The rules and the orchestration: reserve equipment for a
        requirement, and update the status and quantity Technical Support
        owns. Given its collaborators; builds none of them.

    ReservationGateway (abstract)
        What the service needs from a reservation capability. The production
        implementation, ErcongReservationGateway (app/services/), delegates
        to the existing Equipment Reservations function, unchanged. A test
        hands the service a fake instead, so the orchestration is exercised
        without any stock or overlap rules.

        The domain owns the contract and depends on no implementation of it:
        the adapter, which has to import his router, lives outside.

    RequirementReservationLinks, RequirementProgress (requirement_progress.py)
        Which reserved items fulfil which requirement, and the status that
        follows.

This feature does not make reservations of its own, and does not duplicate
how one is checked or made. Stock, overlap, event status and the write are
all Ercong's `reserve_equipment`. What is added here is only the question
"which requirement is this for?", answered by a link written in the same
commit as the reservation.
"""

from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from app.domain.equipment_requirements import EQUIPMENT_ACTIVE_STATUSES
from app.domain.errors import Conflict, DomainError, InvalidInput, NotFound
from app.domain.requirement_progress import (
    TECH_SUPPORT_STATUSES,
    RequirementProgress,
    RequirementReservationLinks,
    ReservedItem,
)
from app.models.enums import EquipmentStatus
from app.models.equipment import CoordinatorEquipmentRequirement, Equipment
from app.models.events import Event
from app.models.user import User

__all__ = [
    "TECH_SUPPORT_STATUSES",
    "EquipmentRequirementFulfillmentService",
    "RequirementProgress",
    "RequirementReservationLinks",
    "ReservationGateway",
    "ReservationRefused",
    "ReservedItem",
]

# What an update may change. The type and the notes are the Coordinator's.
_UPDATABLE_FIELDS = frozenset({"status", "quantity_needed"})


class ReservationRefused(DomainError):
    """The reservation capability said no, and said why.

    Carries the refusal's own status and words, so what the user reads is
    what the Equipment Reservations page would have told them.
    """

    def __init__(self, message: str, *, status_code: int, field: str | None = None) -> None:
        super().__init__(message, field=field)
        self.status_code = status_code


class ReservationGateway(ABC):
    """A way of reserving equipment for an event."""

    @abstractmethod
    def forced_quantity(self, event_id: int, equipment_id: int) -> int | None:
        """How many of the item a reservation would take whatever is asked
        for, or None if the quantity is the caller's to choose."""

    @abstractmethod
    def reserve(
        self, *, event_id: int, equipment_id: int, quantity: int | None, user: User
    ) -> int:
        """Reserve the item for the event. Returns the quantity reserved.

        Raises ReservationRefused if it cannot be reserved.
        """


class EquipmentRequirementFulfillmentService:
    """Technical Support's side of a requirement: reserve for it, and update
    the status and quantity they own.

    Does not commit, except that the gateway's reservation does -- which is
    intended: it carries the link with it. The router commits what is left
    (a status moved on after a successful reservation).
    """

    def __init__(
        self,
        db: Session,
        gateway: ReservationGateway,
        links: RequirementReservationLinks | None = None,
    ) -> None:
        self._db = db
        self._gateway = gateway
        self._links = links if links is not None else RequirementReservationLinks(db)

    # --- commands -----------------------------------------------------------

    def reserve(
        self, requirement_id: int, equipment_id: int, quantity: int | None, user: User
    ) -> tuple[CoordinatorEquipmentRequirement, RequirementProgress]:
        requirement = self._requirement_in_window(requirement_id)
        item = self._item_of_the_requirements_type(requirement, equipment_id)
        progress = self._links.progress_for(requirement)
        to_gateway = self._checked_quantity_to_reserve(requirement, item, progress, quantity)

        # The link goes into the session BEFORE the reservation is made, so
        # the reservation's own commit writes both or neither. If it refuses,
        # the pending link is rolled back with nothing else to undo.
        self._links.claim(requirement, item.id)
        try:
            self._gateway.reserve(
                event_id=requirement.event_id,
                equipment_id=item.id,
                quantity=to_gateway,
                user=user,
            )
        except BaseException:
            self._db.rollback()
            raise

        if requirement.status is EquipmentStatus.rejected:
            # Equipment turned up after it was marked Unavailable: it is being
            # worked on again. Moving the stored outcome on means it does not
            # come back as Unavailable if the reservation is later lost.
            requirement.status = EquipmentStatus.reviewing
            self._db.flush()
        return requirement, self._links.progress_for(requirement)

    def update(
        self, requirement_id: int, **changes: object
    ) -> tuple[CoordinatorEquipmentRequirement, RequirementProgress]:
        """Change the status and/or quantity needed. Fields not mentioned are
        left alone; an empty update is not a write."""
        unknown = set(changes) - _UPDATABLE_FIELDS
        if unknown:
            raise TypeError(f"Not updatable here: {', '.join(sorted(unknown))}")

        requirement = self._requirement_in_window(requirement_id)
        progress = self._links.progress_for(requirement)

        if "status" in changes:
            requirement.status = self._checked_status(changes["status"], progress)
        if "quantity_needed" in changes:
            requirement.quantity_needed = progress.check_new_quantity(changes["quantity_needed"])

        self._db.flush()
        return requirement, self._links.progress_for(requirement)

    # --- rules --------------------------------------------------------------

    def _requirement_in_window(self, requirement_id: int) -> CoordinatorEquipmentRequirement:
        """The requirement, if Technical Support is meant to see it.

        Outside the window, or unknown, it is NotFound -- the same answer the
        event record gives, so the two never disagree.
        """
        requirement = self._db.get(CoordinatorEquipmentRequirement, requirement_id)
        event = self._db.get(Event, requirement.event_id) if requirement else None
        if event is None or event.status not in EQUIPMENT_ACTIVE_STATUSES:
            raise NotFound("Requirement not found")
        return requirement

    def _item_of_the_requirements_type(
        self, requirement: CoordinatorEquipmentRequirement, equipment_id: int
    ) -> Equipment:
        """The Coordinator chose a TYPE; Technical Support chooses the item,
        from that type."""
        item = self._db.get(Equipment, equipment_id)
        if item is None:
            raise InvalidInput("That equipment does not exist.", field="equipment_id")
        if (item.category or "").strip().casefold() != requirement.category.strip().casefold():
            raise InvalidInput(
                f"{item.name} is not {requirement.category} equipment; "
                f"this requirement needs {requirement.category}.",
                field="equipment_id",
            )
        return item

    def _checked_quantity_to_reserve(
        self,
        requirement: CoordinatorEquipmentRequirement,
        item: Equipment,
        progress: RequirementProgress,
        quantity: int | None,
    ) -> int | None:
        """Refuse a reservation that would reserve more than is needed, and
        say what to ask the gateway for.

        There is no way to give a reservation back, so over-filling a
        requirement cannot be undone. Where the Organiser asked for the item
        the reservation takes THEIR quantity whole (not the service's
        choice), so that is what is compared with what remains.
        """
        if progress.remaining == 0:
            raise Conflict("This requirement is already fully reserved.")
        if quantity is not None and (
            not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1
        ):
            raise InvalidInput("Quantity must be at least 1.", field="quantity")

        forced = self._gateway.forced_quantity(requirement.event_id, item.id)
        if forced is not None:
            if forced > progress.remaining:
                raise Conflict(
                    f"This event asked for {forced} {item.name}, and a reservation takes "
                    f"that whole quantity; this requirement needs only {progress.remaining} more."
                )
            return quantity  # as sent: if it differs from the forced quantity, his refusal says so

        taking = progress.remaining if quantity is None else quantity
        if taking > progress.remaining:
            raise Conflict(
                f"This requirement needs {progress.remaining} more; {taking} is too many.",
                field="quantity",
            )
        return taking

    @staticmethod
    def _checked_status(status: object, progress: RequirementProgress) -> EquipmentStatus:
        try:
            status = EquipmentStatus(status)
        except ValueError:
            raise InvalidInput("Choose a status.", field="status") from None
        if status is EquipmentStatus.reserved:
            raise InvalidInput(
                "Reserved comes from the reservations; it cannot be set by hand.", field="status"
            )
        if status not in TECH_SUPPORT_STATUSES:
            raise InvalidInput("That status cannot be set here.", field="status")
        if status is EquipmentStatus.rejected and progress.reserved > 0:
            raise Conflict(
                "Equipment is already reserved for this requirement, "
                "so it cannot be marked unavailable.",
                field="status",
            )
        return status
