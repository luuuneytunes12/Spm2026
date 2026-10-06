"""Unit tests for the classes behind "Update Equipment Requirement Status".

test_equipment_requirement_fulfillment.py proves the behaviour through HTTP
against Ercong's real reservation function. These call the classes
directly, with no web layer, to show where the rules live:

    RequirementProgress (value object)
        needed + reserved + the status Technical Support set -> the status
        everyone sees. `reserved` is never stored: it is what the
        reservations say.

    ReservationGateway (abstract)
        What the orchestration needs from a reservation capability.
            ErcongReservationGateway   production: delegates to his
                                       unchanged reserve_equipment
            FakeReservationGateway     below: records calls, needs no
                                       reservation rules at all
        The service is handed one; it never knows which. That is the
        polymorphism, and it is why these tests need no stock arithmetic.

    RequirementReservationLinks (repository)
        Which reserved items fulfil which requirement.

    EquipmentRequirementFulfillmentService
        The rules and the orchestration, with the gateway injected.
"""

import itertools

import pytest

from app.core.roles import Role
from app.domain.equipment_fulfillment import (
    TECH_SUPPORT_STATUSES,
    EquipmentRequirementFulfillmentService,
    RequirementProgress,
    RequirementReservationLinks,
    ReservationGateway,
    ReservationRefused,
    ReservedItem,
)
from app.domain.equipment_requirements import EQUIPMENT_ACTIVE_STATUSES
from app.domain.errors import Conflict, DomainError, InvalidInput, NotFound
from app.models.enums import PLANNED_EVENT_STATUSES, EquipmentStatus, EventStatus
from app.models.equipment import (
    CoordinatorEquipmentRequirement,
    Equipment,
    EquipmentRequest,
    RequirementReservationLink,
)
from app.models.events import Event
from app.models.user import User
from app.services.reservation_gateway import ErcongReservationGateway
from datetime import datetime, timezone

START = datetime(2026, 11, 2, 9, tzinfo=timezone.utc)
END = datetime(2026, 11, 2, 17, tzinfo=timezone.utc)
_unique = itertools.count()

REQUESTED, REVIEWING = EquipmentStatus.requested, EquipmentStatus.reviewing
RESERVED, REJECTED = EquipmentStatus.reserved, EquipmentStatus.rejected


def _items(*quantities: int) -> tuple[ReservedItem, ...]:
    return tuple(ReservedItem(equipment_id=i + 1, equipment_name=f"Item {i + 1}", quantity=q)
                 for i, q in enumerate(quantities))


def _progress(needed, *reserved, status=REQUESTED) -> RequirementProgress:
    return RequirementProgress(needed=needed, stored_status=status, reservations=_items(*reserved))


# ---------------------------------------------------------------------------
# RequirementProgress -- the effective status
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "needed,reserved,stored,effective",
    [
        # nothing reserved: what Technical Support set is what it is
        (5, [], REQUESTED, REQUESTED),
        (5, [], REVIEWING, REVIEWING),
        (5, [], REJECTED, REJECTED),
        # some reserved: work is under way, whatever was stored
        (5, [3], REQUESTED, REVIEWING),
        (5, [1], REJECTED, REVIEWING),
        (5, [2, 2], REVIEWING, REVIEWING),
        # all of it reserved, in one item or several
        (5, [5], REQUESTED, RESERVED),
        (5, [3, 2], REVIEWING, RESERVED),
        # more reserved than needed still counts as covered
        (2, [4], REQUESTED, RESERVED),
    ],
)
def test_the_effective_status_follows_the_reservations(needed, reserved, stored, effective):
    assert _progress(needed, *reserved, status=stored).status is effective


def test_reserved_is_never_taken_from_what_was_stored():
    """Nothing reserved means nothing is reserved, whatever the column says."""
    assert _progress(5, status=RESERVED).status is REQUESTED


def test_reserved_and_remaining_come_from_the_reserved_items():
    progress = _progress(5, 3)
    assert (progress.reserved, progress.remaining) == (3, 2)


def test_remaining_never_goes_below_zero():
    assert _progress(2, 4).remaining == 0


def test_a_quantity_below_what_is_reserved_is_refused():
    with pytest.raises(Conflict) as refused:
        _progress(5, 3).check_new_quantity(2)
    assert refused.value.field == "quantity_needed"
    assert "3" in refused.value.message


@pytest.mark.parametrize("quantity", [3, 4, 100])
def test_a_quantity_at_or_above_what_is_reserved_is_allowed(quantity):
    _progress(5, 3).check_new_quantity(quantity)


