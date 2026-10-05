"""Unit tests for the equipment requirement domain classes.

test_equipment_requirements.py proves the behaviour through HTTP. These
call the classes directly, with no web layer at all, to show the business
rules live in the domain rather than in the routers:

    DomainError (+ NotFound, Conflict, InvalidInput, Forbidden)
        What went wrong, independent of HTTP. One exception handler maps the
        hierarchy to status codes, so no rule ever imports HTTPException.

    CategoryResolver (a Protocol) / CatalogueCategories
        How a typed category becomes a catalogue category. The service
        depends on the Protocol, so a test can hand it a fake and the
        category rule is exercised without a catalogue table.

    EquipmentRequirementService
        The Coordinator's side: add, edit, remove, list.

    TechSupportRequirementReader
        Technical Support's side, read-only.
"""

import itertools

import pytest

from app.core.roles import Role
from app.domain.equipment_requirements import (
    EQUIPMENT_ACTIVE_STATUSES,
    CatalogueCategories,
    EquipmentRequirementService,
    TechSupportRequirementReader,
)
from app.domain.errors import Conflict, DomainError, Forbidden, InvalidInput, NotFound
from app.models.enums import EquipmentOperationalStatus, EventStatus
from app.models.equipment import CoordinatorEquipmentRequirement, Equipment
from app.models.events import Event
from app.models.user import User

_unique = itertools.count()


def _user(db_session, role: Role) -> User:
    user = User(
        name=role.value.title(),
        email=f"{role.value}{next(_unique)}@example.com",
        password_hash="x",
        role=role.value,
    )
    db_session.add(user)
    db_session.flush()
    return user


def _event(db_session, organiser, coordinator, status=EventStatus.approved) -> Event:
    event = Event(
        name="An event", organiser_id=organiser.id, coordinator_id=coordinator.id, status=status
    )
    db_session.add(event)
    db_session.flush()
    return event


def _catalogue(db_session, *categories: str) -> None:
    for i, category in enumerate(categories):
        db_session.add(
            Equipment(
                name=f"Item {i} {category}",
                category=category,
                total_quantity=5,
                operational_status=EquipmentOperationalStatus.available,
            )
        )
    db_session.flush()


class _FixedCategories:
    """A stand-in resolver: knows exactly one category, and needs no database."""

    def resolve(self, category: str) -> str | None:
        return "Staging" if category.strip().lower() == "staging" else None


# --- the error hierarchy ----------------------------------------------------


@pytest.mark.parametrize(
    "error,status_code",
    [(NotFound, 404), (Conflict, 409), (InvalidInput, 422), (Forbidden, 403)],
)
def test_each_domain_error_knows_its_own_http_status(error, status_code):
    """The status belongs to the error class, so adding a new kind of error
    is one subclass -- the handler never changes (polymorphism)."""
    assert issubclass(error, DomainError)
    assert error("message").status_code == status_code


def test_an_invalid_input_error_can_name_the_field_at_fault():
    error = InvalidInput("Choose a type from the catalogue.", field="category")

    assert error.field == "category"
    assert str(error) == "Choose a type from the catalogue."


def test_other_errors_name_no_field():
    assert NotFound("Event not found").field is None


# --- the status window ------------------------------------------------------


def test_equipment_is_recordable_exactly_while_approved_planning_or_confirmed():
    """One constant, used by the Coordinator's side and Technical Support's
    side alike, so they can never disagree about where requirements live."""
    assert set(EQUIPMENT_ACTIVE_STATUSES) == {
        EventStatus.approved,
        EventStatus.planning,
        EventStatus.confirmed,
    }


# --- the Coordinator's service ---------------------------------------------


def test_the_service_records_a_requirement_without_any_web_layer(db_session):
    organiser, coordinator = _user(db_session, Role.ORGANISER), _user(db_session, Role.COORDINATOR)
    _catalogue(db_session, "Audio")
    event = _event(db_session, organiser, coordinator)
    service = EquipmentRequirementService(db_session)

    requirement = service.add(
        event.id, coordinator.id, category="audio", quantity_needed=6, technical_notes="Wireless"
    )

    assert (requirement.category, requirement.quantity_needed) == ("Audio", 6)
    assert requirement.created_by == coordinator.id


def test_the_service_takes_its_category_rule_as_a_dependency(db_session):
    """Dependency injection: with a fake resolver the service accepts a
    category that is in no catalogue, because the rule is not its own."""
    organiser, coordinator = _user(db_session, Role.ORGANISER), _user(db_session, Role.COORDINATOR)
    event = _event(db_session, organiser, coordinator)
    service = EquipmentRequirementService(db_session, categories=_FixedCategories())

    requirement = service.add(event.id, coordinator.id, category="STAGING", quantity_needed=2)

    assert requirement.category == "Staging"


