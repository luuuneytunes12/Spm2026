"""The rules for recording equipment requirements, and for reading them.

Two sides of one subject, kept as two classes because they have different
reasons to change:

    EquipmentRequirementService   the Event Coordinator's side -- add, edit,
                                  remove, list. All the write rules.
    TechSupportRequirementReader  Technical Support's side -- read-only.

and one collaborator the service is handed rather than building for itself:

    CategoryResolver (a Protocol)  how a typed category becomes a catalogue
                                   category. The service depends on this
                                   interface, not on the equipment table.

Neither class commits, nor knows about HTTP. They raise DomainError
subclasses; the router commits (the same convention as
app/services/assignment.py) and one handler maps errors to status codes.
"""

from collections.abc import Sequence
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.errors import Conflict, InvalidInput, NotFound
from app.domain.requirement_progress import RequirementReservationLinks, checked_quantity
from app.models.enums import EventStatus
from app.models.equipment import CoordinatorEquipmentRequirement, Equipment, EquipmentRequest
from app.models.events import Event

# The statuses in which equipment is recorded, and in which Technical
# Support looks. ONE list for both sides, so a requirement can never sit
# somewhere Technical Support is not looking.
#
# PROVISIONAL. Neither the Week 1 briefing nor the Week 4 instructions say
# when equipment may be recorded. This window is inferred:
#   * W4 p3: the Coordinator can "view and update relevant event
#     information during the planning process"
#   * W1 Step 8 (Technical Requirements) comes after Step 5 (Initial
#     Approval)
#   * W1 p3: equipment changes keep arriving "even after it has been
#     confirmed"
# and recording is excluded once an event is completed, cancelled or
# rejected (W1 p8: reservations must not stay committed to a cancelled
# event). To be confirmed with the customer in Q&A; changing it is this one
# line plus the status-by-status test cases.
EQUIPMENT_ACTIVE_STATUSES: tuple[EventStatus, ...] = (
    EventStatus.approved,
    EventStatus.planning,
    EventStatus.confirmed,
)

# The fields an edit may change. The link to an Organiser's pick is a fact
# about where a requirement came from, so it is set once, at creation.
_EDITABLE_FIELDS = frozenset({"category", "quantity_needed", "technical_notes"})


class CategoryResolver(Protocol):
    """Turns what a person typed into a category the catalogue knows."""

    def resolve(self, category: str) -> str | None:
        """The catalogue's own spelling of `category`, or None if it has none."""
        ...


