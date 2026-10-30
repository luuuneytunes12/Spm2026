"""Tests for SCRUM-59 "Auto-Release Equipment on Event Cancellation or Completion".

    As a Technical Support Staff member, I want equipment reservations to be
    automatically released when an event is cancelled or completed, so that I
    do not need to manually free up equipment after every event.

The release follows the Event's status rather than a job that runs, so these
reserve through the API and then move the Event on.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.roles import Role
from app.models.enums import EventStatus
from app.models.equipment import Equipment, EquipmentRequest
from app.models.events import Event
from tests.event_review_test_helpers import user

RELEASING = [EventStatus.event_cancelled, EventStatus.event_completed]
TOTAL = 8
RESERVED = 5


def _approved_event(db_session, w, name):
    start = datetime.now(timezone.utc) + timedelta(days=5)
    event = Event(
        name=name,
        organiser_id=w["organiser"].id,
        status=EventStatus.event_approved,
        proposed_start=start,
        proposed_end=start + timedelta(hours=8),
    )
    db_session.add(event)
    db_session.flush()
    db_session.add(
        EquipmentRequest(event_id=event.id, equipment_id=w["item"].id, quantity_requested=RESERVED)
    )
    db_session.commit()
    return event


def _reserve(client, w, event):
    return client.post(
        "/equipment-reservations",
        json={"event_id": event.id, "equipment_id": w["item"].id},
        headers=w["tech"],
    )


@pytest.fixture()
def w(client, db_session):
    organiser, _ = user(client, db_session, Role.ORGANISER, "org@example.com", "Org")
    _, tech = user(client, db_session, Role.TECH_SUPPORT, "tech@example.com", "Tess Tech")
    item = Equipment(name="Projector", category="Projection", total_quantity=TOTAL)
    db_session.add(item)
    db_session.commit()
    w = {"organiser": organiser, "tech": tech, "item": item}
    w["event"] = _approved_event(db_session, w, "First")
    assert _reserve(client, w, w["event"]).status_code == 200
    return w


def _available(client, w):
    rows = client.get("/equipment", headers=w["tech"]).json()["items"]
    return next(row for row in rows if row["id"] == w["item"].id)["available_quantity"]


def _move_on(db_session, w, status):
    w["event"].status = status
    db_session.commit()


def test_ac1_ac2_reserved_stock_is_counted_as_taken_until_then(client, w):
    assert _available(client, w) == TOTAL - RESERVED


@pytest.mark.parametrize("status", RELEASING)
def test_ac1_ac2_the_released_quantity_returns_to_the_available_count(client, db_session, w, status):
    _move_on(db_session, w, status)
    assert _available(client, w) == TOTAL


@pytest.mark.parametrize(
    "status",
    [
        EventStatus.planning_event,
        EventStatus.awaiting_safety_check,
        EventStatus.safety_check_passed,
    ],
)
def test_ac1_other_status_changes_release_nothing(client, db_session, w, status):
    _move_on(db_session, w, status)
    assert _available(client, w) == TOTAL - RESERVED


@pytest.mark.parametrize("status", RELEASING)
def test_ac3_a_new_reservation_after_a_release_is_a_normal_one(client, db_session, w, status):
    _move_on(db_session, w, status)
    second = _approved_event(db_session, w, "Second")

    res = _reserve(client, w, second)

    assert res.status_code == 200
    assert res.json()["quantity"] == RESERVED
    assert _available(client, w) == TOTAL - RESERVED


def test_ac3_without_a_release_the_same_reservation_is_refused(client, db_session, w):
    second = _approved_event(db_session, w, "Second")
    assert _reserve(client, w, second).status_code == 409
