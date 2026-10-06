"""Tests for the Technical Support equipment stories.

SCRUM-45 Check Equipment Availability -- is there enough for an event's
date and time?
SCRUM-46 Reserve Equipment -- reserve against true availability, so items
are not committed to conflicting events.

A reservation is the event's equipment request moved to `reserved`; it holds
its units for the event's window and frees them at the event's end time.
Test names carry the acceptance criterion they prove.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.roles import Role
from app.models.enums import EquipmentStatus, EventStatus
from app.models.equipment import Equipment, EquipmentRequest
from app.models.events import Event
from tests.event_review_test_helpers import user

START = datetime(2026, 11, 2, 9, tzinfo=timezone.utc)
END = datetime(2026, 11, 2, 17, tzinfo=timezone.utc)
HOUR = timedelta(hours=1)


@pytest.fixture()
def tech(client, db_session):
    return user(client, db_session, Role.TECH_SUPPORT, "tech@example.com", "Tess Tech")


@pytest.fixture()
def organiser(client, db_session):
    return user(client, db_session, Role.ORGANISER, "organiser@example.com", "Olivia Org")


@pytest.fixture()
def item(db_session):
    projector = Equipment(name="Projector", category="Projection", total_quantity=10)
    db_session.add(projector)
    db_session.commit()
    return projector


def _event(db_session, organiser, item, needs, name="Conference", status=EventStatus.event_approved,
           start=START, end=END):
    """An event that asked for `needs` of `item`."""
    event = Event(name=name, organiser_id=organiser[0].id, status=status, proposed_start=start, proposed_end=end)
    db_session.add(event)
    db_session.flush()
    db_session.add(EquipmentRequest(event_id=event.id, equipment_id=item.id, quantity_requested=needs))
    db_session.commit()
    return event


def _check(client, headers, item, start=START, end=END, event=None):
    params = {"equipment_id": item.id, "start": start.isoformat(), "end": end.isoformat()}
    if event is not None:
        params["event_id"] = event.id
    return client.get("/equipment-reservations/availability", params=params, headers=headers)


def _reserve(client, headers, event, item):
    return client.post(
        "/equipment-reservations", json={"event_id": event.id, "equipment_id": item.id}, headers=headers
    )


def _line(db_session, event):
    db_session.expire_all()
    return db_session.query(EquipmentRequest).filter_by(event_id=event.id).one()


# --- SCRUM-45 Check Equipment Availability ---------------------------------


def test_scrum45_ac1_shows_the_available_quantity_for_the_window(client, tech, item):
    body = _check(client, tech[1], item).json()

    assert (body["total_quantity"], body["reserved_quantity"], body["available_quantity"]) == (10, 0, 10)
    assert body["start_time"].startswith("2026-11-02T09:00")
    assert body["end_time"].startswith("2026-11-02T17:00")


def test_scrum45_ac2_units_reserved_for_an_overlapping_event_are_not_available(
    client, db_session, tech, organiser, item
):
    overlapping = _event(db_session, organiser, item, 4, "Overlaps", start=END - HOUR, end=END + HOUR)
    back_to_back = _event(db_session, organiser, item, 3, "Back to back", start=END, end=END + 2 * HOUR)
    _event(db_session, organiser, item, 5, "Only requested")  # not reserved: holds nothing
    _reserve(client, tech[1], overlapping, item)
    _reserve(client, tech[1], back_to_back, item)

    body = _check(client, tech[1], item).json()

    assert body["reserved_quantity"] == 4
    assert body["available_quantity"] == 6


def test_scrum45_ac3_indicates_insufficient_stock_against_what_the_event_requires(
    client, db_session, tech, organiser, item
):
    _reserve(client, tech[1], _event(db_session, organiser, item, 4, "Other"), item)
    needs_seven = _event(db_session, organiser, item, 7, "Needs 7")
    needs_six = _event(db_session, organiser, item, 6, "Needs 6")

    short = _check(client, tech[1], item, event=needs_seven).json()
    exact = _check(client, tech[1], item, event=needs_six).json()

    assert (short["required_quantity"], short["sufficient"]) == (7, False)
    assert (exact["required_quantity"], exact["sufficient"]) == (6, True)


def test_scrum45_lists_approved_events_with_what_they_require(client, db_session, tech, organiser, item):
    approved = _event(db_session, organiser, item, 4)
    _event(db_session, organiser, item, 1, "Under review", status=EventStatus.under_review)

    events = client.get("/equipment-reservations/events", headers=tech[1]).json()

    assert [e["id"] for e in events] == [approved.id]
    assert events[0]["equipment_items"][0]["quantity_requested"] == 4


def test_scrum45_a_window_that_ends_before_it_starts_is_refused(client, tech, item):
    res = _check(client, tech[1], item, start=END, end=START)
    assert res.status_code == 422
    assert res.json()["detail"][0]["loc"] == ["query", "end"]


# --- SCRUM-46 Reserve Equipment --------------------------------------------


def test_scrum46_ac1_a_request_exceeding_the_available_quantity_is_refused_with_the_amount_available(
    client, db_session, tech, organiser, item
):
    _reserve(client, tech[1], _event(db_session, organiser, item, 4, "Other"), item)
    too_many = _event(db_session, organiser, item, 7, "Needs 7")
    fits = _event(db_session, organiser, item, 6, "Needs 6")

    refused = _reserve(client, tech[1], too_many, item)
    assert refused.status_code == 409
    assert refused.json()["detail"].startswith("Only 6 Projector available")
    assert _line(db_session, too_many).status is EquipmentStatus.requested  # nothing changed

    assert _reserve(client, tech[1], fits, item).status_code == 200


def test_scrum46_ac2_the_reservation_records_equipment_quantity_event_date_and_times(
    client, db_session, tech, organiser, item
):
    event = _event(db_session, organiser, item, 3, "Partner Conference")

    body = _reserve(client, tech[1], event, item).json()

    assert body["equipment_name"] == "Projector"
    assert body["equipment_category"] == "Projection"
    assert body["quantity"] == 3
    assert body["event"] == {"id": event.id, "name": "Partner Conference"}
    assert body["start_time"].startswith("2026-11-02T09:00")
    assert body["end_time"].startswith("2026-11-02T17:00")
    assert body["reserved_by"]["name"] == "Tess Tech"  # audit: actor
    assert body["reserved_at"]  # audit: time

    line = _line(db_session, event)
    assert (line.status, line.reviewed_by) == (EquipmentStatus.reserved, tech[0].id)
    listed = client.get("/equipment-reservations", params={"event_id": event.id}, headers=tech[1]).json()
    assert [r["id"] for r in listed] == [body["id"]]


def test_scrum46_ac3_reserved_units_are_deducted_until_the_event_ends(client, db_session, tech, organiser, item):
    _reserve(client, tech[1], _event(db_session, organiser, item, 3), item)

    assert _check(client, tech[1], item, START + 4 * HOUR, END + 4 * HOUR).json()["available_quantity"] == 7
    assert _check(client, tech[1], item, END, END + 4 * HOUR).json()["available_quantity"] == 10  # freed at end


def test_scrum46_reserving_the_same_request_twice_is_refused(client, db_session, tech, organiser, item):
    event = _event(db_session, organiser, item, 2)
    assert _reserve(client, tech[1], event, item).status_code == 200

    again = _reserve(client, tech[1], event, item)

    assert again.status_code == 409
    assert "already reserved" in again.json()["detail"]
    assert _check(client, tech[1], item).json()["reserved_quantity"] == 2


def test_scrum46_an_event_that_is_not_approved_cannot_have_equipment_reserved(
    client, db_session, tech, organiser, item
):
    event = _event(db_session, organiser, item, 1, status=EventStatus.under_review)
    assert _reserve(client, tech[1], event, item).status_code == 409
    assert _line(db_session, event).status is EquipmentStatus.requested


def _mic(db_session, total=5):
    mic = Equipment(name="Microphone", category="Audio", total_quantity=total)
    db_session.add(mic)
    db_session.commit()
    return mic


def test_scrum46_equipment_the_event_did_not_request_can_be_added_and_reserved_with_a_quantity(
    client, db_session, tech, organiser, item
):
    event = _event(db_session, organiser, item, 1)
    mic = _mic(db_session)

    res = client.post(
        "/equipment-reservations",
        json={"event_id": event.id, "equipment_id": mic.id, "quantity": 3},
        headers=tech[1],
    )

    assert res.status_code == 200
    assert (res.json()["equipment_name"], res.json()["quantity"]) == ("Microphone", 3)
    db_session.expire_all()
    line = db_session.query(EquipmentRequest).filter_by(event_id=event.id, equipment_id=mic.id).one()
    assert (line.status, line.reviewed_by, line.quantity_requested) == (EquipmentStatus.reserved, tech[0].id, 3)
    assert _check(client, tech[1], mic).json()["available_quantity"] == 2


@pytest.mark.parametrize(
    "quantity, code, message",
    [
        (None, 422, "has not requested Microphone; enter a quantity"),
        (6, 409, "Only 5 Microphone available"),
    ],
)
def test_scrum46_adding_unrequested_equipment_needs_a_quantity_within_what_is_available(
    client, db_session, tech, organiser, item, quantity, code, message
):
    event = _event(db_session, organiser, item, 1)
    mic = _mic(db_session)

    res = client.post(
        "/equipment-reservations",
        json={"event_id": event.id, "equipment_id": mic.id, "quantity": quantity},
        headers=tech[1],
    )

    assert res.status_code == code
    assert message in res.json()["detail"]
    assert db_session.query(EquipmentRequest).filter_by(equipment_id=mic.id).count() == 0


# --- Access (both stories) -------------------------------------------------


@pytest.mark.parametrize("role", [Role.ORGANISER, Role.COORDINATOR])
def test_only_technical_support_can_check_or_reserve(client, db_session, organiser, item, role):
    event = _event(db_session, organiser, item, 1)
    headers = organiser[1] if role is Role.ORGANISER else user(
        client, db_session, role, "coordinator@example.com", "Cora"
    )[1]

    assert _check(client, headers, item).status_code == 403
    assert _reserve(client, headers, event, item).status_code == 403
    assert _line(db_session, event).status is EquipmentStatus.requested
