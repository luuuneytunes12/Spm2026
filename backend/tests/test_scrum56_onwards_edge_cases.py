"""Refusal and failure paths no other test reaches, for stories SCRUM-56 onwards.

Each story's main tests live in its own file; only the branches those leave
unexecuted are here, named after the story and criterion they belong to.
"""

import asyncio
from datetime import timedelta

import pytest

from app.models.enums import BookingStatus, EquipmentStatus, EventStatus, NotificationType
from app.models.equipment import Equipment, EquipmentRequest
from app.models.events import Event
from app.models.notifications import Notification
from app.models.venues import VenueBooking
from app.services.hold_sweeper import HoldSweeper
from tests.test_clarifications import _awaiting, _event, _log, _reply, w  # noqa: F401
from tests.test_safety_checks import _post, _setup
from tests.test_venue_booking_decision import _setup as _booking_setup
from tests.test_venue_hold_expiry import _hold, _reminders, _status, _sweep


# --- SCRUM-89: Reject or Request Changes in Operational Safety Check ----------


def _state(db_session, s):
    db_session.expire_all()
    return db_session.get(Event, s["event_id"]).status


def test_scrum89_ac2_requesting_changes_with_nothing_marked_is_refused(client, db_session):
    s = _setup(client, db_session)

    res = _post(client, s, "request-changes", reason="Too crowded.", venue_booking_ids=[], equipment_request_ids=[])

    assert res.status_code == 422
    assert _state(db_session, s) == EventStatus.awaiting_safety_check


@pytest.mark.parametrize("field", ["venue_booking_ids", "equipment_request_ids"])
def test_scrum89_ac2_marking_something_not_on_this_event_is_refused(client, db_session, field):
    s = _setup(client, db_session)
    marked = {"venue_booking_ids": [], "equipment_request_ids": [], field: [999999]}

    res = _post(client, s, "request-changes", reason="Too crowded.", **marked)

    assert res.status_code == 422
    assert _state(db_session, s) == EventStatus.awaiting_safety_check
    assert db_session.get(VenueBooking, s["booking_id"]).status == BookingStatus.approved
    assert db_session.get(EquipmentRequest, s["line_id"]).status == EquipmentStatus.reserved


@pytest.mark.parametrize("action", ["approve", "reject", "request-changes"])
def test_scrum88_scrum89_deciding_an_unknown_event_is_not_found(client, db_session, action):
    s = _setup(client, db_session)
    body = {"reason": "No.", "venue_booking_ids": [s["booking_id"]], "equipment_request_ids": []}

    res = client.post(f"/safety-checks/999999/{action}", json=body, headers=s["officer_h"])

    assert res.status_code == 404


# --- SCRUM-98: Auto-Expire Tentative Holds & Notify Coordinator ---------------


def test_scrum98_ac2_one_failed_pass_does_not_stop_the_sweeper():
    passes = []

    class Flaky(HoldSweeper):
        def run_once(self, now=None):
            passes.append(now)
            if len(passes) == 1:
                raise RuntimeError("database went away")
            return 0, 0

    async def scenario():
        sweeper = asyncio.ensure_future(Flaky(lambda: None, 0).run_forever())
        while len(passes) < 2:
            await asyncio.sleep(0)
        sweeper.cancel()
        with pytest.raises(asyncio.CancelledError):
            await sweeper

    asyncio.run(asyncio.wait_for(scenario(), timeout=5))
    assert len(passes) >= 2


@pytest.mark.usefixtures("coordinator_auto_assign")
def test_scrum98_ac1_a_hold_whose_event_has_no_coordinator_reminds_nobody(client, db_session):
    s = _booking_setup(client, db_session)
    expiry = _hold(client, s, hours=48)
    db_session.get(Event, s["event_id"]).coordinator_id = None
    db_session.commit()
    before = db_session.query(Notification).count()

    _sweep(db_session, expiry - timedelta(hours=24))

    assert db_session.query(Notification).count() == before
    assert _status(db_session, s) == BookingStatus.tentative_hold
    assert _reminders(db_session, s) == []


# --- SCRUM-103: Respond to Clarification Request as Event Organiser -----------


def test_scrum103_ac2_a_reply_on_an_event_with_no_coordinator_notifies_nobody(client, w):  # noqa: F811
    _awaiting(client, w)
    event = _event(w)
    event.coordinator_id = None
    w["db"].commit()

    assert _reply(client, w).status_code == 201

    assert w["db"].query(Notification).filter_by(type=NotificationType.clarification_replied).count() == 0
    assert _event(w).status == EventStatus.under_review


def test_scrum103_ac6_amending_the_equipment_is_saved_and_logged(client, w):  # noqa: F811
    item = Equipment(name="Projector", category="Projection", total_quantity=10)
    w["db"].add(item)
    w["db"].commit()
    _awaiting(client, w)

    res = _reply(
        client,
        w,
        {
            "message": "Added a projector.",
            "updates": {"equipment_items": [{"equipment_id": item.id, "quantity_requested": 2}]},
        },
    )

    assert res.status_code == 201
    [line] = _event(w).equipment_items
    assert line.equipment_id == item.id and line.quantity_requested == 2
    assert "equipment_items updated" in _log(client, w)[0]["note"]


def test_scrum103_ac6_a_reply_that_changes_nothing_logs_only_the_message(client, w):  # noqa: F811
    _awaiting(client, w)
    same = _event(w).expected_attendance

    res = _reply(client, w, {"message": "Nothing to change.", "updates": {"expected_attendance": same}})

    assert res.status_code == 201
    assert _log(client, w)[0]["note"] == "Nothing to change."
