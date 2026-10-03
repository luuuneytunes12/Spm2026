"""Tests for coordinator assignment.

Coordinator assignment (originally written as ACs of an older story, kept
here as numbered):
    AC1 - The Event Organiser can see who their assigned coordinator is on
          their event page.
    AC2 - The assigned coordinator receives a notification of their
          assignment.
    AC3 - The assignment is recorded in the event's activity log with a
          timestamp.

"An available Event Coordinator is automatically assigned when a request
is submitted" is a SEPARATE backlog item ("Get Coordinator Assigned") that
shares this file and its picker (app/services/assignment.py). Those tests
are still here (test_submitting_with_*, test_an_unavailable_coordinator_*,
test_assignment_picks_*) but are not numbered against the ACs above.

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
# AC1 -- automatic assignment on submission
# --------------------------------------------------------------------------


def test_submitting_with_an_available_coordinator_assigns_them(client, db_session):
    """AC1: a submitted request is handed to the one available Coordinator."""
    organiser, organiser_headers = _organiser(client, db_session)
    coordinator, _ = _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")

    event_id = _submit(client, organiser_headers)

    assert db_session.get(Event, event_id).coordinator_id == coordinator.id


def test_submitting_with_no_coordinator_leaves_it_unassigned(client, db_session):
    """AC1's flip side: no available Coordinator means the request still
    goes through, just without one -- it is not blocked or errored."""
    organiser, organiser_headers = _organiser(client, db_session)

    event_id = _submit(client, organiser_headers)

    res = client.get(f"/events/{event_id}", headers=organiser_headers)
    assert res.status_code == 200
    assert res.json()["coordinator_id"] is None


def test_an_unavailable_coordinator_is_never_assigned(client, db_session):
    """"Available" is load-bearing -- a Coordinator who is not available must
    not receive new work."""
    organiser, organiser_headers = _organiser(client, db_session)
    unavailable, unavailable_headers = _coordinator(
        client, db_session, "busy@connectsphere.test", "Busy Coordinator"
    )
    _mark_unavailable(db_session, unavailable)

    event_id = _submit(client, organiser_headers)

    assert db_session.get(Event, event_id).coordinator_id is None


def test_assignment_picks_the_least_loaded_available_coordinator(client, db_session):
    """AC1: distributes fairly rather than always picking the same one."""
    organiser, organiser_headers = _organiser(client, db_session)
    busy, _ = _coordinator(client, db_session, "busy@connectsphere.test", "Busy Coordinator")
    idle, _ = _coordinator(client, db_session, "idle@connectsphere.test", "Idle Coordinator")

    first_id = _submit(client, organiser_headers, name="First event")
    assert db_session.get(Event, first_id).coordinator_id == busy.id

    second_id = _submit(client, organiser_headers, name="Second event")

    assert db_session.get(Event, second_id).coordinator_id == idle.id


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


def test_new_events_skip_the_unavailable_coordinator_but_old_ones_stay(client, db_session):
    organiser, organiser_headers = _organiser(client, db_session)
    holder, holder_headers = _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")
    other, _ = _coordinator(client, db_session, "priya@connectsphere.test", "Priya Nair")
    first_id = _submit(client, organiser_headers, name="Already assigned")
    assert db_session.get(Event, first_id).coordinator_id == holder.id
    _mark_unavailable(db_session, holder)

    second_id = _submit(client, organiser_headers, name="Submitted afterwards")

    assert db_session.get(Event, first_id).coordinator_id == holder.id  # unchanged
    assert db_session.get(Event, second_id).coordinator_id == other.id  # skipped Sam


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
    event = Event(organiser_id=organiser.id, name="Draft", status=EventStatus.submitted)
    db_session.add(event)
    db_session.commit()

    with patch.object(broker, "publish") as publish:
        assign_coordinator(db_session, event, actor_id=organiser.id)
        db_session.rollback()

    publish.assert_not_called()
    assert db_session.query(Notification).count() == 0