def test_any_quantity_is_allowed_while_nothing_is_reserved():
    _progress(5).check_new_quantity(1)


def test_technical_support_may_set_requested_reviewing_and_rejected_only():
    """Reserved comes from reservations; cancelled belongs to the event."""
    assert set(TECH_SUPPORT_STATUSES) == {REQUESTED, REVIEWING, REJECTED}


# ---------------------------------------------------------------------------
# The two rules that must not drift from Ercong's feature
# ---------------------------------------------------------------------------


def test_the_window_for_recording_is_the_window_for_reserving():
    """His reserve refuses an event outside PLANNED_EVENT_STATUSES. A
    requirement shown to Technical Support must be in the same window, or the
    Reserve button would lead to a refusal for a reason it never mentioned."""
    assert tuple(EQUIPMENT_ACTIVE_STATUSES) == tuple(PLANNED_EVENT_STATUSES)


# ---------------------------------------------------------------------------
# Database-backed fixtures
# ---------------------------------------------------------------------------


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


@pytest.fixture()
def world(db_session):
    organiser, coordinator = _user(db_session, Role.ORGANISER), _user(db_session, Role.COORDINATOR)
    tech = _user(db_session, Role.TECH_SUPPORT)
    mic = Equipment(name="Shure BLX24", category="Audio", total_quantity=10)
    pa = Equipment(name="Yamaha PA", category="Audio", total_quantity=10)
    projector = Equipment(name="Epson", category="Projection", total_quantity=10)
    db_session.add_all([mic, pa, projector])
    event = Event(
        name="Conference",
        organiser_id=organiser.id,
        coordinator_id=coordinator.id,
        status=EventStatus.event_approved,
        proposed_start=START,
        proposed_end=END,
    )
    db_session.add(event)
    db_session.flush()
    requirement = CoordinatorEquipmentRequirement(
        event_id=event.id, category="Audio", quantity_needed=5, created_by=coordinator.id
    )
    db_session.add(requirement)
    db_session.commit()
    return type(
        "World", (), dict(tech=tech, mic=mic, pa=pa, projector=projector, event=event,
                          requirement=requirement, coordinator=coordinator),
    )


class FakeReservationGateway(ReservationGateway):
    """A reservation capability with no rules of its own.

    Records what it was asked, reserves exactly what it is told (or the
    forced quantity of an Organiser's line), and can be told to refuse. The
    orchestration is exercised without any stock, overlap or status logic --
    which is Ercong's, and has its own tests.
    """

    def __init__(self, db, *, forced=None, refuse=None):
        self._db = db
        self._forced = forced or {}
        self._refuse = refuse
        self.calls: list[dict] = []

    def forced_quantity(self, event_id, equipment_id):
        return self._forced.get((event_id, equipment_id))

    def reserve(self, *, event_id, equipment_id, quantity, user):
        self.calls.append(dict(event_id=event_id, equipment_id=equipment_id, quantity=quantity))
        if self._refuse:
            raise self._refuse
        taken = self._forced.get((event_id, equipment_id)) or quantity
        self._db.add(
            EquipmentRequest(
                event_id=event_id, equipment_id=equipment_id,
                quantity_requested=taken, status=EquipmentStatus.reserved,
            )
        )
        self._db.commit()  # his function commits; the fake behaves the same way
        return taken


def _service(db_session, gateway=None, **gateway_options):
    gateway = gateway or FakeReservationGateway(db_session, **gateway_options)
    return EquipmentRequirementFulfillmentService(db_session, gateway), gateway


def _links(db_session):
    return db_session.query(RequirementReservationLink).all()


# ---------------------------------------------------------------------------
# ReservationGateway -- the contract, and the two implementations of it
# ---------------------------------------------------------------------------


def test_a_gateway_cannot_be_used_without_implementing_the_contract():
    with pytest.raises(TypeError):
        ReservationGateway()  # abstract


def test_both_gateways_are_reservation_gateways():
    assert issubclass(ErcongReservationGateway, ReservationGateway)
    assert issubclass(FakeReservationGateway, ReservationGateway)


def test_the_service_runs_the_same_with_either_gateway(db_session, world):
    """Polymorphism: the service is given a gateway and asks it, nothing
    more. Swapping the implementation needs no change to the service."""
    for gateway in (FakeReservationGateway(db_session), ErcongReservationGateway(db_session)):
        assert isinstance(gateway, ReservationGateway)
        service = EquipmentRequirementFulfillmentService(db_session, gateway)
        _, progress = service.reserve(world.requirement.id, world.mic.id, 5, world.tech)
        assert progress.reserved == 5
        db_session.query(RequirementReservationLink).delete()
        db_session.query(EquipmentRequest).delete()
        db_session.commit()


