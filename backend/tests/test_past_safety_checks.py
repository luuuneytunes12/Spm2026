"""As a Safety Officer, I want to view the Safety Checks I have already
decided, so that I can check my past decisions and reasons when an Event
comes back to me or is questioned.

Test names carry the acceptance criterion they prove.
"""

from app.core.roles import Role
from app.models.enums import EventStatus
from app.models.events import Event, EventStatusHistory
from tests.event_review_test_helpers import submitted_event, user
from tests.test_safety_check_return import _clear_flags
from tests.test_safety_checks import _post, _setup, _status


def _history(client, headers):
    return client.get("/safety-checks/history", headers=headers)


def _detail(client, s, headers=None):
    return client.get(f"/safety-checks/{s['event_id']}", headers=headers or s["officer_h"])


def _resubmit(client, db_session, s):
    _clear_flags(client, db_session, s)
    assert client.post(f"/events/{s['event_id']}/confirm", headers=s["coord_h"]).status_code == 200


def _second_event_awaiting(client, db_session, s, name="Second Event"):
    """Another of the Organiser's events, put straight into the queue."""
    event_id = submitted_event(client, s["org_h"])
    event = db_session.get(Event, event_id)
    event.name = name
    event.status = EventStatus.awaiting_safety_check
    db_session.commit()
    return event_id


# --- AC1: each decided event with name, date, decision, reason, time; newest first


def test_ac1_lists_each_decided_event_with_name_date_decision_reason_and_time(client, db_session):
    s = _setup(client, db_session)
    _post(client, s, "reject", reason="Exits blocked")

    res = _history(client, s["officer_h"])

    assert res.status_code == 200
    [row] = res.json()
    assert row["id"] == s["event_id"]
    assert row["name"] == "Regional Partner Conference"
    assert row["proposed_start"].startswith("2026-11-02T09:00")
    assert row["decision"] == "Rejected"
    assert row["reason"] == "Exits blocked"
    assert row["decided_at"]
    assert row["status"] == EventStatus.planning_event


def test_ac1_an_approval_is_listed_with_no_reason(client, db_session):
    s = _setup(client, db_session)
    assert _post(client, s, "approve").status_code == 200

    [row] = _history(client, s["officer_h"]).json()

    assert (row["decision"], row["reason"]) == ("Approved", None)
    assert row["status"] == EventStatus.safety_check_passed


def test_ac1_newest_decision_first(client, db_session):
    s = _setup(client, db_session)
    _post(client, s, "reject", reason="First")
    second_id = _second_event_awaiting(client, db_session, s)
    assert client.post(
        f"/safety-checks/{second_id}/reject", json={"reason": "Later"}, headers=s["officer_h"]
    ).status_code == 200

    rows = _history(client, s["officer_h"]).json()

    assert [r["id"] for r in rows] == [second_id, s["event_id"]]
    assert [r["reason"] for r in rows] == ["Later", "First"]


def test_ac1_one_row_per_event_showing_my_latest_decision(client, db_session):
    s = _setup(client, db_session)
    _post(client, s, "reject", reason="First problem")
    _resubmit(client, db_session, s)
    _post(client, s, "request-changes", reason="Move the projector", equipment_request_ids=[s["line_id"]])

    rows = _history(client, s["officer_h"]).json()

    assert len(rows) == 1
    assert (rows[0]["decision"], rows[0]["reason"]) == ("Changes Requested", "Move the projector")


def test_ac1_a_cancelled_event_stays_listed_with_its_status_now(client, db_session):
    s = _setup(client, db_session)
    _post(client, s, "reject", reason="Exits blocked")
    db_session.get(Event, s["event_id"]).status = EventStatus.event_cancelled
    db_session.commit()

    [row] = _history(client, s["officer_h"]).json()

    assert row["status"] == EventStatus.event_cancelled
    assert row["reason"] == "Exits blocked"


def test_ac1_empty_when_i_have_decided_nothing(client, db_session):
    s = _setup(client, db_session)  # an event is waiting, but nobody has decided it

    res = _history(client, s["officer_h"])

    assert res.status_code == 200
    assert res.json() == []


def test_ac1_another_officers_decisions_are_not_in_my_list(client, db_session):
    s = _setup(client, db_session)
    _, other_h = user(client, db_session, Role.SAFETY_OFFICER, "safety2@example.com", "Sasha Second")
    assert client.post(
        f"/safety-checks/{s['event_id']}/reject", json={"reason": "Theirs"}, headers=other_h
    ).status_code == 200

    assert _history(client, s["officer_h"]).json() == []
    assert [r["reason"] for r in _history(client, other_h).json()] == ["Theirs"]


