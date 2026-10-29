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
commit as the reservation -- and, optionally, where the item will be placed,
which his reservation already records.

The statuses are the Definition of Done's (11b). Technical Support sets
Requested or Unavailable (with a reason); Reserved comes from the
reservations and Available from the event ending, so neither is settable.
Every change of the status people see goes in the Activity Log.
"""

from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from app.domain.activity_log import ActivityLog, EventHistoryLog
from app.domain.equipment_requirements import EQUIPMENT_ACTIVE_STATUSES
from app.domain.errors import Conflict, DomainError, InvalidInput, NotFound
from app.domain.requirement_progress import (
    STORED_UNAVAILABLE,
    TECH_SUPPORT_STATUSES,
    RequirementProgress,
    RequirementReservationLinks,
    RequirementStatus,
    RequirementStatusLog,
    ReservedItem,
    checked_reason,
)
from app.models.enums import EquipmentStatus
from app.models.equipment import CoordinatorEquipmentRequirement, Equipment
from app.models.events import Event
from app.models.user import User
from app.services.organiser_notices import EquipmentOutcomeNotice

__all__ = [
    "TECH_SUPPORT_STATUSES",
    "EquipmentRequirementFulfillmentService",
    "RequirementProgress",
    "RequirementReservationLinks",
    "RequirementStatus",
    "ReservationGateway",
    "ReservationRefused",
    "ReservedItem",
]

# What an update may change. The type and the notes are the Coordinator's.
# `reason` goes with an Unavailable status; sent on its own it changes nothing.
_UPDATABLE_FIELDS = frozenset({"status", "quantity_needed", "reason"})


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
        self,
        *,
        event_id: int,
        equipment_id: int,
        quantity: int | None,
        user: User,
        placement_notes: str | None = None,
    ) -> int:
        """Reserve the item for the event, noting where it will be placed.
        Returns the quantity reserved.

        Raises ReservationRefused if it cannot be reserved.
        """


class EquipmentRequirementFulfillmentService:
    """Technical Support's side of a requirement: reserve for it, and update
    the status and quantity they own.

    Does not commit, except that the gateway's reservation does -- which is
    intended: it carries the link with it. The router commits what is left
    (a status moved on after a successful reservation, the Activity Log).
    """

    def __init__(
        self,
        db: Session,
        gateway: ReservationGateway,
        links: RequirementReservationLinks | None = None,
        activity: ActivityLog | None = None,
    ) -> None:
        self._db = db
        self._gateway = gateway
        self._links = links if links is not None else RequirementReservationLinks(db)
        self._status_log = RequirementStatusLog(
            activity if activity is not None else EventHistoryLog(db)
        )

    # --- commands -----------------------------------------------------------

    def reserve(
        self,
        requirement_id: int,
        equipment_id: int,
        quantity: int | None,
        user: User,
        placement_notes: str | None = None,
    ) -> tuple[CoordinatorEquipmentRequirement, RequirementProgress]:
        requirement = self._requirement_in_window(requirement_id)
        item = self._item_of_the_requirements_type(requirement, equipment_id)
        progress = self._links.progress_for(requirement)
        self._ensure_not_freed(progress)
        to_gateway = self._checked_quantity_to_reserve(requirement, item, progress, quantity)
        placement = self._checked_placement(placement_notes)

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
                placement_notes=placement,
            )
        except BaseException:
            self._db.rollback()
            raise

        if requirement.status is STORED_UNAVAILABLE:
            # Equipment turned up after it was marked Unavailable: it is being
            # worked on again. Moving the stored outcome on means it does not
            # come back as Unavailable if the reservation is later lost, and
            # the old reason is no longer true.
            requirement.status = EquipmentStatus.requested
            requirement.unavailable_reason = None
        self._db.flush()

        after = self._links.progress_for(requirement)
        self._status_log.record(
            self._event_of(requirement),
            user,
            requirement,
            progress.status,
            after.status,
            by=user.name,
        )
        self._tell_organiser(requirement, progress.status, after.status)
        return requirement, after

    def update(
        self, requirement_id: int, *, actor: User | None = None, **changes: object
    ) -> tuple[CoordinatorEquipmentRequirement, RequirementProgress]:
        """Change the status and/or quantity needed. Fields not mentioned are
        left alone; an empty update is not a write.

        `actor` is who is making the change, for the Activity Log.
        """
        unknown = set(changes) - _UPDATABLE_FIELDS
        if unknown:
            raise TypeError(f"Not updatable here: {', '.join(sorted(unknown))}")

        requirement = self._requirement_in_window(requirement_id)
        progress = self._links.progress_for(requirement)
        if "status" in changes or "quantity_needed" in changes:
            self._ensure_not_freed(progress)

        if "status" in changes:
            self._apply_status(requirement, progress, changes["status"], changes.get("reason"))
        if "quantity_needed" in changes:
            requirement.quantity_needed = progress.check_new_quantity(changes["quantity_needed"])

        self._db.flush()
        after = self._links.progress_for(requirement)
        if actor is not None:
            self._status_log.record(
                self._event_of(requirement),
                actor,
                requirement,
                progress.status,
                after.status,
                by=actor.name,
                reason=after.unavailable_reason,
            )
        self._tell_organiser(requirement, progress.status, after.status, after.unavailable_reason)
        return requirement, after

    def _tell_organiser(
        self,
        requirement: CoordinatorEquipmentRequirement,
        before: RequirementStatus,
        after: RequirementStatus,
        reason: str | None = None,
    ) -> None:
        """Confirmed or Unavailable is news to the Event's Organiser."""
        notice = EquipmentOutcomeNotice.for_change(requirement, before, after, reason)
        if notice is not None:
            notice.send(self._db, self._event_of(requirement))

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

    def _event_of(self, requirement: CoordinatorEquipmentRequirement) -> Event:
        return self._db.get(Event, requirement.event_id)

    @staticmethod
    def _ensure_not_freed(progress: RequirementProgress) -> None:
        """Available means the reservation was freed because the event is
        over. There is nothing left to fulfil, so nothing to change."""
        if progress.status is RequirementStatus.AVAILABLE:
            raise Conflict(
                "This requirement's reservation was freed when the event ended; "
                "it can no longer be changed."
            )

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
    def _checked_placement(placement_notes: str | None) -> str | None:
        """Where the item will be set up. Optional; spaces are not a note."""
        if placement_notes is None:
            return None
        if not isinstance(placement_notes, str):
            raise InvalidInput("Placement must be text.", field="placement_notes")
        return placement_notes.strip() or None

    @staticmethod
    def _apply_status(
        requirement: CoordinatorEquipmentRequirement,
        progress: RequirementProgress,
        status: object,
        reason: object,
    ) -> None:
        """Set Requested or Unavailable. Nothing else can be set by hand."""
        try:
            status = RequirementStatus(status)
        except ValueError:
            raise InvalidInput("Choose a status.", field="status") from None
        if status not in TECH_SUPPORT_STATUSES:
            raise InvalidInput(
                "Reserved and Available come from the reservations; "
                "they cannot be set by hand.",
                field="status",
            )

        if status is RequirementStatus.UNAVAILABLE:
            if progress.reserved > 0:
                raise Conflict(
                    "Equipment is already reserved for this requirement, "
                    "so it cannot be marked unavailable.",
                    field="status",
                )
            requirement.unavailable_reason = checked_reason(reason)
            requirement.status = STORED_UNAVAILABLE
        else:
            # A reason belongs to Unavailable; leaving it is not "Requested".
            requirement.unavailable_reason = None
            requirement.status = EquipmentStatus.requested
