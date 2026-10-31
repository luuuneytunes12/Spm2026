"""Tests for "Mark Equipment Damaged or Under Maintenance" (SCRUM-115).

    AC1  marking some quantity saves it; it no longer counts as available
    AC2  the marked quantity is excluded for any time window
    AC3  a repaired quantity returned to service counts as available again
    AC4  above the total, zero or below zero is refused and nothing is saved
"""

from datetime import datetime, timezone

import pytest

from app.core.roles import Role
from app.models.enums import EquipmentOperationalStatus, EquipmentStatus, EventStatus
from app.models.equipment import Equipment, EquipmentActivity, EquipmentRequest
from app.models.events import Event
from app.models.user import User
from tests.test_equipment import _equipment, _user

DAMAGED = "damaged"
MAINTENANCE = "maintenance"
TECH = "tia@example.com"


@pytest.fixture()
def tech_h(client, db_session):
    return _user(client, db_session, Role.TECH_SUPPORT, TECH, "Tia Tech")


def _mark(client, headers, item, quantity, condition=DAMAGED):
    return client.post(
        f"/equipment/{item.id}/out-of-service",
        json={"condition": condition, "quantity": quantity},
        headers=headers,
    )


def _return(client, headers, item, quantity, condition=DAMAGED):
    return client.post(
        f"/equipment/{item.id}/return-to-service",
        json={"condition": condition, "quantity": quantity},
        headers=headers,
    )


def _available_in(client, headers, item, start, end):
    res = client.get(
        "/equipment-reservations/availability",
        params={"equipment_id": item.id, "start": start, "end": end},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    return res.json()


def _counts(db_session, item):
    db_session.expire_all()
    row = db_session.get(Equipment, item.id)
    return row.damaged_quantity, row.maintenance_quantity


def _log(db_session, item):
    db_session.expire_all()
    return db_session.query(EquipmentActivity).filter_by(equipment_id=item.id).all()


# --- AC1 --------------------------------------------------------------------


@pytest.mark.parametrize(("condition", "expected"), [(DAMAGED, (3, 0)), (MAINTENANCE, (0, 3))])
def test_ac1_marking_saves_and_reduces_available(client, db_session, tech_h, condition, expected):
    item = _equipment(db_session, "Mic", total_quantity=10)

    res = _mark(client, tech_h, item, 3, condition)

    assert res.status_code == 200, res.text
    assert res.json()["available_quantity"] == 7
    assert res.json()["operational_status"] == "available"
    assert _counts(db_session, item) == expected
    assert client.get("/equipment", headers=tech_h).json()["items"][0]["available_quantity"] == 7


def test_ac1_both_conditions_add_up(client, db_session, tech_h):
    item = _equipment(db_session, "Mic", total_quantity=10)
    assert _mark(client, tech_h, item, 2, DAMAGED).status_code == 200

    res = _mark(client, tech_h, item, 3, MAINTENANCE)

    assert (res.json()["damaged_quantity"], res.json()["maintenance_quantity"]) == (2, 3)
    assert res.json()["available_quantity"] == 5


def test_ac1_audit_records_who_and_when(client, db_session, tech_h):
    item = _equipment(db_session, "Mic", total_quantity=10)
    _mark(client, tech_h, item, 3, MAINTENANCE)

    [entry] = _log(db_session, item)

    assert entry.note == "Marked 3 as Under Maintenance."
    assert entry.changed_by == db_session.query(User).filter_by(email=TECH).one().id
    assert entry.created_at is not None


# --- AC2 --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2020-01-01T00:00:00Z", "2020-01-02T00:00:00Z"),
        ("2030-11-02T09:00:00Z", "2030-11-02T17:00:00Z"),
        ("2099-01-01T00:00:00Z", "2099-12-31T00:00:00Z"),
    ],
)
def test_ac2_excluded_for_any_window(client, db_session, tech_h, start, end):
    item = _equipment(db_session, "Mic", total_quantity=10)
    _mark(client, tech_h, item, 4)

    body = _available_in(client, tech_h, item, start, end)

    assert body["available_quantity"] == 6
    assert body["out_of_service_quantity"] == 4
    assert body["total_quantity"] == 10


