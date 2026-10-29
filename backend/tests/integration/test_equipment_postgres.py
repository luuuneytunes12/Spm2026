"""Equipment on real PostgreSQL:

    SCRUM-42  View Equipment Catalogue
    SCRUM-43  Record Equipment Requirements for Event
    SCRUM-44  Update Equipment Requirement Status
    SCRUM-45  Check Equipment Availability
    SCRUM-46  Reserve Equipment for Event
    SCRUM-100 View Equipment Requirements as Technical Support Staff

The SQLite tests (tests/test_equipment.py, test_equipment_requirements.py,
test_equipment_requirement_fulfillment.py, test_equipment_reservations.py,
test_requested_requirements_list.py) prove the rules. Availability is a sum
over reservations whose event window overlaps -- a timestamptz comparison --
and reserving locks the item row so two people cannot both take the last
units. SQLite has neither real time zones nor row locks; these tests run the
same paths on the production engine, and race the reservations.
"""

from datetime import datetime, timezone

import pytest

from app.core.roles import Role
from app.models.enums import EquipmentOperationalStatus, EquipmentStatus, EventStatus
from app.models.equipment import CoordinatorEquipmentRequirement, Equipment, EquipmentRequest
from app.models.events import Event, EventStatusHistory
from tests.integration.conftest import assign_event, submit_event
from tests.integration.test_coordinator_concurrency_postgres import THREADS, race

pytestmark = pytest.mark.integration

START = "2026-11-02T09:00:00Z"
END = "2026-11-02T17:00:00Z"


@pytest.fixture()
def catalogue(db):
    items = [
        Equipment(name="Shure BLX24", category="Audio", description="Wireless handheld mic", total_quantity=4,
                  location="Store B1", operational_status=EquipmentOperationalStatus.available),
        Equipment(name="Yamaha PA", category="Audio", description="Portable PA", total_quantity=2,
                  location="Store B1", operational_status=EquipmentOperationalStatus.available),
        Equipment(name="Epson EB-L200SW", category="Projection", description="Short-throw projector",
                  total_quantity=3, location="Store A2", operational_status=EquipmentOperationalStatus.available),
        Equipment(name="Old Projector", category="Projection", description="Lamp failing", total_quantity=1,
                  location="Store A2", operational_status=EquipmentOperationalStatus.maintenance),
    ]
    db.add_all(items)
    db.commit()
    return {i.name: i.id for i in items}


@pytest.fixture()
def world(client, make_user, db, catalogue):
    """An approved, dated event assigned to Cora, Technical Support, and the catalogue."""
    _o, org_h = make_user(Role.ORGANISER, "org@connectsphere.test", "Olivia Organiser")
    coordinator, coord_h = make_user(Role.COORDINATOR, "cora@connectsphere.test", "Cora Coord")
    _l, lead_h = make_user(Role.COORDINATOR_LEAD, "lena@connectsphere.test", "Lena Lead")
    tech, tech_h = make_user(Role.TECH_SUPPORT, "tia@connectsphere.test", "Tia Tech")

    def approved_event(**fields):
        event_id = submit_event(client, org_h, proposed_start=fields.pop("start", START),
                                proposed_end=fields.pop("end", END), **fields)
        assign_event(client, lead_h, event_id, coordinator.id)
        assert client.post(f"/events/{event_id}/approve", headers=coord_h).status_code == 200
        return event_id

    return dict(org_h=org_h, coordinator=coordinator, coord_h=coord_h, tech=tech, tech_h=tech_h,
                lead_h=lead_h, items=catalogue, approved_event=approved_event)


def _add_requirement(client, coord_h, event_id, **body):
    res = client.post(f"/equipment-requirements/events/{event_id}",
                      json={"category": "Audio", "quantity_needed": 2, **body}, headers=coord_h)
    assert res.status_code == 201, res.text
    return res.json()


