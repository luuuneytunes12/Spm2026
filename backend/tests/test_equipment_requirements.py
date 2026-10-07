"""Tests for the "Record Equipment Requirements for Event" story.

    As an Event Coordinator, I want to record the equipment an event
    requires, so that Technical Support Staff know what to review and
    reserve.

Acceptance criteria:

    ER AC1  I can add equipment requirements to an event: equipment type,
            quantity needed, and any technical notes.
    ER AC2  Requirements are visible to Technical Support Staff from the
            event record.

Each test is named after the criterion it covers; the mapping is in
docs/test-cases-equipment-requirements.md.

The contract under test:

    Coordinator (assigned events only)
        POST   /equipment-requirements/events/{event_id}
        GET    /equipment-requirements/events/{event_id}
        PATCH  /equipment-requirements/{requirement_id}
        DELETE /equipment-requirements/{requirement_id}

    Technical Support
        GET    /equipment-requirements/support/events
        GET    /equipment-requirements/support/events/{event_id}

A requirement is the Coordinator's own record, in its own table. It is NOT a
row of `equipment_requests` -- those are the Organiser's picks, and an
Organiser's approved change request replaces every one of them.
"""

import itertools
from types import SimpleNamespace

import pytest

from app.core.roles import Role
from app.models.enums import EquipmentOperationalStatus, EquipmentStatus, EventStatus
from app.models.equipment import CoordinatorEquipmentRequirement, Equipment, EquipmentRequest
from app.models.events import Event
from app.models.user import User
from app.services.equipment_lines import replace_equipment_lines

_unique = itertools.count()

# Where the Coordinator may record equipment, and where Technical Support
# looks. One list for both, so a requirement can never sit somewhere
# Technical Support is not looking.
#
# PROVISIONAL: neither PDF says when equipment may be recorded. This is the
# window from W4 p3 ("during the planning process") and W1 Step 8, which
# comes after Step 5 approval. Pending the customer's answer in Q&A.
ACTIVE = [EventStatus.event_approved, EventStatus.planning_event, EventStatus.safety_check_passed]
INACTIVE = [s for s in EventStatus if s not in ACTIVE]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _user(client, db_session, role, email=None, name="Test User"):
    """Register a user, promote them to `role`, and return (user, headers).

    Registration always assigns `attendee` (by design -- a client can never
    pick its own role), so the role is set directly here. The re-login is
    what makes the returned token reflect the new role.
    """
    email = email or f"user{next(_unique)}@example.com"
    password = "password123"
    res = client.post(
        "/auth/register", json={"name": name, "email": email, "password": password}
    )
    assert res.status_code == 201, res.text
    user = db_session.query(User).filter(User.email == email).one()
    user.role = role.value
    db_session.commit()
    token = client.post("/auth/login", json={"email": email, "password": password}).json()[
        "access_token"
    ]
    return user, {"Authorization": f"Bearer {token}"}


