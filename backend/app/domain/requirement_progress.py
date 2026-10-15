"""How far a Coordinator's requirement has got, and where that is read from.

    RequirementStatus           the four statuses people see (DoD 11b)
    RequirementProgress         a value object: what is needed, what has been
                                reserved, what Technical Support set -- and
                                from those, the one status everybody sees
    RequirementReservationLinks the repository: which reserved items fulfil
                                which requirement

The statuses are the Definition of Done's, and only those:

    Requested    waiting for Technical Support. That includes a requirement
                 only PART reserved: the DoD has no "in progress", so what is
                 reserved so far is shown as a figure beside Requested
    Reserved     the full quantity is reserved. Never set by hand
    Unavailable  Technical Support cannot provide it; a reason is required
    Available    its reservation was freed because the event is over. Never
                 set by hand

Reserved and Available are worked out, never stored. Unavailable is stored in
the shared enum's existing `rejected` value, which nothing else here uses:
adding a value to an enum that Ercong's table shares is not done for one
feature. A stored `reviewing` -- what "In review" used to save -- reads as
Requested.

A requirement's reserved quantity is the sum of the reserved equipment_requests
rows its links point at, read fresh every time, so it can never disagree with
the reservations themselves -- which belong to Ercong's feature and are not
touched here.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.core.datetimes import as_utc
from app.domain.activity_log import ActivityLog
from app.domain.errors import Conflict, InvalidInput
from app.models.enums import EquipmentStatus
from app.models.equipment import (
    CoordinatorEquipmentRequirement,
    Equipment,
    EquipmentRequest,
    RequirementReservationLink,
)
from app.models.events import Event
from app.models.user import User


class RequirementStatus(StrEnum):
    """What a requirement is, in the Definition of Done's words (11b)."""

    REQUESTED = "requested"
    RESERVED = "reserved"
    UNAVAILABLE = "unavailable"
    AVAILABLE = "available"


# What Technical Support may set by hand. Reserved is not on the list on
# purpose: it has to be backed by a real reservation. Available is not either:
# it is a reservation freed, which is the event ending, not a decision.
TECH_SUPPORT_STATUSES: tuple[RequirementStatus, ...] = (
    RequirementStatus.REQUESTED,
    RequirementStatus.UNAVAILABLE,
)

# How Unavailable is stored: the shared enum's `rejected`.
STORED_UNAVAILABLE = EquipmentStatus.rejected


def checked_quantity(quantity: object) -> int:
    """A quantity needed: a whole number, at least 1."""
    # bool is an int subclass; True is not "1 of something".
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
        raise InvalidInput("Quantity must be at least 1.", field="quantity_needed")
    return quantity


def checked_reason(reason: object) -> str:
    """Why Technical Support cannot provide the equipment (DoD 11b: required).
    Spaces are not a reason."""
    if not isinstance(reason, str) or not reason.strip():
        raise InvalidInput("Give a reason the equipment is unavailable.", field="reason")
    return reason.strip()


@dataclass(frozen=True)
class ReservedItem:
    """One item reserved towards a requirement, and where it will be placed."""

    equipment_id: int
    equipment_name: str
    quantity: int
    # Where the item will be set up at the venue: recorded by Technical Support
    # when they reserve, and read by the Safety Officer. It lives on the
    # reservation, so a requirement not yet reserved has none.
    placement_notes: str | None = None