# --------------------------------------------------------------------------
# SCRUM-42 View Equipment Catalogue
# --------------------------------------------------------------------------


def test_scrum42_ac1_ac2_every_item_shows_type_description_quantity_location_and_status(client, world):
    catalogue = client.get("/equipment", headers=world["tech_h"]).json()

    by_name = {i["name"]: i for i in catalogue["items"]}
    assert set(by_name) == set(world["items"])
    mic = by_name["Shure BLX24"]
    assert (mic["category"], mic["description"], mic["total_quantity"], mic["location"]) == (
        "Audio", "Wireless handheld mic", 4, "Store B1")
    assert mic["operational_status"] == "available" and mic["available_quantity"] == 4
    assert by_name["Old Projector"]["operational_status"] == "maintenance"
    assert sorted(catalogue["types"]) == ["Audio", "Projection"]


def test_scrum42_ac3_filter_by_type_and_search_by_text(client, world):
    audio = client.get("/equipment", params={"type": "Audio"}, headers=world["tech_h"]).json()["items"]
    assert sorted(i["name"] for i in audio) == ["Shure BLX24", "Yamaha PA"]
    found = client.get("/equipment", params={"q": "short-throw"}, headers=world["tech_h"]).json()["items"]
    assert [i["name"] for i in found] == ["Epson EB-L200SW"]


def test_scrum42_the_catalogue_is_closed_to_roles_without_equipment_read(client, world, make_user):
    _a, attendee_h = make_user(Role.ATTENDEE, "ava@connectsphere.test")
    _s, safety_h = make_user(Role.SAFETY_OFFICER, "sol@connectsphere.test")

    assert client.get("/equipment", headers=attendee_h).status_code == 403
    assert client.get("/equipment", headers=safety_h).status_code == 403
    assert client.get("/equipment", headers=world["coord_h"]).status_code == 200


# --------------------------------------------------------------------------
# SCRUM-43 Record Equipment Requirements for Event
# --------------------------------------------------------------------------


def test_scrum43_ac1_ac2_a_requirement_is_stored_and_visible_to_technical_support(client, world, db):
    event_id = world["approved_event"]()

    added = _add_requirement(client, world["coord_h"], event_id, category="Projection", quantity_needed=2,
                             technical_notes="HDMI and USB-C; mounted at rear of hall")

    assert added["status"] == "requested" and added["quantity_needed"] == 2
    db.expire_all()
    row = db.get(CoordinatorEquipmentRequirement, added["id"])
    assert row.created_by == world["coordinator"].id and row.event_id == event_id
    record = client.get(f"/equipment-requirements/support/events/{event_id}", headers=world["tech_h"]).json()
    [seen] = record["requirements"]
    assert (seen["category"], seen["quantity_needed"], seen["technical_notes"]) == (
        "Projection", 2, "HDMI and USB-C; mounted at rear of hall")
    assert record["coordinator"]["name"] == "Cora Coord"


def test_scrum43_bad_requirements_are_refused_and_nothing_is_stored(client, world, db):
    event_id = world["approved_event"]()

    assert client.post(f"/equipment-requirements/events/{event_id}", json={"category": "Audio", "quantity_needed": 0},
                       headers=world["coord_h"]).status_code == 422
    unknown = client.post(f"/equipment-requirements/events/{event_id}",
                          json={"category": "Teleporter", "quantity_needed": 1}, headers=world["coord_h"])
    assert unknown.status_code in (404, 409, 422)
    assert db.query(CoordinatorEquipmentRequirement).count() == 0


def test_scrum43_only_the_assigned_coordinator_records_requirements(client, world, make_user, db):
    event_id = world["approved_event"]()
    _x, other_h = make_user(Role.COORDINATOR, "priya@connectsphere.test", "Priya Nair")

    res = client.post(f"/equipment-requirements/events/{event_id}", json={"category": "Audio", "quantity_needed": 1},
                      headers=other_h)

    assert res.status_code in (403, 404)
    assert client.get(f"/equipment-requirements/events/{event_id}", headers=other_h).status_code in (403, 404)
    assert db.query(CoordinatorEquipmentRequirement).count() == 0