def _event_reserving(db_session, item, quantity):
    organiser = db_session.query(User).filter_by(email=TECH).one()
    event = Event(
        name="Gala",
        organiser_id=organiser.id,
        status=EventStatus.planning_event,
        proposed_start=datetime(2030, 11, 2, 9, tzinfo=timezone.utc),
        proposed_end=datetime(2030, 11, 2, 17, tzinfo=timezone.utc),
    )
    db_session.add(event)
    db_session.flush()
    if quantity:
        db_session.add(
            EquipmentRequest(
                event_id=event.id,
                equipment_id=item.id,
                quantity_requested=quantity,
                status=EquipmentStatus.reserved,
            )
        )
    db_session.commit()
    return event


def test_ac2_excluded_on_top_of_reservations(client, db_session, tech_h):
    item = _equipment(db_session, "Mic", total_quantity=10)
    _event_reserving(db_session, item, 5)
    _mark(client, tech_h, item, 3)

    body = _available_in(client, tech_h, item, "2030-11-02T10:00:00Z", "2030-11-02T11:00:00Z")

    assert body["available_quantity"] == 2
    assert body["reserved_quantity"] == 5


def test_ac2_more_out_than_is_free_reports_none_and_keeps_the_reservation(client, db_session, tech_h):
    item = _equipment(db_session, "Mic", total_quantity=10)
    _event_reserving(db_session, item, 8)

    assert _mark(client, tech_h, item, 5).status_code == 200

    body = _available_in(client, tech_h, item, "2030-11-02T10:00:00Z", "2030-11-02T11:00:00Z")
    assert body["available_quantity"] == 0
    db_session.expire_all()
    assert db_session.query(EquipmentRequest).one().status == EquipmentStatus.reserved


def test_ac2_a_marked_unit_cannot_be_reserved(client, db_session, tech_h):
    item = _equipment(db_session, "Mic", total_quantity=4)
    event = _event_reserving(db_session, item, 0)
    _mark(client, tech_h, item, 2)

    def reserve(quantity):
        return client.post(
            "/equipment-reservations",
            json={"event_id": event.id, "equipment_id": item.id, "quantity": quantity},
            headers=tech_h,
        )

    refused = reserve(3)

    assert refused.status_code == 409
    assert "Only 2" in refused.json()["detail"]
    assert db_session.query(EquipmentRequest).count() == 0
    assert reserve(2).status_code == 200


# --- AC3 --------------------------------------------------------------------


def test_ac3_returned_units_are_available_again(client, db_session, tech_h):
    item = _equipment(db_session, "Mic", total_quantity=10)
    _mark(client, tech_h, item, 4)

    res = _return(client, tech_h, item, 3)

    assert res.status_code == 200, res.text
    assert res.json()["available_quantity"] == 9
    assert _counts(db_session, item) == (1, 0)
    body = _available_in(client, tech_h, item, "2030-11-02T09:00:00Z", "2030-11-02T17:00:00Z")
    assert body["available_quantity"] == 9
    assert [e.note for e in _log(db_session, item)] == [
        "Marked 4 as Damaged.",
        "Returned 3 from Damaged to service.",
    ]


@pytest.mark.parametrize("marked", [DAMAGED, MAINTENANCE])
def test_ac3_negative_cannot_return_more_than_is_marked(client, db_session, tech_h, marked):
    item = _equipment(db_session, "Mic", total_quantity=10)
    _mark(client, tech_h, item, 2, marked)

    assert _return(client, tech_h, item, 3, marked).status_code == 422

    other = MAINTENANCE if marked == DAMAGED else DAMAGED
    assert _return(client, tech_h, item, 1, other).status_code == 422
    assert sum(_counts(db_session, item)) == 2
    assert len(_log(db_session, item)) == 1