def test_ac1_a_log_row_leaving_the_check_that_is_not_a_decision_is_not_listed(client, db_session):
    s = _setup(client, db_session)
    db_session.add(
        EventStatusHistory(
            event_id=s["event_id"],
            changed_by=s["officer"].id,
            from_status=EventStatus.awaiting_safety_check,
            to_status=EventStatus.event_cancelled,
            note="Cancelled: venue closed",
        )
    )
    db_session.commit()

    assert _history(client, s["officer_h"]).json() == []


# --- AC2: open it read-only, with details and current status ------------------


def test_ac2_a_decided_event_opens_with_its_details_and_current_status(client, db_session):
    s = _setup(client, db_session)
    _post(client, s, "reject", reason="Exits blocked")

    res = _detail(client, s)

    assert res.status_code == 200
    detail = res.json()
    assert detail["status"] == EventStatus.planning_event
    assert detail["name"] == "Regional Partner Conference"
    assert detail["expected_attendance"] == 120


def test_ac2_a_decided_event_cannot_be_decided_again_until_resubmitted(client, db_session):
    s = _setup(client, db_session)
    _post(client, s, "reject", reason="Exits blocked")

    for action, body in [("approve", None), ("reject", {"reason": "Again"})]:
        res = client.post(f"/safety-checks/{s['event_id']}/{action}", json=body, headers=s["officer_h"])
        assert res.status_code == 409
    assert _status(db_session, s) == EventStatus.planning_event
    assert len(_detail(client, s).json()["decisions"]) == 1


# --- AC3: every earlier decision listed with reason, who and time ---------------


def test_ac3_every_decision_by_any_officer_is_listed_newest_first(client, db_session):
    s = _setup(client, db_session)
    _, other_h = user(client, db_session, Role.SAFETY_OFFICER, "safety2@example.com", "Sasha Second")
    _post(client, s, "reject", reason="First problem")
    _resubmit(client, db_session, s)
    assert client.post(
        f"/safety-checks/{s['event_id']}/request-changes",
        json={"reason": "Second problem", "equipment_request_ids": [s["line_id"]]},
        headers=other_h,
    ).status_code == 200

    decisions = _detail(client, s).json()["decisions"]

    assert [(d["decision"], d["reason"], d["decided_by_name"]) for d in decisions] == [
        ("Changes Requested", "Second problem", "Sasha Second"),
        ("Rejected", "First problem", "Sam Safety"),
    ]
    assert all(d["decided_at"] for d in decisions)


def test_ac3_an_event_never_decided_has_no_decisions(client, db_session):
    s = _setup(client, db_session)

    assert _detail(client, s).json()["decisions"] == []


# --- AC4: access denied to anyone without the Safety Officer role --------------


def test_ac4_other_roles_are_refused_the_past_safety_checks(client, db_session):
    s = _setup(client, db_session)
    _post(client, s, "reject", reason="Exits blocked")
    _, lead_h = user(client, db_session, Role.COORDINATOR_LEAD, "lead@example.com", "Lee Lead")

    for headers in (s["org_h"], s["coord_h"], s["tech_h"], lead_h):
        history = _history(client, headers)
        detail = _detail(client, s, headers)
        assert history.status_code == 403
        assert detail.status_code == 403
        assert "Exits blocked" not in history.text + detail.text


def test_ac4_unauthenticated_requests_are_refused(client, db_session):
    s = _setup(client, db_session)
    _post(client, s, "reject", reason="Exits blocked")

    res = client.get("/safety-checks/history")

    assert res.status_code == 401
    assert "Exits blocked" not in res.text


# --- Frozen literals: behaviour this story must not change ---------------------


def test_frozen_queue_rows_keep_their_shape_and_hold_only_awaiting_events(client, db_session):
    s = _setup(client, db_session)
    [row] = client.get("/safety-checks", headers=s["officer_h"]).json()
    assert set(row) == {"id", "name", "proposed_start", "proposed_end", "coordinator"}

    _post(client, s, "reject", reason="Exits blocked")

    assert client.get("/safety-checks", headers=s["officer_h"]).json() == []


def test_frozen_decisions_still_write_the_same_activity_notes(client, db_session):
    s = _setup(client, db_session)
    _post(client, s, "reject", reason="Exits blocked")

    notes = [a["note"] for a in _detail(client, s).json()["activity"]]

    assert "Safety arrangement rejected: Exits blocked" in notes