def test_the_default_dependency_is_the_catalogue(db_session):
    _catalogue(db_session, "Audio", "Lighting")

    assert CatalogueCategories(db_session).resolve(" lighting ") == "Lighting"
    assert CatalogueCategories(db_session).resolve("Pyrotechnics") is None


def test_the_service_raises_domain_errors_never_http_exceptions(db_session):
    organiser, coordinator = _user(db_session, Role.ORGANISER), _user(db_session, Role.COORDINATOR)
    stranger = _user(db_session, Role.COORDINATOR)
    _catalogue(db_session, "Audio")
    event = _event(db_session, organiser, coordinator)
    service = EquipmentRequirementService(db_session)

    with pytest.raises(NotFound):
        service.add(event.id, stranger.id, category="Audio", quantity_needed=1)
    with pytest.raises(InvalidInput) as unknown:
        service.add(event.id, coordinator.id, category="Pyrotechnics", quantity_needed=1)
    assert unknown.value.field == "category"
    with pytest.raises(InvalidInput) as zero:
        service.add(event.id, coordinator.id, category="Audio", quantity_needed=0)
    assert zero.value.field == "quantity_needed"


@pytest.mark.parametrize("status", [s for s in EventStatus if s not in EQUIPMENT_ACTIVE_STATUSES])
def test_the_service_refuses_to_record_outside_the_window(db_session, status):
    organiser, coordinator = _user(db_session, Role.ORGANISER), _user(db_session, Role.COORDINATOR)
    _catalogue(db_session, "Audio")
    event = _event(db_session, organiser, coordinator, status=status)

    with pytest.raises(Conflict):
        EquipmentRequirementService(db_session).add(
            event.id, coordinator.id, category="Audio", quantity_needed=1
        )


def test_the_service_edits_and_removes(db_session):
    organiser, coordinator = _user(db_session, Role.ORGANISER), _user(db_session, Role.COORDINATOR)
    _catalogue(db_session, "Audio")
    event = _event(db_session, organiser, coordinator)
    service = EquipmentRequirementService(db_session)
    requirement = service.add(event.id, coordinator.id, category="Audio", quantity_needed=1)

    service.edit(requirement.id, coordinator.id, quantity_needed=4)
    assert service.list_for_coordinator(event.id, coordinator.id)[0].quantity_needed == 4

    service.remove(requirement.id, coordinator.id)
    assert service.list_for_coordinator(event.id, coordinator.id) == []


def test_editing_with_no_changes_changes_nothing(db_session):
    """An empty edit is not an error and not a write."""
    organiser, coordinator = _user(db_session, Role.ORGANISER), _user(db_session, Role.COORDINATOR)
    _catalogue(db_session, "Audio")
    event = _event(db_session, organiser, coordinator)
    service = EquipmentRequirementService(db_session)
    requirement = service.add(event.id, coordinator.id, category="Audio", quantity_needed=3)

    unchanged = service.edit(requirement.id, coordinator.id)

    assert (unchanged.category, unchanged.quantity_needed) == ("Audio", 3)


# --- Technical Support's reader ---------------------------------------------


def test_the_reader_lists_only_active_events_that_have_requirements(db_session):
    organiser, coordinator = _user(db_session, Role.ORGANISER), _user(db_session, Role.COORDINATOR)
    _catalogue(db_session, "Audio")
    approved = _event(db_session, organiser, coordinator)
    _event(db_session, organiser, coordinator)  # approved, but nothing recorded
    under_review = _event(db_session, organiser, coordinator, status=EventStatus.under_review)
    EquipmentRequirementService(db_session).add(
        approved.id, coordinator.id, category="Audio", quantity_needed=1
    )
    # The service would refuse this one, so it goes in directly: the point is
    # that even a requirement that exists is not shown for an event outside
    # the window.
    db_session.add(
        CoordinatorEquipmentRequirement(
            event_id=under_review.id, category="Audio", quantity_needed=1,
            created_by=coordinator.id,
        )
    )
    db_session.flush()

    listed = TechSupportRequirementReader(db_session).events()

    assert [(event.id, count) for event, count in listed] == [(approved.id, 1)]


def test_the_reader_refuses_events_outside_the_window(db_session):
    organiser, coordinator = _user(db_session, Role.ORGANISER), _user(db_session, Role.COORDINATOR)
    draft = _event(db_session, organiser, coordinator, status=EventStatus.draft)

    with pytest.raises(NotFound):
        TechSupportRequirementReader(db_session).event(draft.id)
