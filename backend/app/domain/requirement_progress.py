"""How far a Coordinator's requirement has got, and where that is read from.

    RequirementProgress         a value object: what is needed, what has been
                                reserved, what Technical Support has set --
                                and from those, the one status everybody sees
    RequirementReservationLinks the repository: which reserved items fulfil
                                which requirement

Nothing here stores "reserved". A requirement's reserved quantity is the sum
of the reserved equipment_requests rows its links point at, read fresh every
time, so it can never disagree with the reservations themselves -- which
belong to Ercong's feature and are not touched here.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.domain.errors import Conflict, InvalidInput
from app.models.enums import EquipmentStatus
from app.models.equipment import (
    CoordinatorEquipmentRequirement,
    Equipment,
    EquipmentRequest,
    RequirementReservationLink,
)

# What Technical Support may set by hand. `reserved` is not on the list on
# purpose: it has to be backed by a real reservation, so it is only ever
# worked out (see RequirementProgress.status). `cancelled` belongs to the
# event, not to a requirement. `rejected` is stored as it is and shown as
# "Unavailable" -- the shared enum is not extended for one feature.
TECH_SUPPORT_STATUSES: tuple[EquipmentStatus, ...] = (
    EquipmentStatus.requested,
    EquipmentStatus.reviewing,
    EquipmentStatus.rejected,
)


def checked_quantity(quantity: object) -> int:
    """A quantity needed: a whole number, at least 1."""
    # bool is an int subclass; True is not "1 of something".
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
        raise InvalidInput("Quantity must be at least 1.", field="quantity_needed")
    return quantity


@dataclass(frozen=True)
class ReservedItem:
    """One item reserved towards a requirement."""

    equipment_id: int
    equipment_name: str
    quantity: int


@dataclass(frozen=True)
class RequirementProgress:
    """A requirement's quantities and status, as one immutable fact.

    `needed` is the Coordinator's and is never written by a reservation.
    `reserved` is what the reservations add up to. 5 needed / 3 reserved is a
    normal state, and stays distinguishable.
    """

    needed: int
    stored_status: EquipmentStatus
    reservations: tuple[ReservedItem, ...] = ()

    @property
    def reserved(self) -> int:
        return sum(item.quantity for item in self.reservations)

    @property
    def remaining(self) -> int:
        return max(self.needed - self.reserved, 0)

    @property
    def status(self) -> EquipmentStatus:
        """The status everyone sees.

        Reserved is worked out, not stored: it means the reservations cover
        what is needed. Some reserved but not all is work in progress, so it
        reads Reviewing, whatever was set by hand. With nothing reserved, the
        status is the one Technical Support set -- and a stored `reserved`
        with nothing behind it is not believed.
        """
        if self.reserved >= self.needed:
            return EquipmentStatus.reserved
        if self.reserved > 0:
            return EquipmentStatus.reviewing
        if self.stored_status in TECH_SUPPORT_STATUSES:
            return self.stored_status
        return EquipmentStatus.requested

    def check_new_quantity(self, quantity: object) -> int:
        """`quantity` as the new quantity needed, if it can be.

        Not below what is already reserved: there is no way to give a
        reservation back, so needing less than is held would leave stock
        committed to nothing.
        """
        quantity = checked_quantity(quantity)
        if quantity < self.reserved:
            raise Conflict(
                f"{self.reserved} already reserved; the quantity needed cannot be less than that.",
                field="quantity_needed",
            )
        return quantity


class RequirementReservationLinks:
    """Which reserved items fulfil which requirement.

    Reads only. The one write, `claim`, adds a pending link and leaves the
    session alone: it is committed by the reservation's own commit, which is
    what makes the link and the reservation a single transaction.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def progress_for(self, requirement: CoordinatorEquipmentRequirement) -> RequirementProgress:
        return self.progress_of([requirement])[requirement.id]

    def progress_of(
        self, requirements: Sequence[CoordinatorEquipmentRequirement]
    ) -> dict[int, RequirementProgress]:
        """Progress for each requirement, read in one query.

        A link only counts while the reservation behind it exists: the join
        to a RESERVED equipment_requests row is what makes an approved
        Organiser change -- which rebuilds those rows -- reduce progress
        instead of leaving a stale figure behind.
        """
        by_requirement: dict[int, list[ReservedItem]] = {r.id: [] for r in requirements}
        if not by_requirement:
            return {}
        rows = self._db.execute(
            select(
                RequirementReservationLink.requirement_id,
                Equipment.id,
                Equipment.name,
                EquipmentRequest.quantity_requested,
            )
            .join(
                EquipmentRequest,
                and_(
                    EquipmentRequest.event_id == RequirementReservationLink.event_id,
                    EquipmentRequest.equipment_id == RequirementReservationLink.equipment_id,
                ),
            )
            .join(Equipment, Equipment.id == RequirementReservationLink.equipment_id)
            .where(
                RequirementReservationLink.requirement_id.in_(by_requirement),
                EquipmentRequest.status == EquipmentStatus.reserved,
            )
            .order_by(RequirementReservationLink.id)
        ).all()
        for requirement_id, equipment_id, name, quantity in rows:
            by_requirement[requirement_id].append(ReservedItem(equipment_id, name, quantity))
        return {
            r.id: RequirementProgress(
                needed=r.quantity_needed,
                stored_status=r.status,
                reservations=tuple(by_requirement[r.id]),
            )
            for r in requirements
        }

    def claim(self, requirement: CoordinatorEquipmentRequirement, equipment_id: int) -> None:
        """Say that `equipment_id` is about to be reserved for `requirement`.

        Adds the link to the session without committing it. If the item
        already fulfils another requirement of the event, that is refused --
        unless nothing is reserved behind that link any more (the Organiser's
        change wiped it), in which case the stale link is taken over.
        """
        existing = self._db.scalar(
            select(RequirementReservationLink).where(
                RequirementReservationLink.event_id == requirement.event_id,
                RequirementReservationLink.equipment_id == equipment_id,
            )
        )
        if existing is None:
            self._db.add(
                RequirementReservationLink(
                    requirement_id=requirement.id,
                    event_id=requirement.event_id,
                    equipment_id=equipment_id,
                )
            )
        elif existing.requirement_id == requirement.id:
            return
        elif self._is_reserved(existing):
            raise Conflict(
                "That item is already reserved for another requirement of this event.",
                field="equipment_id",
            )
        else:
            existing.requirement_id = requirement.id

    def _is_reserved(self, link: RequirementReservationLink) -> bool:
        return (
            self._db.scalar(
                select(EquipmentRequest.id).where(
                    EquipmentRequest.event_id == link.event_id,
                    EquipmentRequest.equipment_id == link.equipment_id,
                    EquipmentRequest.status == EquipmentStatus.reserved,
                )
            )
            is not None
        )
