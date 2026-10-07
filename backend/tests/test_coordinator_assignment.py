"""Tests for coordinator assignment.

Coordinator assignment (originally written as ACs of an older story, kept
here as numbered):
    AC1 - The Event Organiser can see who their assigned coordinator is on
          their event page.
    AC2 - The assigned coordinator receives a notification of their
          assignment.
    AC3 - The assignment is recorded in the event's activity log with a
          timestamp.

The app does not auto-assign: the Event Coordinator Lead assigns manually
(see test_lead_assign_event.py). The `coordinator_auto_assign` fixture only
gives these tests an already-assigned event to start from.

There is no longer a way for a Coordinator to mark themselves unavailable.
`users.is_available` still exists and the assignment pool still honours it,
so these tests set it directly on the row where they need an unavailable
Coordinator.

Each test name states the acceptance criterion it covers, in the same style
as test_assigned_events.py.
"""

from unittest.mock import patch

from app.core.roles import Role
from app.models.enums import EventStatus
from app.models.events import Event
from app.models.notifications import Notification
from app.models.user import User
from app.services.assignment import assign_coordinator
from app.services.notifications import broker
import pytest

# These tests start from an event that already has a Coordinator; assignment is
# now the Lead's job, so submit alone no longer provides one (see conftest).
pytestmark = pytest.mark.usefixtures("coordinator_auto_assign")

COMPLETE = {
    "name": "Regional Partner Conference",
    "purpose": "Annual partner briefing",
    "event_type": "conference",
    "proposed_start": "2026-11-02T09:00:00Z",
    "proposed_end": "2026-11-02T17:00:00Z",
    "expected_attendance": 120,
    "venue_requirements": "Main hall, stage, podium",
    "accessibility_needs": "Step-free access, hearing loop",
    "equipment_requirements": "2 projectors, 4 radio mics",
}


def _user(client, db_session, role, email, name="Test User"):
    """Register a user, promote them to `role`, and return (user, headers).

    Mirrors the identical helper in test_assigned_events.py.
    """
    password = "password123"
    res = client.post(
        "/auth/register", json={"name": name, "email": email, "password": password}
    )
    assert res.status_code == 201

    user = db_session.query(User).filter(User.email == email).one()
    user.role = role.value
    db_session.commit()

    token = client.post("/auth/login", json={"email": email, "password": password}).json()[
        "access_token"
    ]
    return user, {"Authorization": f"Bearer {token}"}


def _mark_unavailable(db_session, coordinator):
    """Take `coordinator` out of the assignment pool, directly on their row."""
    coordinator.is_available = False
    db_session.commit()


def _organiser(client, db_session, email="org@connectsphere.test"):
    return _user(client, db_session, Role.ORGANISER, email, name="Priya Menon")


def _coordinator(client, db_session, email, name):
    return _user(client, db_session, Role.COORDINATOR, email, name=name)


def _submit(client, organiser_headers, **overrides) -> int:
    event_id = client.post(
        "/events", json={**COMPLETE, **overrides}, headers=organiser_headers
    ).json()["id"]
    assert client.post(f"/events/{event_id}/submit", headers=organiser_headers).status_code == 200
    return event_id


# --------------------------------------------------------------------------
# AC2 -- the Organiser can see who is assigned
# --------------------------------------------------------------------------


def test_organiser_sees_the_assigned_coordinators_name_and_email(client, db_session):
    """AC2: GET /events/{id} -- the Organiser's own event page -- names the
    Coordinator and how to reach them, once one has been assigned."""
    organiser, organiser_headers = _organiser(client, db_session)
    coordinator, _ = _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")

    event_id = _submit(client, organiser_headers)

    body = client.get(f"/events/{event_id}", headers=organiser_headers).json()
    assert body["coordinator"] == {
        "id": coordinator.id,
        "name": "Sam Tan",
        "email": "sam@connectsphere.test",
    }


def test_organiser_sees_no_coordinator_before_one_is_assigned(client, db_session):
    """AC2's honest empty state: nothing assigned yet reads as null, not a
    missing field or an error."""
    organiser, organiser_headers = _organiser(client, db_session)

    event_id = _submit(client, organiser_headers)

    body = client.get(f"/events/{event_id}", headers=organiser_headers).json()
    assert body["coordinator_id"] is None
    assert body["coordinator"] is None


# --------------------------------------------------------------------------
# AC3 -- the assigned coordinator is notified
# --------------------------------------------------------------------------