def test_scrum43_the_coordinator_can_edit_and_remove_a_requirement(client, world, db):
    event_id = world["approved_event"]()
    added = _add_requirement(client, world["coord_h"], event_id)

    edited = client.patch(f"/equipment-requirements/{added['id']}", json={"quantity_needed": 3},
                          headers=world["coord_h"])
    assert edited.status_code == 200 and edited.json()["quantity_needed"] == 3
    assert client.delete(f"/equipment-requirements/{added['id']}", headers=world["coord_h"]).status_code == 204
    assert client.get(f"/equipment-requirements/events/{event_id}", headers=world["coord_h"]).json() == []


# --------------------------------------------------------------------------
# SCRUM-100 Equipment Requests list for Technical Support
# --------------------------------------------------------------------------


def test_scrum100_ac1_requested_rows_list_event_type_quantity_and_date_oldest_first(client, world):
    later = world["approved_event"](name="Later Event", start="2026-12-01T09:00:00Z", end="2026-12-01T17:00:00Z")
    sooner = world["approved_event"](name="Sooner Event")
    _add_requirement(client, world["coord_h"], later, category="Projection", quantity_needed=1)
    _add_requirement(client, world["coord_h"], sooner, category="Audio", quantity_needed=2)

    rows = client.get("/equipment-requirements/support/requested", headers=world["tech_h"]).json()

    assert [r["event"]["name"] for r in rows] == ["Sooner Event", "Later Event"]
    assert (rows[0]["category"], rows[0]["quantity_needed"]) == ("Audio", 2)
    assert rows[0]["event"]["proposed_start"].startswith("2026-11-02T09:00")


def test_scrum100_ac2_with_nothing_requested_the_list_is_empty(client, world):
    assert client.get("/equipment-requirements/support/requested", headers=world["tech_h"]).json() == []


def test_scrum100_ac4_nobody_else_may_open_the_list(client, world, make_user):
    for role in (Role.COORDINATOR, Role.ORGANISER, Role.VENUE_STAFF, Role.ATTENDEE):
        _u, headers = make_user(role, f"x-{role.value}@connectsphere.test")
        assert client.get("/equipment-requirements/support/requested", headers=headers).status_code == 403


# --------------------------------------------------------------------------
# SCRUM-45 Check Equipment Availability / SCRUM-46 Reserve Equipment
# --------------------------------------------------------------------------


def _availability(client, tech_h, equipment_id, start=START, end=END, **params):
    res = client.get("/equipment-reservations/availability",
                     params={"equipment_id": equipment_id, "start": start, "end": end, **params}, headers=tech_h)
    assert res.status_code == 200, res.text
    return res.json()


def _reserve(client, tech_h, event_id, equipment_id, quantity=None, **extra):
    body = {"event_id": event_id, "equipment_id": equipment_id, **extra}
    if quantity is not None:
        body["quantity"] = quantity
    return client.post("/equipment-reservations", json=body, headers=tech_h)


def test_scrum45_ac1_free_stock_is_shown_for_a_window(client, world):
    mic = world["items"]["Shure BLX24"]

    free = _availability(client, world["tech_h"], mic)

    assert (free["total_quantity"], free["reserved_quantity"], free["available_quantity"]) == (4, 0, 4)


