"""Tests for "View Equipment Requirements as Technical Support Staff".

    As a Technical Support Staff member, I want a list of Equipment
    Requirements waiting for me, so that I can review and reserve them without
    searching every Event.

Traceability (see docs/test-cases-view-equipment-requirements.md):
    AC1  each Requested requirement is listed with its Event, equipment type,
         quantity, date and time, oldest Event date first
    AC2  none Requested -> an empty list (the screen shows the message)
    AC3  a listed requirement carries its technical notes and placement, so it
         can be opened and reserved (the existing Manage panel's data)
    AC4  anyone but Technical Support is denied, on a direct request

"Requested" is the Definition of Done's status (11b): nothing reserved, or only
part of it. Fully reserved (Reserved), marked Unavailable, and freed (Available)
are not waiting for Technical Support, so they are not listed.
"""

from datetime import datetime, timezone

import pytest

from app.core.roles import Role
from app.models.enums import EquipmentStatus, EventStatus
from app.models.equipment import CoordinatorEquipmentRequirement
from tests.test_equipment_requirement_fulfillment import (
    _reserve,
    _reserved,
    _update,
    _user,
    _world,
)
from tests.test_equipment_requirements import INACTIVE, _added, _event

PATH = "/equipment-requirements/support/requested"


def _utc(month, day, hour=9):
    return datetime(2026, month, day, hour, tzinfo=timezone.utc)