class CatalogueCategories:
    """The real resolver: a category is valid if some catalogue item has it.

    Matched ignoring case and surrounding spaces, and returned in the
    catalogue's own spelling, so "audio" and "Audio" can never become two
    different types. Retired items count -- the category exists as long as
    the catalogue records it.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def resolve(self, category: str) -> str | None:
        wanted = category.strip().casefold()
        if not wanted:
            return None
        recorded = self._db.scalars(
            select(Equipment.category).where(Equipment.category.is_not(None)).distinct()
        )
        # Sorted, so that if the catalogue holds both "Audio" and "audio"
        # the answer is stable rather than whichever the database returned.
        for candidate in sorted(recorded):
            if candidate.strip().casefold() == wanted:
                return candidate
        return None


class EquipmentRequirementService:
    """The Event Coordinator's equipment requirements for their events.

    Every rule about who may record what, and when, lives here and nowhere
    else: the routers only parse input and call these methods. The category
    rule is injected, so it can be swapped -- for a fake in a test, or for a
    stricter resolver later -- without touching this class.
    """

    def __init__(
        self,
        db: Session,
        categories: CategoryResolver | None = None,
        links: RequirementReservationLinks | None = None,
    ) -> None:
        self._db = db
        self._categories = categories if categories is not None else CatalogueCategories(db)
        # How much of a requirement is reserved, for the rules that protect it
        # once Technical Support has reserved equipment against it.
        self._links = links if links is not None else RequirementReservationLinks(db)

    # --- commands -----------------------------------------------------------

    def add(
        self,
        event_id: int,
        coordinator_id: int,
        *,
        category: str,
        quantity_needed: int,
        technical_notes: str | None = None,
        organiser_equipment_request_id: int | None = None,
    ) -> CoordinatorEquipmentRequirement:
        event = self._own_event(event_id, coordinator_id)
        self._ensure_recordable(event)

        requirement = CoordinatorEquipmentRequirement(
            event_id=event.id,
            organiser_equipment_request_id=self._checked_pick(event, organiser_equipment_request_id),
            category=self._checked_category(category),
            quantity_needed=self._checked_quantity(quantity_needed),
            technical_notes=self._checked_notes(technical_notes),
            created_by=coordinator_id,
        )
        self._db.add(requirement)
        self._db.flush()
        return requirement

    def edit(
        self, requirement_id: int, coordinator_id: int, **changes: object
    ) -> CoordinatorEquipmentRequirement:
        """Change a requirement. Fields not mentioned are left alone; an
        explicit None clears the notes. An empty edit is not a write."""
        unknown = set(changes) - _EDITABLE_FIELDS
        if unknown:
            raise TypeError(f"Not editable: {', '.join(sorted(unknown))}")

        requirement, event = self._own_requirement(requirement_id, coordinator_id)
        self._ensure_recordable(event)
        progress = self._links.progress_for(requirement)

        if "category" in changes:
            category = self._checked_category(changes["category"])
            # There is no way to give a reservation back, so once equipment is
            # reserved the type it was reserved as cannot be changed under it.
            # Sending the same type again (the edit form always does) is not
            # a change.
            if progress.reserved and category != requirement.category:
                raise Conflict(
                    "Equipment is already reserved for this requirement, "
                    "so its type cannot be changed.",
                    field="category",
                )
            requirement.category = category
        if "quantity_needed" in changes:
            # Not below what is reserved: it would leave stock committed to
            # a need that is no longer there.
            requirement.quantity_needed = progress.check_new_quantity(changes["quantity_needed"])
        if "technical_notes" in changes:
            requirement.technical_notes = self._checked_notes(changes["technical_notes"])

        self._db.flush()
        return requirement

    def remove(self, requirement_id: int, coordinator_id: int) -> None:
        requirement, event = self._own_requirement(requirement_id, coordinator_id)
        self._ensure_recordable(event)
        if self._links.progress_for(requirement).reserved:
            # Nothing can release a reservation, so deleting the requirement
            # would leave equipment held for a need that no longer exists.
            raise Conflict(
                "Equipment is already reserved for this requirement, so it cannot be removed."
            )
        self._db.delete(requirement)
        self._db.flush()

    # --- queries ------------------------------------------------------------

    def list_for_coordinator(
        self, event_id: int, coordinator_id: int
    ) -> list[CoordinatorEquipmentRequirement]:
        """An event's requirements, oldest first.

        Readable whatever the event's status: recording stops outside the
        window, but a completed event's requirements are still its record.
        """
        event = self._own_event(event_id, coordinator_id)
        return list(
            self._db.scalars(
                select(CoordinatorEquipmentRequirement)
                .where(CoordinatorEquipmentRequirement.event_id == event.id)
                .order_by(CoordinatorEquipmentRequirement.id)
            )
        )

    # --- rules --------------------------------------------------------------

    def _own_event(self, event_id: int, coordinator_id: int) -> Event:
        """The event, if it is assigned to this Coordinator.

        Anything else is NotFound -- "not yours" and "does not exist" must
        look the same, or ids could be probed.
        """
        event = self._db.get(Event, event_id)
        if event is None or event.coordinator_id != coordinator_id:
            raise NotFound("Event not found")
        return event

    def _own_requirement(
        self, requirement_id: int, coordinator_id: int
    ) -> tuple[CoordinatorEquipmentRequirement, Event]:
        requirement = self._db.get(CoordinatorEquipmentRequirement, requirement_id)
        if requirement is None:
            raise NotFound("Requirement not found")
        event = self._db.get(Event, requirement.event_id)
        if event is None or event.coordinator_id != coordinator_id:
            raise NotFound("Requirement not found")
        return requirement, event

    @staticmethod
    def _ensure_recordable(event: Event) -> None:
        if event.status not in EQUIPMENT_ACTIVE_STATUSES:
            raise Conflict(
                "Equipment can only be recorded once the event is approved; "
                f"it is '{event.status}'."
            )

    def _checked_category(self, category: object) -> str:
        resolved = self._categories.resolve(category) if isinstance(category, str) else None
        if resolved is None:
            raise InvalidInput("Choose an equipment type from the catalogue.", field="category")
        return resolved

    @staticmethod
    def _checked_quantity(quantity: object) -> int:
        return checked_quantity(quantity)

    @staticmethod
    def _checked_notes(notes: object) -> str | None:
        """Spaces are not a note, and should not read as one on screen."""
        if notes is None:
            return None
        if not isinstance(notes, str):
            raise InvalidInput("Notes must be text.", field="technical_notes")
        return notes.strip() or None

    def _checked_pick(self, event: Event, pick_id: int | None) -> int | None:
        """The link says "this need came from that request", so it has to be
        a request for the same event."""
        if pick_id is None:
            return None
        pick = self._db.get(EquipmentRequest, pick_id)
        if pick is None or pick.event_id != event.id:
            raise InvalidInput(
                "That is not one of this event's requested items.",
                field="organiser_equipment_request_id",
            )
        return pick.id


class TechSupportRequirementReader:
    """What Technical Support sees: the events with requirements to review,
    and each one's record.

    Read-only, and scoped by event status rather than by owner -- unlike the
    Coordinator, Technical Support reviews equipment across every event.
    Drafts and events not yet approved are never shown.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def events(self) -> list[tuple[Event, int]]:
        """Events in the window that have at least one requirement, soonest
        first, each with how many it has. Undated events come last."""
        count = func.count(CoordinatorEquipmentRequirement.id)
        rows = self._db.execute(
            select(Event, count)
            .join(CoordinatorEquipmentRequirement, CoordinatorEquipmentRequirement.event_id == Event.id)
            .where(Event.status.in_(EQUIPMENT_ACTIVE_STATUSES))
            .group_by(Event.id)
            .order_by(Event.proposed_start.is_(None), Event.proposed_start, Event.id)
        ).all()
        return [(event, total) for event, total in rows]

    def event(self, event_id: int) -> tuple[Event, Sequence[CoordinatorEquipmentRequirement]]:
        """One event and its requirements.

        Available even before anything is recorded -- the event is
        something Technical Support can open; the list just does not offer
        it. Outside the window it is NotFound, indistinguishable from an
        event that does not exist.
        """
        event = self._db.get(Event, event_id)
        if event is None or event.status not in EQUIPMENT_ACTIVE_STATUSES:
            raise NotFound("Event not found")
        requirements = self._db.scalars(
            select(CoordinatorEquipmentRequirement)
            .where(CoordinatorEquipmentRequirement.event_id == event.id)
            .order_by(CoordinatorEquipmentRequirement.id)
        ).all()
        return event, requirements