# --- AC4 --------------------------------------------------------------------


@pytest.mark.parametrize("quantity", [11, 0, -1, 2**40, 2.5, "2", True, None])
def test_ac4_bad_quantity_is_refused_and_nothing_saved(client, db_session, tech_h, quantity):
    item = _equipment(db_session, "Mic", total_quantity=10)

    res = _mark(client, tech_h, item, quantity)

    assert res.status_code == 422
    assert _counts(db_session, item) == (0, 0)
    assert _log(db_session, item) == []


def test_ac4_above_what_is_left_counts_what_is_already_out(client, db_session, tech_h):
    item = _equipment(db_session, "Mic", total_quantity=10)
    _mark(client, tech_h, item, 6, DAMAGED)

    res = _mark(client, tech_h, item, 5, MAINTENANCE)

    assert res.status_code == 422
    assert "Only 4 of 10" in res.json()["detail"][0]["msg"]
    assert _counts(db_session, item) == (6, 0)


def test_ac4_exactly_all_of_it_is_allowed(client, db_session, tech_h):
    item = _equipment(db_session, "Mic", total_quantity=10)

    res = _mark(client, tech_h, item, 10)

    assert res.status_code == 200
    assert res.json()["available_quantity"] == 0


@pytest.mark.parametrize("condition", ["available", "retired", "broken"])
def test_negative_only_damaged_or_maintenance_can_be_marked(client, db_session, tech_h, condition):
    item = _equipment(db_session, "Mic", total_quantity=10)

    assert _mark(client, tech_h, item, 1, condition).status_code == 422
    assert _counts(db_session, item) == (0, 0)


@pytest.mark.parametrize(
    "status",
    [
        EquipmentOperationalStatus.damaged,
        EquipmentOperationalStatus.maintenance,
        EquipmentOperationalStatus.retired,
    ],
)
def test_negative_item_with_a_status_as_a_whole_is_refused(client, db_session, tech_h, status):
    item = _equipment(db_session, "Mixer", total_quantity=2, operational_status=status)

    res = _mark(client, tech_h, item, 1)

    assert res.status_code == 409
    assert "as a whole" in res.json()["detail"]
    assert _counts(db_session, item) == (0, 0)
    assert _log(db_session, item) == []


def test_negative_unknown_equipment_is_404(client, tech_h):
    res = client.post(
        "/equipment/999/out-of-service", json={"condition": DAMAGED, "quantity": 1}, headers=tech_h
    )
    assert res.status_code == 404


# --- access -----------------------------------------------------------------


@pytest.mark.parametrize("role", [Role.ORGANISER, Role.COORDINATOR, Role.VENUE_STAFF, Role.ATTENDEE])
@pytest.mark.parametrize("action", [_mark, _return])
def test_negative_other_roles_are_denied(client, db_session, role, action):
    item = _equipment(db_session, "Mic", total_quantity=10, damaged_quantity=2)
    headers = _user(client, db_session, role, f"{role.value}@example.com")

    assert action(client, headers, item, 1).status_code == 403
    assert _counts(db_session, item) == (2, 0)
    assert _log(db_session, item) == []


def test_negative_not_logged_in_is_refused(client, db_session):
    item = _equipment(db_session, "Mic", total_quantity=10)
    assert _mark(client, {}, item, 1).status_code == 401
    assert _counts(db_session, item) == (0, 0)


def test_frozen_literal_an_unmarked_item_reports_total_minus_reserved(client, db_session, tech_h):
    item = _equipment(db_session, "Mic", total_quantity=10)
    _event_reserving(db_session, item, 3)

    body = _available_in(client, tech_h, item, "2030-11-02T10:00:00Z", "2030-11-02T11:00:00Z")

    assert body["available_quantity"] == 7
    assert body["out_of_service_quantity"] == 0