def _equipment(db_session, name, category="Audio", **overrides) -> Equipment:
    item = Equipment(
        name=name,
        category=category,
        description="A description.",
        total_quantity=overrides.pop("total_quantity", 10),
        location="Marina Bay Facility",
        operational_status=overrides.pop(
            "operational_status", EquipmentOperationalStatus.available
        ),
        **overrides,
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item


def _event(db_session, organiser, coordinator=None, status=EventStatus.event_approved, **overrides):
    event = Event(
        name=overrides.pop("name", "Regional Partner Conference"),
        organiser_id=organiser.id,
        coordinator_id=coordinator.id if coordinator else None,
        status=status,
        **overrides,
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    return event


def _organiser_line(db_session, event, equipment, quantity=2) -> EquipmentRequest:
    """One of the Organiser's picks -- a row of `equipment_requests`."""
    line = EquipmentRequest(
        event_id=event.id, equipment_id=equipment.id, quantity_requested=quantity
    )
    db_session.add(line)
    db_session.commit()
    db_session.refresh(line)
    return line


def _world(client, db_session, status=EventStatus.event_approved):
    """An Organiser, the Coordinator assigned to their event, a catalogue
    with two categories, and the event itself."""
    organiser, organiser_headers = _user(client, db_session, Role.ORGANISER, name="Organiser")
    coordinator, headers = _user(client, db_session, Role.COORDINATOR, name="Coordinator")
    _equipment(db_session, "Shure BLX24", category="Audio")
    _equipment(db_session, "Epson EB-L200SW", category="Projection")
    event = _event(db_session, organiser, coordinator, status=status)
    return SimpleNamespace(
        organiser=organiser,
        organiser_headers=organiser_headers,
        coordinator=coordinator,
        headers=headers,
        event=event,
    )


def _tech_support(client, db_session):
    return _user(client, db_session, Role.TECH_SUPPORT, name="Tech Support")[1]


def _add(client, headers, event_id, **body):
    body = {"category": "Audio", "quantity_needed": 6, **body}
    return client.post(f"/equipment-requirements/events/{event_id}", json=body, headers=headers)


def _added(client, headers, event_id, **body) -> dict:
    res = _add(client, headers, event_id, **body)
    assert res.status_code == 201, res.text
    return res.json()


def _fields_flagged(res) -> set[str]:
    return {item["loc"][-1] for item in res.json()["detail"]}


# ---------------------------------------------------------------------------
# ER AC1 -- add equipment type, quantity needed and technical notes
# ---------------------------------------------------------------------------


def test_er_ac1_a_requirement_records_type_quantity_and_notes(client, db_session):
    w = _world(client, db_session)

    body = _added(
        client,
        w.headers,
        w.event.id,
        category="Audio",
        quantity_needed=6,
        technical_notes="Handheld wireless, for panel Q&A",
    )

    assert body["category"] == "Audio"
    assert body["quantity_needed"] == 6
    assert body["technical_notes"] == "Handheld wireless, for panel Q&A"
    assert body["event_id"] == w.event.id


def test_er_ac1_a_new_requirement_starts_as_requested(client, db_session):
    """Recording is not being granted. Technical Support moves it on, which
    is a later story."""
    w = _world(client, db_session)

    body = _added(client, w.headers, w.event.id)

    assert body["status"] == "requested"
    row = db_session.query(CoordinatorEquipmentRequirement).one()
    assert row.status == EquipmentStatus.requested


def test_er_ac1_technical_notes_are_optional(client, db_session):
    w = _world(client, db_session)

    body = _added(client, w.headers, w.event.id)

    assert body["technical_notes"] is None


def test_er_ac1_blank_notes_are_stored_as_no_notes(client, db_session):
    """Spaces are not a note, and should not read as one on screen."""
    w = _world(client, db_session)

    body = _added(client, w.headers, w.event.id, technical_notes="   ")

    assert body["technical_notes"] is None


def test_er_ac1_the_type_is_matched_to_the_catalogue_ignoring_case(client, db_session):
    """The category is one of the catalogue's own, stored in its spelling, so
    "audio" and "Audio" can never become two different types."""
    w = _world(client, db_session)

    body = _added(client, w.headers, w.event.id, category="  audio ")

    assert body["category"] == "Audio"


def test_er_ac1_an_unknown_type_is_rejected(client, db_session):
    w = _world(client, db_session)

    res = _add(client, w.headers, w.event.id, category="Pyrotechnics")

    assert res.status_code == 422
    assert _fields_flagged(res) == {"category"}
    assert db_session.query(CoordinatorEquipmentRequirement).count() == 0


@pytest.mark.parametrize("category", ["", "   "])
def test_er_ac1_a_blank_type_is_rejected(client, db_session, category):
    w = _world(client, db_session)

    assert _add(client, w.headers, w.event.id, category=category).status_code == 422


@pytest.mark.parametrize("quantity", [0, -1])
def test_er_ac1_a_quantity_below_one_is_rejected(client, db_session, quantity):
    w = _world(client, db_session)

    res = _add(client, w.headers, w.event.id, quantity_needed=quantity)

    assert res.status_code == 422
    assert _fields_flagged(res) == {"quantity_needed"}


def test_er_ac1_two_requirements_may_share_a_type(client, db_session):
    """Six microphones and a PA system are both Audio -- they are separate
    needs, and forbidding the second would reject a legitimate requirement."""
    w = _world(client, db_session)

    _added(client, w.headers, w.event.id, category="Audio", quantity_needed=6)
    _added(client, w.headers, w.event.id, category="Audio", quantity_needed=1)

    assert db_session.query(CoordinatorEquipmentRequirement).count() == 2


def test_er_ac1_a_requirement_may_be_based_on_an_organisers_pick(client, db_session):
    w = _world(client, db_session)
    mic = db_session.query(Equipment).filter_by(name="Shure BLX24").one()
    pick = _organiser_line(db_session, w.event, mic, quantity=4)

    body = _added(client, w.headers, w.event.id, organiser_equipment_request_id=pick.id)

    assert body["organiser_equipment_request_id"] == pick.id


def test_er_ac1_a_requirement_need_not_come_from_an_organisers_pick(client, db_session):
    """The Coordinator may record an operational need the Organiser never
    mentioned -- which is why the link is optional."""
    w = _world(client, db_session)

    body = _added(client, w.headers, w.event.id)

    assert body["organiser_equipment_request_id"] is None


def test_er_ac1_one_pick_may_have_several_requirements(client, db_session):
    w = _world(client, db_session)
    mic = db_session.query(Equipment).filter_by(name="Shure BLX24").one()
    pick = _organiser_line(db_session, w.event, mic)

    _added(client, w.headers, w.event.id, organiser_equipment_request_id=pick.id)
    _added(client, w.headers, w.event.id, organiser_equipment_request_id=pick.id)

    assert db_session.query(CoordinatorEquipmentRequirement).count() == 2


def test_er_ac1_a_pick_from_another_event_cannot_be_linked(client, db_session):
    """The link says "this need came from that request", so it has to be a
    request for the same event."""
    w = _world(client, db_session)
    other = _event(db_session, w.organiser, w.coordinator, name="A different event")
    mic = db_session.query(Equipment).filter_by(name="Shure BLX24").one()
    foreign_pick = _organiser_line(db_session, other, mic)

    res = _add(
        client, w.headers, w.event.id, organiser_equipment_request_id=foreign_pick.id
    )

    assert res.status_code == 422
    assert _fields_flagged(res) == {"organiser_equipment_request_id"}


def test_er_ac1_a_pick_that_does_not_exist_cannot_be_linked(client, db_session):
    w = _world(client, db_session)

    res = _add(client, w.headers, w.event.id, organiser_equipment_request_id=9999)

    assert res.status_code == 422


@pytest.mark.parametrize("status", ACTIVE)
def test_er_ac1_equipment_can_be_recorded_in_these_statuses(client, db_session, status):
    w = _world(client, db_session, status=status)

    assert _add(client, w.headers, w.event.id).status_code == 201


@pytest.mark.parametrize("status", INACTIVE)
def test_er_ac1_equipment_cannot_be_recorded_in_any_other_status(client, db_session, status):
    """Drafts and submitted requests are not yet plans, an event under review
    has not been approved, and a rejected, completed or cancelled event has
    nothing left to equip (W1 p8: reservations must not stay committed to a
    cancelled event)."""
    w = _world(client, db_session, status=status)

    res = _add(client, w.headers, w.event.id)

    assert res.status_code == 409
    assert db_session.query(CoordinatorEquipmentRequirement).count() == 0


def test_er_ac1_another_coordinators_event_is_not_found(client, db_session):
    """404, not 403: "not yours" and "does not exist" are indistinguishable,
    so event ids cannot be probed."""
    w = _world(client, db_session)
    _, other_headers = _user(client, db_session, Role.COORDINATOR, name="Other")

    assert _add(client, other_headers, w.event.id).status_code == 404


def test_er_ac1_an_event_that_does_not_exist_is_not_found(client, db_session):
    w = _world(client, db_session)

    assert _add(client, w.headers, 9999).status_code == 404


@pytest.mark.parametrize(
    "role", [Role.ORGANISER, Role.ATTENDEE, Role.TECH_SUPPORT, Role.VENUE_STAFF]
)
def test_er_ac1_only_a_coordinator_can_record_equipment(client, db_session, role):
    w = _world(client, db_session)
    _, headers = _user(client, db_session, role)

    assert _add(client, headers, w.event.id).status_code == 403


def test_er_ac1_an_anonymous_caller_is_unauthenticated(client, db_session):
    w = _world(client, db_session)

    res = client.post(
        f"/equipment-requirements/events/{w.event.id}",
        json={"category": "Audio", "quantity_needed": 1},
    )

    assert res.status_code == 401


# --- the Coordinator reads back what was recorded ---------------------------


def test_er_ac1_the_coordinator_lists_an_events_requirements_oldest_first(client, db_session):
    w = _world(client, db_session)
    _added(client, w.headers, w.event.id, category="Audio", quantity_needed=6)
    _added(client, w.headers, w.event.id, category="Projection", quantity_needed=2)

    res = client.get(f"/equipment-requirements/events/{w.event.id}", headers=w.headers)

    assert res.status_code == 200
    assert [(r["category"], r["quantity_needed"]) for r in res.json()] == [
        ("Audio", 6),
        ("Projection", 2),
    ]


def test_er_ac1_an_event_with_no_requirements_lists_an_empty_array(client, db_session):
    """Empty rather than absent, and not an error."""
    w = _world(client, db_session)

    res = client.get(f"/equipment-requirements/events/{w.event.id}", headers=w.headers)

    assert res.status_code == 200
    assert res.json() == []


def test_er_ac1_requirements_of_another_coordinators_event_are_not_found(client, db_session):
    w = _world(client, db_session)
    _, other_headers = _user(client, db_session, Role.COORDINATOR, name="Other")

    res = client.get(f"/equipment-requirements/events/{w.event.id}", headers=other_headers)

    assert res.status_code == 404


def test_er_ac1_requirements_stay_listed_once_the_event_is_outside_the_window(client, db_session):
    """Recording stops outside the window; reading never does. A completed
    event's requirements are still its record."""
    w = _world(client, db_session)
    _added(client, w.headers, w.event.id)
    w.event.status = EventStatus.event_completed
    db_session.commit()

    res = client.get(f"/equipment-requirements/events/{w.event.id}", headers=w.headers)

    assert res.status_code == 200
    assert len(res.json()) == 1


# --- editing ---------------------------------------------------------------


def test_er_ac1_a_requirement_can_be_edited(client, db_session):
    w = _world(client, db_session)
    created = _added(client, w.headers, w.event.id, quantity_needed=6, technical_notes="Old")

    res = client.patch(
        f"/equipment-requirements/{created['id']}",
        json={"quantity_needed": 8, "technical_notes": "New", "category": "Projection"},
        headers=w.headers,
    )

    assert res.status_code == 200
    assert (res.json()["quantity_needed"], res.json()["technical_notes"]) == (8, "New")
    assert res.json()["category"] == "Projection"


def test_er_ac1_an_edit_that_omits_a_field_leaves_it_alone(client, db_session):
    """Consistent with every other PATCH in the app: omitted means untouched."""
    w = _world(client, db_session)
    created = _added(client, w.headers, w.event.id, quantity_needed=6, technical_notes="Keep me")

    res = client.patch(
        f"/equipment-requirements/{created['id']}",
        json={"quantity_needed": 9},
        headers=w.headers,
    )

    assert res.json()["technical_notes"] == "Keep me"
    assert res.json()["category"] == "Audio"


def test_er_ac1_notes_can_be_cleared_with_an_explicit_null(client, db_session):
    w = _world(client, db_session)
    created = _added(client, w.headers, w.event.id, technical_notes="Remove me")

    res = client.patch(
        f"/equipment-requirements/{created['id']}",
        json={"technical_notes": None},
        headers=w.headers,
    )

    assert res.json()["technical_notes"] is None


@pytest.mark.parametrize(
    "changes,flagged",
    [
        ({"quantity_needed": 0}, "quantity_needed"),
        ({"category": "Pyrotechnics"}, "category"),
        ({"category": "  "}, "category"),
    ],
)
def test_er_ac1_an_invalid_edit_is_rejected_and_changes_nothing(
    client, db_session, changes, flagged
):
    w = _world(client, db_session)
    created = _added(client, w.headers, w.event.id, quantity_needed=6)

    res = client.patch(f"/equipment-requirements/{created['id']}", json=changes, headers=w.headers)

    assert res.status_code == 422
    assert flagged in _fields_flagged(res)
    assert db_session.query(CoordinatorEquipmentRequirement).one().quantity_needed == 6


def test_er_ac1_the_link_to_an_organisers_pick_cannot_be_edited(client, db_session):
    """Where a need came from is a fact about its origin, not a field to
    retarget. An attempt to send one is ignored."""
    w = _world(client, db_session)
    mic = db_session.query(Equipment).filter_by(name="Shure BLX24").one()
    pick = _organiser_line(db_session, w.event, mic)
    created = _added(client, w.headers, w.event.id)

    client.patch(
        f"/equipment-requirements/{created['id']}",
        json={"organiser_equipment_request_id": pick.id},
        headers=w.headers,
    )

    assert db_session.query(CoordinatorEquipmentRequirement).one().organiser_equipment_request_id is None


def test_er_ac1_another_coordinators_requirement_cannot_be_edited(client, db_session):
    w = _world(client, db_session)
    created = _added(client, w.headers, w.event.id)
    _, other_headers = _user(client, db_session, Role.COORDINATOR, name="Other")

    res = client.patch(
        f"/equipment-requirements/{created['id']}", json={"quantity_needed": 1}, headers=other_headers
    )

    assert res.status_code == 404


def test_er_ac1_a_requirement_cannot_be_edited_once_the_event_leaves_the_window(
    client, db_session
):
    w = _world(client, db_session)
    created = _added(client, w.headers, w.event.id)
    w.event.status = EventStatus.event_cancelled
    db_session.commit()

    res = client.patch(
        f"/equipment-requirements/{created['id']}", json={"quantity_needed": 1}, headers=w.headers
    )

    assert res.status_code == 409


def test_er_ac1_a_requirement_that_does_not_exist_is_not_found(client, db_session):
    w = _world(client, db_session)

    res = client.patch("/equipment-requirements/9999", json={"quantity_needed": 1}, headers=w.headers)

    assert res.status_code == 404


# --- deleting --------------------------------------------------------------


def test_er_ac1_a_requirement_can_be_deleted(client, db_session):
    w = _world(client, db_session)
    created = _added(client, w.headers, w.event.id)

    res = client.delete(f"/equipment-requirements/{created['id']}", headers=w.headers)

    assert res.status_code == 204
    assert db_session.query(CoordinatorEquipmentRequirement).count() == 0


def test_er_ac1_another_coordinators_requirement_cannot_be_deleted(client, db_session):
    w = _world(client, db_session)
    created = _added(client, w.headers, w.event.id)
    _, other_headers = _user(client, db_session, Role.COORDINATOR, name="Other")

    res = client.delete(f"/equipment-requirements/{created['id']}", headers=other_headers)

    assert res.status_code == 404
    assert db_session.query(CoordinatorEquipmentRequirement).count() == 1


def test_er_ac1_a_requirement_cannot_be_deleted_once_the_event_leaves_the_window(
    client, db_session
):
    w = _world(client, db_session)
    created = _added(client, w.headers, w.event.id)
    w.event.status = EventStatus.event_completed
    db_session.commit()

    res = client.delete(f"/equipment-requirements/{created['id']}", headers=w.headers)

    assert res.status_code == 409
    assert db_session.query(CoordinatorEquipmentRequirement).count() == 1


@pytest.mark.parametrize("role", [Role.ORGANISER, Role.TECH_SUPPORT, Role.ATTENDEE])
def test_er_ac1_only_a_coordinator_can_edit_or_delete(client, db_session, role):
    w = _world(client, db_session)
    created = _added(client, w.headers, w.event.id)
    _, headers = _user(client, db_session, role)

    edit = client.patch(
        f"/equipment-requirements/{created['id']}", json={"quantity_needed": 1}, headers=headers
    )
    delete = client.delete(f"/equipment-requirements/{created['id']}", headers=headers)

    assert (edit.status_code, delete.status_code) == (403, 403)


# ---------------------------------------------------------------------------
# The Organiser's picks and the Coordinator's requirements stay separate
# ---------------------------------------------------------------------------


def test_replacing_the_organisers_lines_never_deletes_a_requirement(client, db_session):
    """THE reason requirements have their own table.

    An Organiser's approved change request calls replace_equipment_lines,
    which deletes every row of `equipment_requests` for the event and
    rebuilds them. A requirement that lived in that table would go with
    them. Here it survives, and the link to the pick that was replaced is
    simply cleared (ON DELETE SET NULL).
    """
    # SQLite ignores foreign keys unless asked, and ON DELETE SET NULL is
    # exactly what is being proved. The StaticPool shares one connection, so
    # this holds for the whole test; the guard below fails loudly if the
    # pragma ever silently stops applying.
    db_session.connection().exec_driver_sql("PRAGMA foreign_keys=ON")
    assert db_session.connection().exec_driver_sql("PRAGMA foreign_keys").scalar() == 1

    w = _world(client, db_session)
    mic = db_session.query(Equipment).filter_by(name="Shure BLX24").one()
    pick = _organiser_line(db_session, w.event, mic, quantity=4)
    _added(client, w.headers, w.event.id, organiser_equipment_request_id=pick.id)

    replace_equipment_lines(db_session, w.event, [])
    db_session.commit()
    db_session.expire_all()

    assert db_session.query(EquipmentRequest).count() == 0
    requirement = db_session.query(CoordinatorEquipmentRequirement).one()
    assert requirement.organiser_equipment_request_id is None
    assert requirement.category == "Audio"


def test_a_requirement_is_not_one_of_the_organisers_picks(client, db_session):
    """The two live in different tables and never appear in each other."""
    w = _world(client, db_session)
    _added(client, w.headers, w.event.id)

    assert db_session.query(EquipmentRequest).count() == 0


def test_the_organiser_never_receives_the_coordinators_requirements(client, db_session):
    """Internal planning stays internal while arrangements are worked on. The
    Organiser's own view of their request carries their picks only."""
    w = _world(client, db_session)
    mic = db_session.query(Equipment).filter_by(name="Shure BLX24").one()
    _organiser_line(db_session, w.event, mic, quantity=4)
    _added(
        client, w.headers, w.event.id, category="Projection", technical_notes="Ceiling mount"
    )

    res = client.get(f"/events/{w.event.id}", headers=w.organiser_headers)

    assert res.status_code == 200
    assert [line["equipment_name"] for line in res.json()["equipment_items"]] == ["Shure BLX24"]
    assert "Ceiling mount" not in res.text


# ---------------------------------------------------------------------------
# ER AC2 -- visible to Technical Support Staff from the event record
# ---------------------------------------------------------------------------


def test_er_ac2_technical_support_sees_what_the_coordinator_recorded(client, db_session):
    w = _world(client, db_session)
    tech = _tech_support(client, db_session)
    _added(
        client, w.headers, w.event.id,
        category="Audio", quantity_needed=6, technical_notes="Handheld wireless",
    )

    res = client.get(f"/equipment-requirements/support/events/{w.event.id}", headers=tech)

    assert res.status_code == 200
    requirement = res.json()["requirements"][0]
    assert requirement["category"] == "Audio"
    assert requirement["quantity_needed"] == 6
    assert requirement["technical_notes"] == "Handheld wireless"
    assert requirement["status"] == "requested"


def test_er_ac2_the_event_record_carries_what_is_needed_to_review_it(client, db_session):
    organiser, _ = _user(client, db_session, Role.ORGANISER)
    coordinator, headers = _user(client, db_session, Role.COORDINATOR, name="Sam Tan")
    _equipment(db_session, "Shure BLX24")
    event = _event(
        db_session, organiser, coordinator, name="Regional Partner Conference",
        event_type="conference", expected_attendance=120,
        venue_requirements="Main hall, stage, podium",
    )
    _added(client, headers, event.id)
    tech = _tech_support(client, db_session)

    record = client.get(f"/equipment-requirements/support/events/{event.id}", headers=tech).json()

    assert record["id"] == event.id
    assert record["name"] == "Regional Partner Conference"
    assert record["expected_attendance"] == 120
    assert record["venue_requirements"] == "Main hall, stage, podium"
    assert record["status"] == "event_approved"
    assert record["coordinator"]["name"] == "Sam Tan"


def test_er_ac2_the_event_record_is_visible_before_anything_is_recorded(client, db_session):
    """An approved event with no requirements yet is still an event Technical
    Support can open -- the list just does not offer it."""
    w = _world(client, db_session)
    tech = _tech_support(client, db_session)

    res = client.get(f"/equipment-requirements/support/events/{w.event.id}", headers=tech)

    assert res.status_code == 200
    assert res.json()["requirements"] == []


def test_er_ac2_technical_support_lists_events_that_have_requirements(client, db_session):
    w = _world(client, db_session)
    tech = _tech_support(client, db_session)
    _added(client, w.headers, w.event.id)
    _added(client, w.headers, w.event.id, category="Projection")

    res = client.get("/equipment-requirements/support/events", headers=tech)

    assert res.status_code == 200
    assert [(e["id"], e["name"], e["requirement_count"]) for e in res.json()] == [
        (w.event.id, "Regional Partner Conference", 2)
    ]


def test_er_ac2_an_event_with_no_requirements_is_not_listed(client, db_session):
    w = _world(client, db_session)
    tech = _tech_support(client, db_session)

    assert client.get("/equipment-requirements/support/events", headers=tech).json() == []
    assert w.event.id  # the event exists; it is simply nothing to review


@pytest.mark.parametrize("status", ACTIVE)
def test_er_ac2_events_in_the_window_are_listed(client, db_session, status):
    w = _world(client, db_session, status=status)
    tech = _tech_support(client, db_session)
    db_session.add(
        CoordinatorEquipmentRequirement(
            event_id=w.event.id, category="Audio", quantity_needed=1,
            created_by=w.coordinator.id,
        )
    )
    db_session.commit()

    listed = client.get("/equipment-requirements/support/events", headers=tech).json()

    assert [e["id"] for e in listed] == [w.event.id]


@pytest.mark.parametrize("status", INACTIVE)
def test_er_ac2_events_outside_the_window_are_neither_listed_nor_openable(
    client, db_session, status
):
    """Drafts are private to the Organiser, and an event still under review
    is not yet something Technical Support acts on. Not-found rather than
    forbidden, so they are indistinguishable from events that do not exist."""
    w = _world(client, db_session, status=status)
    tech = _tech_support(client, db_session)
    db_session.add(
        CoordinatorEquipmentRequirement(
            event_id=w.event.id, category="Audio", quantity_needed=1,
            created_by=w.coordinator.id,
        )
    )
    db_session.commit()

    assert client.get("/equipment-requirements/support/events", headers=tech).json() == []
    res = client.get(f"/equipment-requirements/support/events/{w.event.id}", headers=tech)
    assert res.status_code == 404


def test_er_ac2_an_event_that_does_not_exist_is_not_found(client, db_session):
    tech = _tech_support(client, db_session)

    assert client.get("/equipment-requirements/support/events/9999", headers=tech).status_code == 404


def test_er_ac2_technical_support_sees_requirements_of_every_coordinators_events(
    client, db_session
):
    """Unlike the Coordinator, Technical Support is not scoped to "my"
    events -- they review equipment across all of them."""
    first = _world(client, db_session)
    second = _world(client, db_session)
    tech = _tech_support(client, db_session)
    _added(client, first.headers, first.event.id)
    _added(client, second.headers, second.event.id)

    listed = client.get("/equipment-requirements/support/events", headers=tech).json()

    assert {e["id"] for e in listed} == {first.event.id, second.event.id}


def test_er_ac2_technical_support_receives_only_what_it_needs_of_a_requirement(
    client, db_session
):
    """The requirement as Technical Support sees it. No author, no link to
    the Organiser's pick -- that is the Coordinator's bookkeeping. Progress
    (reserved_quantity, reservations) was added by Update Equipment
    Requirement Status; nothing of the Coordinator's own was."""
    w = _world(client, db_session)
    tech = _tech_support(client, db_session)
    _added(client, w.headers, w.event.id)

    requirement = client.get(
        f"/equipment-requirements/support/events/{w.event.id}", headers=tech
    ).json()["requirements"][0]

    assert set(requirement) == {
        "id", "category", "quantity_needed", "technical_notes", "status",
        "reserved_quantity", "reservations",
    }


def test_er_ac2_the_event_record_does_not_leak_the_coordinators_password_hash(
    client, db_session
):
    w = _world(client, db_session)
    tech = _tech_support(client, db_session)
    _added(client, w.headers, w.event.id)

    record = client.get(f"/equipment-requirements/support/events/{w.event.id}", headers=tech).json()

    assert set(record["coordinator"]) == {"id", "name", "email"}


@pytest.mark.parametrize(
    "role", [Role.COORDINATOR, Role.ORGANISER, Role.ATTENDEE, Role.VENUE_STAFF]
)
@pytest.mark.parametrize(
    "path", ["/equipment-requirements/support/events", "/equipment-requirements/support/events/1"]
)
def test_er_ac2_only_technical_support_can_use_the_support_view(client, db_session, role, path):
    _, headers = _user(client, db_session, role)

    assert client.get(path, headers=headers).status_code == 403


@pytest.mark.parametrize(
    "path", ["/equipment-requirements/support/events", "/equipment-requirements/support/events/1"]
)
def test_er_ac2_an_anonymous_caller_is_unauthenticated(client, db_session, path):
    assert client.get(path).status_code == 401