def test_the_ercong_gateway_turns_his_refusals_into_domain_errors(db_session, world):
    """His function speaks HTTP. The domain does not: the adapter translates,
    keeping his status and his words, so the user sees what his own page
    would have said."""
    world.event.status = EventStatus.draft
    db_session.commit()

    with pytest.raises(ReservationRefused) as refused:
        ErcongReservationGateway(db_session).reserve(
            event_id=world.event.id, equipment_id=world.mic.id, quantity=1, user=world.tech
        )

    assert isinstance(refused.value, DomainError)
    assert refused.value.status_code == 409
    assert "approved" in refused.value.message


def test_the_ercong_gateway_reports_the_quantity_his_rule_would_force(db_session, world):
    """If the Organiser asked for the item, his reserve takes THEIR quantity
    and no other. The gateway says so up front, so a reservation that would
    over-fill a requirement can be refused before anything is written."""
    db_session.add(EquipmentRequest(event_id=world.event.id, equipment_id=world.mic.id, quantity_requested=4))
    db_session.commit()
    gateway = ErcongReservationGateway(db_session)

    assert gateway.forced_quantity(world.event.id, world.mic.id) == 4
    assert gateway.forced_quantity(world.event.id, world.pa.id) is None


# ---------------------------------------------------------------------------
# RequirementReservationLinks
# ---------------------------------------------------------------------------


def _reserved_row(db_session, world, item, quantity, status=EquipmentStatus.reserved):
    db_session.add(EquipmentRequest(
        event_id=world.event.id, equipment_id=item.id, quantity_requested=quantity, status=status))
    db_session.commit()


def _link(db_session, world, item, requirement=None):
    link = RequirementReservationLink(
        requirement_id=(requirement or world.requirement).id,
        event_id=world.event.id,
        equipment_id=item.id,
    )
    db_session.add(link)
    db_session.commit()
    return link


def test_progress_is_read_from_the_reserved_rows_the_links_point_at(db_session, world):
    _reserved_row(db_session, world, world.mic, 3)
    _link(db_session, world, world.mic)

    progress = RequirementReservationLinks(db_session).progress_for(world.requirement)

    assert progress.reserved == 3
    assert [(i.equipment_name, i.quantity) for i in progress.reservations] == [("Shure BLX24", 3)]


def test_a_link_with_no_reserved_row_behind_it_counts_for_nothing(db_session, world):
    """An approved Organiser change deletes and rebuilds the rows. The link
    to the item survives; the reservation did not, and progress says so."""
    _link(db_session, world, world.mic)  # no reserved row at all
    _reserved_row(db_session, world, world.pa, 2, status=EquipmentStatus.requested)
    _link(db_session, world, world.pa)  # a row, but not reserved

    assert RequirementReservationLinks(db_session).progress_for(world.requirement).reserved == 0


def test_progress_of_many_requirements_is_read_in_one_go(db_session, world):
    other = CoordinatorEquipmentRequirement(
        event_id=world.event.id, category="Audio", quantity_needed=2, created_by=world.coordinator.id
    )
    db_session.add(other)
    db_session.commit()
    _reserved_row(db_session, world, world.mic, 3)
    _link(db_session, world, world.mic)

    progress = RequirementReservationLinks(db_session).progress_of([world.requirement, other])

    assert progress[world.requirement.id].reserved == 3
    assert progress[other.id].reserved == 0


def test_claiming_an_item_adds_a_pending_link_and_commits_nothing(db_session, world):
    RequirementReservationLinks(db_session).claim(world.requirement, world.mic.id)

    assert len(db_session.new) == 1  # pending: the gateway's commit will write it
    db_session.rollback()
    assert _links(db_session) == []


def test_claiming_an_item_this_requirement_already_holds_adds_nothing_new(db_session, world):
    _link(db_session, world, world.mic)

    RequirementReservationLinks(db_session).claim(world.requirement, world.mic.id)

    assert len(db_session.new) == 0


def test_an_item_reserved_for_another_requirement_cannot_be_claimed(db_session, world):
    other = CoordinatorEquipmentRequirement(
        event_id=world.event.id, category="Audio", quantity_needed=2, created_by=world.coordinator.id
    )
    db_session.add(other)
    db_session.commit()
    _reserved_row(db_session, world, world.mic, 3)
    _link(db_session, world, world.mic, requirement=other)

    with pytest.raises(Conflict) as refused:
        RequirementReservationLinks(db_session).claim(world.requirement, world.mic.id)

    assert "another requirement" in refused.value.message