def test_assigned_coordinator_receives_a_notification(client, db_session):
    """AC3: assignment creates a notification for the new Coordinator."""
    organiser, organiser_headers = _organiser(client, db_session)
    coordinator, coordinator_headers = _coordinator(
        client, db_session, "sam@connectsphere.test", "Sam Tan"
    )

    event_id = _submit(client, organiser_headers)

    notifications = client.get("/notifications", headers=coordinator_headers).json()
    assert len(notifications) == 1
    assert notifications[0]["event_id"] == event_id
    assert notifications[0]["type"] == "event_assigned"
    assert "Regional Partner Conference" in notifications[0]["message"]


def test_notification_is_scoped_to_the_assigned_coordinator(client, db_session):
    """A Coordinator never sees another's assignment notifications."""
    organiser, organiser_headers = _organiser(client, db_session)
    _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")
    _other, other_headers = _coordinator(client, db_session, "other@connectsphere.test", "Other One")

    _submit(client, organiser_headers)

    assert client.get("/notifications", headers=other_headers).json() == []


# --------------------------------------------------------------------------
# AC4 -- the assignment is in the activity log, with a timestamp
# --------------------------------------------------------------------------


def test_assignment_is_recorded_in_the_activity_log(client, db_session):
    """AC4: the assigned Coordinator can see, on the assigned-event detail
    page, that they were assigned and when."""
    organiser, organiser_headers = _organiser(client, db_session)
    coordinator, coordinator_headers = _coordinator(
        client, db_session, "sam@connectsphere.test", "Sam Tan"
    )

    event_id = _submit(client, organiser_headers)

    body = client.get(f"/events/assigned/{event_id}", headers=coordinator_headers).json()
    assignment_entries = [e for e in body["activity"] if "Assigned to Sam Tan" in (e["note"] or "")]
    assert len(assignment_entries) == 1
    entry = assignment_entries[0]
    assert entry["created_at"] is not None
    assert entry["changed_by_name"] == organiser.name


# --------------------------------------------------------------------------
# An unavailable Coordinator keeps what they hold; new events skip them
# --------------------------------------------------------------------------


def test_an_unavailable_coordinator_can_still_work_the_events_they_hold(client, db_session):
    organiser, organiser_headers = _organiser(client, db_session)
    holder, holder_headers = _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")
    event_id = _submit(client, organiser_headers)
    _mark_unavailable(db_session, holder)

    assert client.get(f"/events/assigned/{event_id}", headers=holder_headers).status_code == 200
    assert client.post(f"/events/{event_id}/approve", headers=holder_headers).status_code == 200


def test_anonymous_cannot_list_notifications(client):
    assert client.get("/notifications").status_code == 401


# --------------------------------------------------------------------------
# Live push -- notifications go out through notify(), only after the commit
# --------------------------------------------------------------------------


def _pushed(publish) -> list[tuple[int, dict]]:
    """(user_id, payload) for every call made to the patched broker.publish."""
    return [c.args for c in publish.call_args_list]


def test_assignment_is_pushed_live_to_the_assigned_coordinator(client, db_session):
    """AC2, live: the Coordinator's open streams get the notification, with
    the same id GET /notifications will later return for it."""
    organiser, organiser_headers = _organiser(client, db_session)
    coordinator, coordinator_headers = _coordinator(
        client, db_session, "sam@connectsphere.test", "Sam Tan"
    )

    with patch.object(broker, "publish") as publish:
        event_id = _submit(client, organiser_headers)

    # Role-specific: the Coordinator hears they were assigned, the Organiser
    # hears who their Coordinator is -- each with their own notification.
    pushed = _pushed(publish)
    assert {(user_id, payload["type"]) for user_id, payload in pushed} == {
        (coordinator.id, "event_assigned"),
        (organiser.id, "event_coordinator_assigned"),
    }
    payload = next(p for user_id, p in pushed if user_id == coordinator.id)
    assert payload["event_id"] == event_id
    stored = client.get("/notifications", headers=coordinator_headers).json()
    assert payload["id"] == stored[0]["id"]


def test_rolled_back_assignment_pushes_nothing(client, db_session):
    """A transaction that never commits must never notify anyone -- and
    leaves no notification row behind either."""
    organiser, _ = _organiser(client, db_session)
    _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")
    event = Event(organiser_id=organiser.id, name="Draft", status=EventStatus.submitted_awaiting_coordinator)
    db_session.add(event)
    db_session.commit()

    with patch.object(broker, "publish") as publish:
        assign_coordinator(db_session, event, actor_id=organiser.id)
        db_session.rollback()

    publish.assert_not_called()
    assert db_session.query(Notification).count() == 0
