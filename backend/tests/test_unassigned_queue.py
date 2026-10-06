"""Backend tests for "View Unassigned Event Request Queue as Coordinator Lead".

  AC1 - a submitted request enters the queue as 'submitted' with no
        Coordinator (submit no longer auto-assigns)
  AC2 - a draft is not listed
  AC3 - each queued request shows name, type, date/time, expected attendance,
        Organiser and submitted time, oldest first
  AC4 - opening one shows everything the Organiser entered, read-only
  AC5 - anyone without the Lead role is denied (list and direct request)

These tests deliberately do NOT use the `coordinator_auto_assign` fixture.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.roles import Role
from app.models.enums import EventStatus
from app.models.events import Event, EventStatusHistory
from app.models.notifications import Notification
from event_review_test_helpers import user

FULL = {
    "name": "Regional Partner Conference",
    "purpose": "Annual partner briefing",
    "description": "A full-day briefing for our regional partners.",
    "event_type": "conference",
    "proposed_start": "2026-11-02T09:00:00Z",
    "proposed_end": "2026-11-02T17:00:00Z",
    "expected_attendance": 120,
    "venue_requirements": "Main hall, stage, podium",
    "accessibility_needs": "Step-free access, hearing loop",
    "equipment_requirements": "2 projectors, 4 radio mics",
    "registration_enabled": True,
}
QUEUE = "/lead/unassigned-queue"


@pytest.fixture()
def world(client, db_session):
    _, org_auth = user(client, db_session, Role.ORGANISER, "org@cs.local", "Olivia Organiser")
    coordinator, coord_auth = user(client, db_session, Role.COORDINATOR, "coord@cs.local", "Sam Tan")
    _, lead_auth = user(client, db_session, Role.COORDINATOR_LEAD, "lead@cs.local", "Lena Lead")
    return {"org": org_auth, "coord": coord_auth, "coordinator": coordinator, "lead": lead_auth}


def _draft(client, headers, **over) -> int:
    return client.post("/events", json={**FULL, **over}, headers=headers).json()["id"]


def _submit(client, headers, **over) -> int:
    event_id = _draft(client, headers, **over)
    assert client.post(f"/events/{event_id}/submit", headers=headers).status_code == 200
    return event_id


# --- AC1 -------------------------------------------------------------------


def test_ac1_submitted_request_enters_the_queue_as_submitted_with_no_coordinator(client, db_session, world):
    event_id = _submit(client, world["org"])

    body = client.get(QUEUE, headers=world["lead"]).json()
    assert [e["id"] for e in body] == [event_id]
    assert body[0]["status"] == "submitted"
    assert body[0]["coordinator"] is None
    assert db_session.get(Event, event_id).coordinator_id is None


def test_ac1_submit_does_not_assign_even_when_a_coordinator_is_available(client, db_session, world):
    assert world["coordinator"].is_available is True
    event_id = _submit(client, world["org"])
    event = db_session.get(Event, event_id)
    assert (event.coordinator_id, event.status) == (None, EventStatus.submitted)
    # nobody was told they were assigned, and the log holds only the submission
    assert db_session.query(Notification).filter(Notification.user_id == world["coordinator"].id).count() == 0
    log = db_session.query(EventStatusHistory).filter(EventStatusHistory.event_id == event_id).all()
    assert [h.to_status for h in log] == ["submitted"]


def test_ac1_an_assigned_request_leaves_the_queue(client, db_session, world):
    event_id = _submit(client, world["org"])
    event = db_session.get(Event, event_id)
    event.coordinator_id = world["coordinator"].id
    event.status = EventStatus.under_review
    db_session.commit()
    assert client.get(QUEUE, headers=world["lead"]).json() == []


# --- AC2 -------------------------------------------------------------------


def test_ac2_a_draft_is_not_listed(client, world):
    _draft(client, world["org"], name="Still a draft")
    assert client.get(QUEUE, headers=world["lead"]).json() == []


def test_ac2_a_draft_cannot_be_opened_through_the_queue(client, world):
    draft_id = _draft(client, world["org"])
    assert client.get(f"{QUEUE}/{draft_id}", headers=world["lead"]).status_code == 404


# --- AC3 -------------------------------------------------------------------


def test_ac3_each_row_carries_the_review_fields(client, world):
    _submit(client, world["org"])
    row = client.get(QUEUE, headers=world["lead"]).json()[0]
    assert row["name"] == "Regional Partner Conference"
    assert row["event_type"] == "conference"
    assert row["proposed_start"].startswith("2026-11-02T09:00")
    assert row["proposed_end"].startswith("2026-11-02T17:00")
    assert row["expected_attendance"] == 120
    assert row["organiser"]["name"] == "Olivia Organiser"
    assert row["submitted_at"] is not None


def test_ac3_oldest_submission_comes_first(client, db_session, world):
    now = datetime.now(timezone.utc)
    newest = _submit(client, world["org"], name="Newest")
    oldest = _submit(client, world["org"], name="Oldest")
    middle = _submit(client, world["org"], name="Middle")
    for event_id, age in ((oldest, 3), (middle, 2), (newest, 1)):
        db_session.get(Event, event_id).submitted_at = now - timedelta(hours=age)
    db_session.commit()
    assert [e["name"] for e in client.get(QUEUE, headers=world["lead"]).json()] == ["Oldest", "Middle", "Newest"]


# --- AC4 -------------------------------------------------------------------


def test_ac4_opening_a_request_shows_everything_the_organiser_entered(client, world):
    event_id = _submit(client, world["org"])
    body = client.get(f"{QUEUE}/{event_id}", headers=world["lead"]).json()
    for field, expected in {
        "name": FULL["name"],
        "purpose": FULL["purpose"],
        "description": FULL["description"],
        "event_type": FULL["event_type"],
        "expected_attendance": FULL["expected_attendance"],
        "venue_requirements": FULL["venue_requirements"],
        "accessibility_needs": FULL["accessibility_needs"],
        "equipment_requirements": FULL["equipment_requirements"],
        "registration_enabled": True,
    }.items():
        assert body[field] == expected, field
    assert body["proposed_start"].startswith("2026-11-02T09:00")
    assert body["proposed_end"].startswith("2026-11-02T17:00")
    assert body["organiser"]["name"] == "Olivia Organiser"


@pytest.mark.parametrize("method", ["put", "patch", "post", "delete"])
def test_ac4_the_queue_is_read_only(client, db_session, world, method):
    event_id = _submit(client, world["org"])
    res = client.request(method.upper(), f"{QUEUE}/{event_id}", headers=world["lead"], json={"name": "Hacked"})
    assert res.status_code == 405
    assert db_session.get(Event, event_id).name == FULL["name"]


def test_ac4_an_unknown_request_is_a_404(client, world):
    assert client.get(f"{QUEUE}/99999", headers=world["lead"]).status_code == 404


# --- AC5 -------------------------------------------------------------------


@pytest.mark.parametrize(
    "role", [Role.ORGANISER, Role.COORDINATOR, Role.VENUE_STAFF, Role.TECH_SUPPORT, Role.ATTENDEE]
)
def test_ac5_other_roles_are_denied_and_see_no_requests(client, db_session, world, role):
    event_id = _submit(client, world["org"])
    _, auth = user(client, db_session, role, f"x_{role.value}@cs.local", "Someone Else")
    for path in (QUEUE, f"{QUEUE}/{event_id}"):
        res = client.get(path, headers=auth)
        assert res.status_code == 403
        assert "Regional Partner Conference" not in res.text


@pytest.mark.parametrize("path", [QUEUE, f"{QUEUE}/1"])
def test_ac5_unauthenticated_is_rejected(client, path):
    assert client.get(path).status_code == 401