def test_scrum45_ac2_scrum46_ac3_overlapping_reservations_are_deducted_and_touching_ones_are_not(client, world):
    mic = world["items"]["Shure BLX24"]
    morning = world["approved_event"](name="Morning", start="2026-11-02T09:00:00Z", end="2026-11-02T12:00:00Z")
    assert _reserve(client, world["tech_h"], morning, mic, 3).status_code == 200

    overlapping = _availability(client, world["tech_h"], mic, "2026-11-02T11:00:00Z", "2026-11-02T13:00:00Z")
    touching = _availability(client, world["tech_h"], mic, "2026-11-02T12:00:00Z", "2026-11-02T13:00:00Z")
    other_zone = _availability(client, world["tech_h"], mic, "2026-11-02T19:30:00+08:00", "2026-11-02T21:00:00+08:00")

    assert overlapping["available_quantity"] == 1 and overlapping["reserved_quantity"] == 3
    assert touching["available_quantity"] == 4
    assert other_zone["available_quantity"] == 1  # 11:30Z-13:00Z, given in +08:00


def test_scrum45_ac3_insufficient_stock_is_flagged_against_what_the_event_asked_for(client, world, db):
    pa = world["items"]["Yamaha PA"]
    event_id = world["approved_event"]()
    db.add(EquipmentRequest(event_id=event_id, equipment_id=pa, quantity_requested=3))
    db.commit()

    result = _availability(client, world["tech_h"], pa, event_id=event_id)

    assert result["required_quantity"] == 3 and result["available_quantity"] == 2
    assert result["sufficient"] is False


def test_scrum46_ac1_ac2_a_reservation_records_type_quantity_event_and_window(client, world, db):
    projector = world["items"]["Epson EB-L200SW"]
    event_id = world["approved_event"]()

    res = _reserve(client, world["tech_h"], event_id, projector, 2, placement_notes="Rear of hall, left")

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["quantity"] == 2 and body["start_time"].startswith("2026-11-02T09:00")
    assert body["end_time"].startswith("2026-11-02T17:00")
    db.expire_all()
    line = db.query(EquipmentRequest).filter_by(event_id=event_id, equipment_id=projector).one()
    assert line.status == EquipmentStatus.reserved and line.reviewed_by == world["tech"].id
    assert line.reviewed_at is not None and line.placement_notes == "Rear of hall, left"
    listed = client.get("/equipment-reservations", params={"event_id": event_id}, headers=world["tech_h"]).json()
    assert [r["quantity"] for r in listed] == [2]


def test_scrum46_ac1_you_cannot_reserve_more_than_is_free(client, world, db):
    pa = world["items"]["Yamaha PA"]
    first = world["approved_event"](name="First")
    second = world["approved_event"](name="Second")
    assert _reserve(client, world["tech_h"], first, pa, 2).status_code == 200

    refused = _reserve(client, world["tech_h"], second, pa, 1)

    assert refused.status_code == 409 and "Only 0" in refused.json()["detail"]
    assert db.query(EquipmentRequest).filter_by(event_id=second).count() == 0


def test_scrum46_equipment_is_only_reserved_for_an_approved_event(client, world, db):
    submitted = submit_event(client, world["org_h"])

    res = _reserve(client, world["tech_h"], submitted, world["items"]["Yamaha PA"], 1)

    assert res.status_code == 409
    assert db.query(EquipmentRequest).count() == 0


def test_scrum46_racing_for_the_last_units_never_overcommits_stock(make_client, client, world, db):
    pa = world["items"]["Yamaha PA"]  # 2 units
    events = [world["approved_event"](name=f"Event {i}") for i in range(THREADS)]
    calls = iter(events)

    results = race(make_client, THREADS, lambda c: _reserve(c, world["tech_h"], next(calls), pa, 1).status_code)

    assert sorted(results) == [200, 200] + [409] * (THREADS - 2)
    db.expire_all()
    reserved = sum(l.quantity_requested for l in db.query(EquipmentRequest).filter_by(
        equipment_id=pa, status=EquipmentStatus.reserved))
    assert reserved == 2
    assert _availability(client, world["tech_h"], pa)["available_quantity"] == 0


# --------------------------------------------------------------------------
# SCRUM-44 Update Equipment Requirement Status
# --------------------------------------------------------------------------