def test_a_stale_link_to_another_requirement_is_taken_over(db_session, world):
    """Its reservation is gone, so the item is free to fulfil this one."""
    other = CoordinatorEquipmentRequirement(
        event_id=world.event.id, category="Audio", quantity_needed=2, created_by=world.coordinator.id
    )
    db_session.add(other)
    db_session.commit()
    stale = _link(db_session, world, world.mic, requirement=other)  # nothing reserved behind it

    RequirementReservationLinks(db_session).claim(world.requirement, world.mic.id)
    db_session.commit()

    assert stale.requirement_id == world.requirement.id
    assert len(_links(db_session)) == 1


# ---------------------------------------------------------------------------
# EquipmentRequirementFulfillmentService.reserve
# ---------------------------------------------------------------------------


def test_reserving_delegates_to_the_gateway_and_links_the_item(db_session, world):
    service, gateway = _service(db_session)

    requirement, progress = service.reserve(world.requirement.id, world.mic.id, 3, world.tech)

    assert gateway.calls == [dict(event_id=world.event.id, equipment_id=world.mic.id, quantity=3)]
    assert progress.reserved == 3 and progress.status is REVIEWING
    assert [(l.requirement_id, l.equipment_id) for l in _links(db_session)] == [
        (world.requirement.id, world.mic.id)
    ]


def test_a_quantity_left_out_defaults_to_what_the_requirement_still_needs(db_session, world):
    service, gateway = _service(db_session)

    service.reserve(world.requirement.id, world.mic.id, None, world.tech)

    assert gateway.calls[0]["quantity"] == 5


def test_the_default_quantity_is_what_is_still_needed_after_earlier_reservations(db_session, world):
    service, gateway = _service(db_session)
    service.reserve(world.requirement.id, world.mic.id, 3, world.tech)

    service.reserve(world.requirement.id, world.pa.id, None, world.tech)

    assert gateway.calls[1]["quantity"] == 2


def test_an_item_of_another_type_is_refused_before_the_gateway_is_asked(db_session, world):
    service, gateway = _service(db_session)

    with pytest.raises(InvalidInput) as refused:
        service.reserve(world.requirement.id, world.projector.id, 1, world.tech)

    assert refused.value.field == "equipment_id"
    assert gateway.calls == []


def test_an_unknown_item_is_refused(db_session, world):
    service, gateway = _service(db_session)

    with pytest.raises(InvalidInput):
        service.reserve(world.requirement.id, 9999, 1, world.tech)

    assert gateway.calls == []


def test_more_than_is_still_needed_is_refused_before_the_gateway_is_asked(db_session, world):
    service, gateway = _service(db_session)

    with pytest.raises(Conflict) as refused:
        service.reserve(world.requirement.id, world.mic.id, 6, world.tech)  # needs 5

    assert refused.value.field == "quantity"
    assert gateway.calls == []


def test_a_quantity_the_organisers_line_would_force_over_the_remainder_is_refused(db_session, world):
    """Ercong's rule takes the Organiser's quantity whole. If that is more
    than this requirement still needs, reserving would over-fill it, so the
    reservation is refused rather than made."""
    service, gateway = _service(db_session, forced={(world.event.id, world.mic.id): 8})

    with pytest.raises(Conflict) as refused:
        service.reserve(world.requirement.id, world.mic.id, None, world.tech)  # needs 5

    assert "8" in refused.value.message and "5" in refused.value.message
    assert gateway.calls == []


def test_a_forced_quantity_within_the_remainder_is_reserved(db_session, world):
    service, _ = _service(db_session, forced={(world.event.id, world.mic.id): 4})

    _, progress = service.reserve(world.requirement.id, world.mic.id, None, world.tech)

    assert progress.reserved == 4


def test_a_refusal_from_the_gateway_leaves_nothing_linked(db_session, world):
    refusal = ReservationRefused("Only 1 Shure BLX24 available for this event's date and time; 5 requested.", status_code=409)
    service, _ = _service(db_session, refuse=refusal)

    with pytest.raises(ReservationRefused) as refused:
        service.reserve(world.requirement.id, world.mic.id, None, world.tech)

    assert refused.value is refusal  # his words, untouched
    # The session does not autoflush, so a link left pending would not show in
    # a query: look at what is pending, not only at what is stored.
    assert not db_session.new
    assert _links(db_session) == []
    assert db_session.query(EquipmentRequest).count() == 0


