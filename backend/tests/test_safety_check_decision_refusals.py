"""Unit tests for the Safety Officer's decisions being refused.

SCRUM-88  Approve Event in Operational Safety Check

    As a Safety Officer, I want to approve an Event that passes the Operational
    Safety Check, so that it can proceed to preparation.

    AC4  an Event that is not 'Awaiting Safety Check' cannot be approved

SCRUM-89  Reject or Request Changes in Operational Safety Check

    As a Safety Officer, I want to reject an Event's safety arrangement or
    request changes, so that unsafe arrangements are fixed before the Event
    proceeds to preparation.

    AC2  requesting changes marks the affected Venue Bookings or Equipment
    AC6  an Event that is not 'Awaiting Safety Check' cannot be decided

The main paths are tests/test_safety_checks.py; these are the refusals it
leaves unexecuted.
"""

import pytest

from app.models.enums import BookingStatus, EquipmentStatus, EventStatus
from app.models.equipment import EquipmentRequest
from app.models.events import Event
from app.models.venues import VenueBooking
from tests.test_safety_checks import _post, _setup


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
def test_scrum88_ac4_scrum89_ac6_deciding_an_unknown_event_is_not_found(client, db_session, action):
    s = _setup(client, db_session)
    body = {"reason": "No.", "venue_booking_ids": [s["booking_id"]], "equipment_request_ids": []}

    res = client.post(f"/safety-checks/999999/{action}", json=body, headers=s["officer_h"])

    assert res.status_code == 404