@dataclass(frozen=True)
class RequirementProgress:
    """A requirement's quantities and status, as one immutable fact.

    `needed` is the Coordinator's and is never written by a reservation.
    `reserved` is what the reservations hold NOW; once they are freed (the
    event is over) it is 0, and `was_reserved` is what was freed. 5 needed /
    3 reserved is a normal state, and stays distinguishable.
    """

    needed: int
    stored_status: EquipmentStatus
    reservations: tuple[ReservedItem, ...] = ()
    # True once the reservations no longer hold stock: the event has ended.
    released: bool = False
    unavailable_reason: str | None = None

    @property
    def was_reserved(self) -> int:
        return sum(item.quantity for item in self.reservations)

    @property
    def reserved(self) -> int:
        return 0 if self.released else self.was_reserved

    @property
    def remaining(self) -> int:
        return max(self.needed - self.reserved, 0)

    @property
    def status(self) -> RequirementStatus:
        """The status everyone sees.

        Available: it had equipment reserved, and that was freed. Reserved:
        the reservations cover what is needed. Unavailable: Technical Support
        said so, and nothing is reserved. Anything else is Requested -- still
        waiting for Technical Support, whether or not part of it is reserved.
        A stored `reserved` with nothing behind it is not believed.
        """
        if self.released and self.was_reserved > 0:
            return RequirementStatus.AVAILABLE
        if self.reserved > 0 and self.reserved >= self.needed:
            return RequirementStatus.RESERVED
        if self.reserved == 0 and self.stored_status is STORED_UNAVAILABLE:
            return RequirementStatus.UNAVAILABLE
        return RequirementStatus.REQUESTED

    def check_new_quantity(self, quantity: object) -> int:
        """`quantity` as the new quantity needed, if it can be.

        Not below what is reserved: there is no way to give a reservation
        back, so needing less than is held would leave stock committed to
        nothing.
        """
        quantity = checked_quantity(quantity)
        if quantity < self.reserved:
            raise Conflict(
                f"{self.reserved} already reserved; the quantity needed cannot be less than that.",
                field="quantity_needed",
            )
        return quantity


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RequirementReservationLinks:
    """Which reserved items fulfil which requirement.

    Reads only. The one write, `claim`, adds a pending link and leaves the
    session alone: it is committed by the reservation's own commit, which is
    what makes the link and the reservation a single transaction.

    The clock is handed in so "the event is over" can be tested.
    """

    def __init__(self, db: Session, clock: Callable[[], datetime] | None = None) -> None:
        self._db = db
        self._clock = clock if clock is not None else _utcnow

    def progress_for(self, requirement: CoordinatorEquipmentRequirement) -> RequirementProgress:
        return self.progress_of([requirement])[requirement.id]

    def progress_of(
        self, requirements: Sequence[CoordinatorEquipmentRequirement]
    ) -> dict[int, RequirementProgress]:
        """Progress for each requirement, read in two queries.

        A link only counts while the reservation behind it exists: the join
        to a RESERVED equipment_requests row is what makes an approved
        Organiser change -- which rebuilds those rows -- reduce progress
        instead of leaving a stale figure behind. A reservation holds its
        stock until its event's end time (his rule), so after that it reads
        as freed.
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
                EquipmentRequest.placement_notes,
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
        for requirement_id, equipment_id, name, quantity, placement in rows:
            by_requirement[requirement_id].append(ReservedItem(equipment_id, name, quantity, placement))

        ends = dict(
            self._db.execute(
                select(Event.id, Event.proposed_end).where(
                    Event.id.in_({r.event_id for r in requirements})
                )
            ).all()
        )
        now = self._clock()
        return {
            r.id: RequirementProgress(
                needed=r.quantity_needed,
                stored_status=r.status,
                reservations=tuple(by_requirement[r.id]),
                released=ends.get(r.event_id) is not None and as_utc(ends[r.event_id]) <= now,
                unavailable_reason=r.unavailable_reason,
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


_LABELS = {
    RequirementStatus.REQUESTED: "Requested",
    RequirementStatus.RESERVED: "Reserved",
    RequirementStatus.UNAVAILABLE: "Unavailable",
    RequirementStatus.AVAILABLE: "Available",
}


class RequirementStatusLog:
    """Records a requirement's status change in the Activity Log (DoD 11).

    Handed the log it writes to, so the rule -- a change is recorded, with who
    made it and the reason when it is Unavailable; no change records nothing --
    stands on its own. The status is the one everybody sees, so a quantity
    raised over what is reserved, or the last unit being reserved, counts: not
    only what Technical Support chooses.
    """

    def __init__(self, activity: ActivityLog) -> None:
        self._activity = activity

    def record(
        self,
        event: Event,
        actor: User,
        requirement: CoordinatorEquipmentRequirement,
        before: RequirementStatus,
        after: RequirementStatus,
        *,
        by: str,
        reason: str | None = None,
    ) -> None:
        if before is after:
            return
        note = (
            f"Equipment requirement '{requirement.category}' changed from "
            f"{_LABELS[before]} to {_LABELS[after]} by {by}."
        )
        if after is RequirementStatus.UNAVAILABLE and reason:
            note += f" Reason: {reason}"
        self._activity.record(event, actor, note)