def _listed(client, headers):
    res = client.get(PATH, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def _on_another_event(client, db_session, w, name, start, end, *, category="Audio", quantity=3):
    event = _event(
        db_session, w.organiser, w.coordinator, name=name, proposed_start=start, proposed_end=end
    )
    requirement = _added(client, w.headers, event.id, category=category, quantity_needed=quantity)
    return event, requirement


# ---------------------------------------------------------------------------
# AC1 -- each Requested requirement, with its event, type, quantity, date/time
# ---------------------------------------------------------------------------


def test_ac1_a_requested_requirement_is_listed_with_its_event_type_quantity_and_time(client, db_session):
    w = _world(client, db_session, needed=5)

    [row] = _listed(client, w.tech)

    assert row["id"] == w.rid
    assert row["category"] == "Audio" and row["quantity_needed"] == 5
    assert row["status"] == "requested"
    assert row["event"]["id"] == w.event.id
    assert row["event"]["name"] == w.event.name
    assert row["event"]["proposed_start"].startswith("2026-11-02T09:00")
    assert row["event"]["proposed_end"].startswith("2026-11-02T17:00")


def test_ac1_requirements_from_every_event_are_in_the_one_list(client, db_session):
    w = _world(client, db_session)
    _, other = _on_another_event(client, db_session, w, "Gala", _utc(12, 5), _utc(12, 5, 17))

    ids = {row["id"] for row in _listed(client, w.tech)}

    assert ids == {w.rid, other["id"]}


def test_ac1_the_oldest_event_date_comes_first(client, db_session):
    w = _world(client, db_session)  # 2 Nov 2026
    _, earlier = _on_another_event(client, db_session, w, "Workshop", _utc(10, 20), _utc(10, 20, 17))
    _, later = _on_another_event(client, db_session, w, "Gala", _utc(12, 5), _utc(12, 5, 17))

    ids = [row["id"] for row in _listed(client, w.tech)]

    assert ids == [earlier["id"], w.rid, later["id"]]


def test_ac1_requirements_of_one_event_keep_the_order_they_were_recorded_in(client, db_session):
    w = _world(client, db_session)
    second = _added(client, w.headers, w.event.id, category="Projection", quantity_needed=1)

    ids = [row["id"] for row in _listed(client, w.tech)]

    assert ids == [w.rid, second["id"]]


def test_ac1_an_event_with_no_date_is_listed_last(client, db_session):
    w = _world(client, db_session)
    _, undated = _on_another_event(client, db_session, w, "TBC", None, None)
    _, earlier = _on_another_event(client, db_session, w, "Workshop", _utc(10, 20), _utc(10, 20, 17))

    ids = [row["id"] for row in _listed(client, w.tech)]

    assert ids == [earlier["id"], w.rid, undated["id"]]


def test_ac1_an_event_that_has_already_happened_is_still_listed(client, db_session):
    """Requested is a status, not a date: a requirement never fulfilled stays
    waiting until Technical Support deal with it."""
    w = _world(client, db_session)
    _, past = _on_another_event(client, db_session, w, "Last year", _utc(1, 5), _utc(1, 5, 17))

    ids = [row["id"] for row in _listed(client, w.tech)]

    assert past["id"] in ids and ids[0] == past["id"]


def test_ac1_part_reserved_is_still_requested_and_says_how_far(client, db_session):
    w = _world(client, db_session, needed=5)
    _reserved(client, w.tech, w.rid, w.mic.id, quantity=3)

    [row] = _listed(client, w.tech)

    assert row["status"] == "requested"
    assert row["quantity_needed"] == 5 and row["reserved_quantity"] == 3


def test_ac1_a_stored_in_review_value_from_before_still_counts_as_requested(client, db_session):
    w = _world(client, db_session)
    row = db_session.get(CoordinatorEquipmentRequirement, w.rid)
    row.status = EquipmentStatus.reviewing
    db_session.commit()

    assert [r["id"] for r in _listed(client, w.tech)] == [w.rid]


def test_ac1_a_fully_reserved_requirement_is_no_longer_waiting(client, db_session):
    w = _world(client, db_session, needed=4)
    _reserved(client, w.tech, w.rid, w.mic.id)

    assert _listed(client, w.tech) == []


def test_ac1_an_unavailable_requirement_is_no_longer_waiting(client, db_session):
    w = _world(client, db_session)
    assert _update(client, w.tech, w.rid, status="unavailable", reason="Damaged").status_code == 200

    assert _listed(client, w.tech) == []


def test_ac1_a_requirement_set_back_to_requested_is_listed_again(client, db_session):
    w = _world(client, db_session)
    _update(client, w.tech, w.rid, status="unavailable", reason="Damaged")
    _update(client, w.tech, w.rid, status="requested")

    assert [r["id"] for r in _listed(client, w.tech)] == [w.rid]


def test_ac1_a_freed_reservation_is_available_not_requested_so_is_not_listed(client, db_session):
    w = _world(client, db_session, needed=4)
    _reserved(client, w.tech, w.rid, w.mic.id)
    w.event.proposed_start = datetime(2020, 5, 1, 9, tzinfo=timezone.utc)
    w.event.proposed_end = datetime(2020, 5, 1, 17, tzinfo=timezone.utc)
    db_session.commit()

    assert _listed(client, w.tech) == []


def test_ac1_raising_the_quantity_over_what_is_reserved_puts_it_back_in_the_list(client, db_session):
    w = _world(client, db_session, needed=4)
    _reserved(client, w.tech, w.rid, w.mic.id)
    assert _listed(client, w.tech) == []

    _update(client, w.tech, w.rid, quantity_needed=6)

    assert [r["id"] for r in _listed(client, w.tech)] == [w.rid]


@pytest.mark.parametrize("status", INACTIVE)
def test_ac1_an_event_outside_the_window_is_not_listed(client, db_session, status):
    """The same window Technical Support can reserve in: a draft, a rejected
    or a completed event has nothing for them to do."""
    w = _world(client, db_session)
    w.event.status = status
    db_session.commit()

    assert _listed(client, w.tech) == []


# ---------------------------------------------------------------------------
# AC2 -- none Requested
# ---------------------------------------------------------------------------


def test_ac2_with_no_requirements_at_all_the_list_is_empty(client, db_session):
    _, tech = _user(client, db_session, Role.TECH_SUPPORT)

    assert _listed(client, tech) == []


# ---------------------------------------------------------------------------
# AC3 -- opened, a requirement shows technical notes and placement
# ---------------------------------------------------------------------------


def test_ac3_a_listed_requirement_carries_its_technical_notes(client, db_session):
    w = _world(client, db_session)
    [row] = _listed(client, w.tech)

    assert row["technical_notes"] is None
    _added_notes = _added(client, w.headers, w.event.id, technical_notes="Handheld, for panel Q&A")
    rows = {r["id"]: r for r in _listed(client, w.tech)}
    assert rows[_added_notes["id"]]["technical_notes"] == "Handheld, for panel Q&A"


def test_ac3_a_listed_requirement_carries_where_each_reserved_item_is_placed(client, db_session):
    w = _world(client, db_session, needed=5)
    client.post(
        f"/equipment-requirements/{w.rid}/reservations",
        json={"equipment_id": w.mic.id, "quantity": 3, "placement_notes": "Stage left"},
        headers=w.tech,
    )

    [row] = _listed(client, w.tech)

    assert row["reservations"] == [
        {"equipment_id": w.mic.id, "equipment_name": "Shure BLX24", "quantity": 3, "placement_notes": "Stage left"}
    ]


def test_ac3_a_listed_requirement_not_yet_reserved_has_no_placement_yet(client, db_session):
    w = _world(client, db_session)

    [row] = _listed(client, w.tech)

    assert row["reservations"] == []


def test_ac3_the_listed_shape_is_what_the_manage_panel_is_given_plus_its_event(client, db_session):
    """Opening a row needs no second request: it carries everything the
    existing Manage panel reads, and nothing of the Coordinator's own
    bookkeeping (no author, no link to the Organiser's pick)."""
    w = _world(client, db_session)

    [row] = _listed(client, w.tech)

    assert set(row) == {
        "id", "category", "quantity_needed", "technical_notes", "status",
        "reserved_quantity", "released_quantity", "unavailable_reason", "reservations", "event",
    }
    assert set(row["event"]) == {"id", "name", "proposed_start", "proposed_end"}


def test_ac3_the_listed_requirement_can_be_reserved_through_the_existing_route(client, db_session):
    w = _world(client, db_session, needed=4)

    assert _reserve(client, w.tech, w.rid, w.mic.id).status_code == 200
    assert _listed(client, w.tech) == []


# ---------------------------------------------------------------------------
# AC4 -- only Technical Support
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "role", [Role.COORDINATOR, Role.ORGANISER, Role.VENUE_STAFF, Role.ATTENDEE, Role.SAFETY_OFFICER]
)
def test_ac4_anyone_but_technical_support_is_denied(client, db_session, role):
    w = _world(client, db_session)
    _, headers = _user(client, db_session, role)

    assert client.get(PATH, headers=headers).status_code == 403


def test_ac4_the_denial_gives_away_nothing(client, db_session):
    w = _world(client, db_session)
    _, headers = _user(client, db_session, Role.COORDINATOR)

    body = client.get(PATH, headers=headers).json()

    assert "Audio" not in str(body) and w.event.name not in str(body)


def test_ac4_an_anonymous_caller_is_denied(client, db_session):
    _world(client, db_session)

    assert client.get(PATH).status_code == 401
