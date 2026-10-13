"""As an Event Coordinator, I want to see why the Safety Officer sent my Event
back and what must be reviewed again, so that I can fix the arrangements and
resubmit it.

Test names carry the acceptance criterion they prove.
"""

import pytest

from app.core.roles import Role
from app.models.enums import EventStatus
from app.models.events import EventStatusHistory
from tests.event_review_test_helpers import user
from tests.test_safety_checks import _post, _setup, _status


def _detail(client, s):
    return client.get(f"/events/assigned/{s['event_id']}", headers=s["coord_h"]).json()


def _clear_flags(client, db_session, s):
    """Venue Staff and Technical Support approve / reserve again."""
    client.post(f"/equipment-reservations/{s['line_id']}/safety-recheck/confirm", json={}, headers=s["tech_h"])
    if "staff2_h" not in s:
        _, s["staff2_h"] = user(client, db_session, Role.VENUE_STAFF, "staff2@example.com", "Second Staff")
    staff_h = s["staff2_h"]
    for booking_id in (s["booking_id"], s["second_booking_id"]):
        client.post(f"/venue-bookings/{booking_id}/approve", headers=staff_h)


def test_ac1_changes_requested_shows_result_reason_and_only_the_marked_items(client, db_session):
    s = _setup(client, db_session)
    _post(client, s, "request-changes", reason="Move the projector", equipment_request_ids=[s["line_id"]])

    result = _detail(client, s)["safety_check_return"]

    assert result["result"] == "Changes Requested"
    assert result["reason"] == "Move the projector"
    assert result["decided_by_name"] == "Sam Safety"
    assert result["items_to_review"] == ["Equipment: Projector (x2)"]


def test_ac1_rejected_shows_result_reason_and_every_arrangement(client, db_session):
    s = _setup(client, db_session)
    _post(client, s, "reject", reason="Exits blocked")

    result = _detail(client, s)["safety_check_return"]

    assert result["result"] == "Rejected"
    assert result["reason"] == "Exits blocked"
    assert result["items_to_review"] == [
        "Venue booking: Marina Hall",
        "Venue booking: Garden Pavilion",
        "Equipment: Projector (x2)",
    ]


def test_ac1_nothing_is_shown_for_an_event_never_sent_back(client, db_session):
    s = _setup(client, db_session)

    assert _detail(client, s)["safety_check_return"] is None


def test_ac1_another_coordinator_cannot_see_the_result(client, db_session):
    s = _setup(client, db_session)
    _post(client, s, "reject", reason="Exits blocked")
    _, other_h = user(client, db_session, Role.COORDINATOR, "other-coord@example.com", "Other")

    res = client.get(f"/events/assigned/{s['event_id']}", headers=other_h)

    assert res.status_code == 404
    assert "Exits blocked" not in res.text


@pytest.mark.parametrize("decision", ["request-changes", "reject"])
def test_ac2_resubmitting_after_rearranging_makes_it_awaiting_safety_check(client, db_session, decision):
    s = _setup(client, db_session)
    _post(client, s, decision, reason="Fix it", equipment_request_ids=[s["line_id"]])
    _clear_flags(client, db_session, s)

    res = client.post(f"/events/{s['event_id']}/confirm", headers=s["coord_h"])

    assert res.status_code == 200
    assert _status(db_session, s) == EventStatus.awaiting_safety_check
    assert _detail(client, s)["safety_check_return"] is None


def test_ac2_resubmitting_while_items_are_still_flagged_is_blocked(client, db_session):
    s = _setup(client, db_session)
    _post(client, s, "request-changes", reason="Move it", equipment_request_ids=[s["line_id"]])

    res = client.post(f"/events/{s['event_id']}/confirm", headers=s["coord_h"])

    assert res.status_code == 409
    assert _status(db_session, s) == EventStatus.planning_event


def test_ac3_each_earlier_decision_stays_in_the_activity_log(client, db_session):
    s = _setup(client, db_session)
    _post(client, s, "reject", reason="First problem")
    _clear_flags(client, db_session, s)
    assert client.post(f"/events/{s['event_id']}/confirm", headers=s["coord_h"]).status_code == 200
    _post(client, s, "request-changes", reason="Second problem", equipment_request_ids=[s["line_id"]])
    _clear_flags(client, db_session, s)

    res = client.post(f"/events/{s['event_id']}/confirm", headers=s["coord_h"])

    assert res.status_code == 200
    notes = [a["note"] for a in _detail(client, s)["activity"]]
    assert "Safety arrangement rejected: First problem" in notes
    assert "Safety changes requested: Second problem" in notes
    assert notes.count("Submitted for safety check by the Event Coordinator.") == 3
    assert db_session.query(EventStatusHistory).filter_by(event_id=s["event_id"]).count() >= 6