def test_reserving_clears_an_unavailable_outcome(db_session, world):
    """Marked Unavailable, then equipment turns up: the requirement is being
    worked on again. The stored outcome moves to Reviewing, so it does not
    come back as Unavailable if a reservation is later lost."""
    world.requirement.status = REJECTED
    db_session.commit()
    service, _ = _service(db_session)

    requirement, _ = service.reserve(world.requirement.id, world.mic.id, 2, world.tech)

    assert requirement.status is REVIEWING


@pytest.mark.parametrize(
    "event_status", [s for s in EventStatus if s not in EQUIPMENT_ACTIVE_STATUSES]
)
def test_a_requirement_outside_the_window_is_not_found(db_session, world, event_status):
    world.event.status = event_status
    db_session.commit()
    service, gateway = _service(db_session)

    with pytest.raises(NotFound):
        service.reserve(world.requirement.id, world.mic.id, 1, world.tech)

    assert gateway.calls == []


def test_an_unknown_requirement_is_not_found(db_session, world):
    service, _ = _service(db_session)

    with pytest.raises(NotFound):
        service.reserve(9999, world.mic.id, 1, world.tech)


# ---------------------------------------------------------------------------
# EquipmentRequirementFulfillmentService.update
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [REQUESTED, REVIEWING, REJECTED])
def test_technical_support_can_set_a_status_they_own(db_session, world, status):
    service, _ = _service(db_session)

    requirement, progress = service.update(world.requirement.id, status=status)

    assert requirement.status is status and progress.status is status


@pytest.mark.parametrize("status", [RESERVED, EquipmentStatus.cancelled])
def test_reserved_and_cancelled_cannot_be_set_by_hand(db_session, world, status):
    service, _ = _service(db_session)

    with pytest.raises(InvalidInput) as refused:
        service.update(world.requirement.id, status=status)

    assert refused.value.field == "status"
    if status is RESERVED:
        # Not just refused: told why, so nobody hunts for a way round it.
        assert "reservations" in refused.value.message
    assert db_session.get(CoordinatorEquipmentRequirement, world.requirement.id).status is REQUESTED


def test_unavailable_cannot_be_set_once_something_is_reserved(db_session, world):
    service, _ = _service(db_session)
    service.reserve(world.requirement.id, world.mic.id, 2, world.tech)

    with pytest.raises(Conflict) as refused:
        service.update(world.requirement.id, status=REJECTED)

    assert refused.value.field == "status"


def test_the_quantity_needed_can_be_changed(db_session, world):
    service, _ = _service(db_session)

    requirement, progress = service.update(world.requirement.id, quantity_needed=8)

    assert requirement.quantity_needed == 8 and progress.needed == 8


def test_the_quantity_needed_cannot_go_below_what_is_reserved(db_session, world):
    service, _ = _service(db_session)
    service.reserve(world.requirement.id, world.mic.id, 4, world.tech)

    with pytest.raises(Conflict) as refused:
        service.update(world.requirement.id, quantity_needed=3)

    assert refused.value.field == "quantity_needed"
    assert db_session.get(CoordinatorEquipmentRequirement, world.requirement.id).quantity_needed == 5


def test_the_quantity_needed_can_drop_to_exactly_what_is_reserved(db_session, world):
    service, _ = _service(db_session)
    service.reserve(world.requirement.id, world.mic.id, 4, world.tech)

    _, progress = service.update(world.requirement.id, quantity_needed=4)

    assert progress.status is RESERVED


@pytest.mark.parametrize("quantity", [0, -1, True, "3"])
def test_a_quantity_that_is_not_a_positive_whole_number_is_refused(db_session, world, quantity):
    service, _ = _service(db_session)

    with pytest.raises(InvalidInput) as refused:
        service.update(world.requirement.id, quantity_needed=quantity)

    assert refused.value.field == "quantity_needed"


def test_only_status_and_quantity_can_be_updated_here(db_session, world):
    """Type and notes are the Coordinator's. Technical Support changing the
    type under a requirement they are fulfilling is not a thing."""
    service, _ = _service(db_session)

    with pytest.raises(TypeError):
        service.update(world.requirement.id, category="Lighting")
    with pytest.raises(TypeError):
        service.update(world.requirement.id, technical_notes="x")


def test_an_empty_update_changes_nothing(db_session, world):
    service, _ = _service(db_session)

    requirement, _ = service.update(world.requirement.id)

    assert requirement.quantity_needed == 5 and requirement.status is REQUESTED