def test_scrum44_ac1_ac3_reserving_for_a_requirement_shows_reserved_to_the_coordinator(client, world):
    event_id = world["approved_event"]()
    req = _add_requirement(client, world["coord_h"], event_id, category="Audio", quantity_needed=3)
    mic = world["items"]["Shure BLX24"]

    partly = client.post(f"/equipment-requirements/{req['id']}/reservations",
                         json={"equipment_id": mic, "quantity": 2}, headers=world["tech_h"])
    assert partly.status_code == 200, partly.text
    assert partly.json()["status"] == "requested" and partly.json()["reserved_quantity"] == 2

    whole = client.post(f"/equipment-requirements/{req['id']}/reservations",
                        json={"equipment_id": world["items"]["Yamaha PA"], "quantity": 1}, headers=world["tech_h"])
    assert whole.status_code == 200 and whole.json()["status"] == "reserved"

    [seen] = client.get(f"/equipment-requirements/events/{event_id}", headers=world["coord_h"]).json()
    assert seen["status"] == "reserved" and seen["reserved_quantity"] == 3
    assert sorted(r["equipment_name"] for r in seen["reservations"]) == ["Shure BLX24", "Yamaha PA"]
    assert _availability(client, world["tech_h"], mic)["available_quantity"] == 2


def test_scrum44_ac1_unavailable_needs_a_reason_and_is_logged(client, world, db):
    event_id = world["approved_event"]()
    req = _add_requirement(client, world["coord_h"], event_id)
    url = f"/equipment-requirements/support/requirements/{req['id']}"

    assert client.patch(url, json={"status": "unavailable"}, headers=world["tech_h"]).status_code == 422
    res = client.patch(url, json={"status": "unavailable", "reason": "All mics booked by the gala"},
                       headers=world["tech_h"])

    assert res.status_code == 200 and res.json()["status"] == "unavailable"
    [seen] = client.get(f"/equipment-requirements/events/{event_id}", headers=world["coord_h"]).json()
    assert seen["status"] == "unavailable" and seen["unavailable_reason"] == "All mics booked by the gala"
    db.expire_all()
    notes = [h.note or "" for h in db.query(EventStatusHistory).filter_by(event_id=event_id)]
    assert any("All mics booked by the gala" in n for n in notes)


def test_scrum44_ac2_technical_support_updates_the_quantity(client, world, db):
    event_id = world["approved_event"]()
    req = _add_requirement(client, world["coord_h"], event_id, quantity_needed=2)

    res = client.patch(f"/equipment-requirements/support/requirements/{req['id']}", json={"quantity_needed": 4},
                       headers=world["tech_h"])

    assert res.status_code == 200 and res.json()["quantity_needed"] == 4
    db.expire_all()
    assert db.get(CoordinatorEquipmentRequirement, req["id"]).quantity_needed == 4
    [seen] = client.get(f"/equipment-requirements/events/{event_id}", headers=world["coord_h"]).json()
    assert seen["quantity_needed"] == 4


def test_scrum44_reserved_cannot_be_typed_in_by_hand(client, world):
    event_id = world["approved_event"]()
    req = _add_requirement(client, world["coord_h"], event_id)

    res = client.patch(f"/equipment-requirements/support/requirements/{req['id']}", json={"status": "reserved"},
                       headers=world["tech_h"])

    assert res.status_code in (409, 422)
    [seen] = client.get(f"/equipment-requirements/events/{event_id}", headers=world["coord_h"]).json()
    assert seen["status"] == "requested"


def test_scrum44_only_technical_support_updates_status(client, world, make_user):
    event_id = world["approved_event"]()
    req = _add_requirement(client, world["coord_h"], event_id)

    for headers in (world["coord_h"], world["org_h"], world["lead_h"]):
        res = client.patch(f"/equipment-requirements/support/requirements/{req['id']}",
                           json={"status": "unavailable", "reason": "x"}, headers=headers)
        assert res.status_code == 403
