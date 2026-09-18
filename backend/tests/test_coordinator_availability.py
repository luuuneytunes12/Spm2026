"""Tests for the "Mark myself unavailable" story (Event Coordinator).

    As an Event Coordinator, I want to mark myself as unavailable, so that
    my assigned events are automatically reassigned to another coordinator.

Acceptance criteria:
    AC1 - The Event Organiser can see who their assigned coordinator is on
          their event page.
    AC2 - The assigned coordinator receives a notification of their
          assignment.
    AC3 - The assignment is recorded in the event's activity log with a
          timestamp.

"An available Event Coordinator is automatically assigned when a request
is submitted" is a SEPARATE backlog item ("Get Coordinator Assigned") that
happens to share this file and its picker (app/services/assignment.py) --
see docs/test-cases-coordinator-availability.md's scope note. Those tests
are still here (test_submitting_with_*, test_unavailable_coordinator_*,
test_assignment_picks_*) but are not numbered against the ACs above.

Unavailability comes in two forms, both covered here: the global toggle
(PATCH /coordinators/me/availability -- takes the caller out of the pool
entirely and moves every active event they hold) and per-event release
(POST /events/assigned/{id}/release -- hands off just the one event,
leaving the caller's other work and general eligibility untouched).

Each test name states the acceptance criterion it covers, in the same style
as test_assigned_events.py.
"""

from app.core.roles import Role
from app.models.events import Event
from app.models.notifications import Notification
from app.models.user import User

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


def test_unavailable_coordinator_is_never_assigned(client, db_session):
    """AC1: "available" is load-bearing -- a Coordinator who has marked
    themselves unavailable must not receive new work either."""
    organiser, organiser_headers = _organiser(client, db_session)
    unavailable, unavailable_headers = _coordinator(
        client, db_session, "busy@connectsphere.test", "Busy Coordinator"
    )
    client.patch(
        "/coordinators/me/availability", json={"is_available": False}, headers=unavailable_headers
    )

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
# Marking unavailable reassigns active events
# --------------------------------------------------------------------------


def test_marking_unavailable_reassigns_active_events_to_another_coordinator(client, db_session):
    organiser, organiser_headers = _organiser(client, db_session)
    outgoing, outgoing_headers = _coordinator(
        client, db_session, "sam@connectsphere.test", "Sam Tan"
    )
    replacement, replacement_headers = _coordinator(
        client, db_session, "priya@connectsphere.test", "Priya Nair"
    )

    event_id = _submit(client, organiser_headers)
    assert db_session.get(Event, event_id).coordinator_id == outgoing.id

    res = client.patch(
        "/coordinators/me/availability", json={"is_available": False}, headers=outgoing_headers
    )

    assert res.status_code == 200
    assert res.json()["is_available"] is False
    assert db_session.get(Event, event_id).coordinator_id == replacement.id

    # The replacement is notified, same as an initial assignment.
    notifications = client.get("/notifications", headers=replacement_headers).json()
    assert any(n["event_id"] == event_id for n in notifications)

    # And it shows up in their own assigned-events list.
    assigned = client.get("/events/assigned", headers=replacement_headers).json()
    assert [e["id"] for e in assigned] == [event_id]


def test_outgoing_coordinator_is_notified_who_took_over(client, db_session):
    """The Coordinator who went unavailable can still see, in their own
    Notifications, who ended up with the event that used to be theirs --
    not just silently lose it off their list."""
    organiser, organiser_headers = _organiser(client, db_session)
    outgoing, outgoing_headers = _coordinator(
        client, db_session, "sam@connectsphere.test", "Sam Tan"
    )
    _replacement, _ = _coordinator(client, db_session, "priya@connectsphere.test", "Priya Nair")
    event_id = _submit(client, organiser_headers)

    client.patch("/coordinators/me/availability", json={"is_available": False}, headers=outgoing_headers)

    notifications = client.get("/notifications", headers=outgoing_headers).json()
    reassigned_away = [n for n in notifications if n["type"] == "event_reassigned_away"]
    assert len(reassigned_away) == 1
    assert reassigned_away[0]["event_id"] == event_id
    assert "Priya Nair" in reassigned_away[0]["message"]


def test_no_reassigned_away_notification_when_nobody_replaces_them(client, db_session):
    """Nothing to report -- the event was simply unassigned, not handed to
    anyone, so there is no "who took over" to notify about."""
    organiser, organiser_headers = _organiser(client, db_session)
    outgoing, outgoing_headers = _coordinator(
        client, db_session, "sam@connectsphere.test", "Sam Tan"
    )
    _submit(client, organiser_headers)

    client.patch("/coordinators/me/availability", json={"is_available": False}, headers=outgoing_headers)

    notifications = client.get("/notifications", headers=outgoing_headers).json()
    assert [n for n in notifications if n["type"] == "event_reassigned_away"] == []


def test_reassignment_is_recorded_in_the_activity_log(client, db_session):
    organiser, organiser_headers = _organiser(client, db_session)
    outgoing, outgoing_headers = _coordinator(
        client, db_session, "sam@connectsphere.test", "Sam Tan"
    )
    _replacement, replacement_headers = _coordinator(
        client, db_session, "priya@connectsphere.test", "Priya Nair"
    )
    event_id = _submit(client, organiser_headers)

    client.patch("/coordinators/me/availability", json={"is_available": False}, headers=outgoing_headers)

    body = client.get(f"/events/assigned/{event_id}", headers=replacement_headers).json()
    reassignment_entries = [e for e in body["activity"] if "Reassigned from Sam Tan" in (e["note"] or "")]
    assert len(reassignment_entries) == 1
    assert reassignment_entries[0]["changed_by_name"] == "Sam Tan"


def test_marking_unavailable_with_no_replacement_leaves_event_unassigned(client, db_session):
    """No other Coordinator exists -- the event is left unassigned rather
    than the availability toggle failing."""
    organiser, organiser_headers = _organiser(client, db_session)
    outgoing, outgoing_headers = _coordinator(
        client, db_session, "sam@connectsphere.test", "Sam Tan"
    )
    event_id = _submit(client, organiser_headers)

    res = client.patch(
        "/coordinators/me/availability", json={"is_available": False}, headers=outgoing_headers
    )

    assert res.status_code == 200
    assert db_session.get(Event, event_id).coordinator_id is None


def test_marking_unavailable_does_not_touch_completed_events(client, db_session):
    """Only events still active need a working Coordinator -- one that has
    already finished (however it finished) stays exactly as it is."""
    organiser, organiser_headers = _organiser(client, db_session)
    outgoing, outgoing_headers = _coordinator(
        client, db_session, "sam@connectsphere.test", "Sam Tan"
    )
    _coordinator(client, db_session, "priya@connectsphere.test", "Priya Nair")
    event_id = _submit(client, organiser_headers)
    event = db_session.get(Event, event_id)
    event.status = "completed"
    db_session.commit()

    client.patch("/coordinators/me/availability", json={"is_available": False}, headers=outgoing_headers)

    assert db_session.get(Event, event_id).coordinator_id == outgoing.id


def test_toggling_to_the_same_value_is_a_no_op(client, db_session):
    """No spurious reassignment or activity entry when nothing changes."""
    organiser, organiser_headers = _organiser(client, db_session)
    coordinator, coordinator_headers = _coordinator(
        client, db_session, "sam@connectsphere.test", "Sam Tan"
    )
    event_id = _submit(client, organiser_headers)

    res = client.patch(
        "/coordinators/me/availability", json={"is_available": True}, headers=coordinator_headers
    )

    assert res.status_code == 200
    assert db_session.get(Event, event_id).coordinator_id == coordinator.id
    body = client.get(f"/events/assigned/{event_id}", headers=coordinator_headers).json()
    # Just the two entries submission itself produced (submitted, assigned)
    # -- no third "reassigned" entry from a no-op toggle.
    assert len(body["activity"]) == 2


def test_availability_can_be_turned_back_on(client, db_session):
    organiser, organiser_headers = _organiser(client, db_session)
    coordinator, coordinator_headers = _coordinator(
        client, db_session, "sam@connectsphere.test", "Sam Tan"
    )
    client.patch("/coordinators/me/availability", json={"is_available": False}, headers=coordinator_headers)

    res = client.patch(
        "/coordinators/me/availability", json={"is_available": True}, headers=coordinator_headers
    )

    assert res.status_code == 200
    assert res.json()["is_available"] is True

    # Back in the running for new work.
    event_id = _submit(client, organiser_headers)
    assert db_session.get(Event, event_id).coordinator_id == coordinator.id


def test_only_a_coordinator_can_set_their_own_availability(client, db_session):
    """require_role(COORDINATOR): an Organiser holds no such toggle."""
    _, organiser_headers = _organiser(client, db_session)

    res = client.patch(
        "/coordinators/me/availability", json={"is_available": False}, headers=organiser_headers
    )

    assert res.status_code == 403


def test_anonymous_cannot_set_availability(client):
    assert client.patch("/coordinators/me/availability", json={"is_available": False}).status_code == 401


def test_anonymous_cannot_list_notifications(client):
    assert client.get("/notifications").status_code == 401


# --------------------------------------------------------------------------
# Per-event release -- POST /events/assigned/{id}/release
# --------------------------------------------------------------------------


def test_releasing_one_event_reassigns_only_that_one(client, db_session):
    """The other form of "unavailable": narrower than the global toggle --
    everything else on the Coordinator's plate, and their general
    eligibility for new work, is untouched."""
    organiser, organiser_headers = _organiser(client, db_session)
    outgoing, outgoing_headers = _coordinator(
        client, db_session, "sam@connectsphere.test", "Sam Tan"
    )
    # Only one Coordinator exists yet, so both land on `outgoing` -- adding
    # `replacement` only now means it cannot steal either one at submit time.
    keep_id = _submit(client, organiser_headers, name="Keep this one")
    release_id = _submit(client, organiser_headers, name="Release this one")
    assert db_session.get(Event, keep_id).coordinator_id == outgoing.id
    assert db_session.get(Event, release_id).coordinator_id == outgoing.id

    replacement, _ = _coordinator(client, db_session, "priya@connectsphere.test", "Priya Nair")

    res = client.post(f"/events/assigned/{release_id}/release", headers=outgoing_headers)

    assert res.status_code == 200
    assert res.json()["coordinator_id"] == replacement.id
    # Untouched: still Sam's.
    assert db_session.get(Event, keep_id).coordinator_id == outgoing.id
    # Sam did not go globally unavailable.
    assert db_session.get(User, outgoing.id).is_available is True


def test_releasing_reassigns_the_least_loaded_available_coordinator(client, db_session):
    organiser, organiser_headers = _organiser(client, db_session)
    outgoing, outgoing_headers = _coordinator(
        client, db_session, "sam@connectsphere.test", "Sam Tan"
    )
    idle, _ = _coordinator(client, db_session, "idle@connectsphere.test", "Idle Coordinator")
    event_id = _submit(client, organiser_headers)

    res = client.post(f"/events/assigned/{event_id}/release", headers=outgoing_headers)

    assert res.status_code == 200
    assert res.json()["coordinator_id"] == idle.id


def test_releasing_with_no_replacement_leaves_it_unassigned(client, db_session):
    organiser, organiser_headers = _organiser(client, db_session)
    outgoing, outgoing_headers = _coordinator(
        client, db_session, "sam@connectsphere.test", "Sam Tan"
    )
    event_id = _submit(client, organiser_headers)

    res = client.post(f"/events/assigned/{event_id}/release", headers=outgoing_headers)

    assert res.status_code == 200
    assert res.json()["coordinator_id"] is None


def test_releasing_is_recorded_in_the_activity_log_and_notifies_both_sides(client, db_session):
    """AC2/AC3, via the per-event trigger instead of the global one."""
    organiser, organiser_headers = _organiser(client, db_session)
    outgoing, outgoing_headers = _coordinator(
        client, db_session, "sam@connectsphere.test", "Sam Tan"
    )
    _replacement, replacement_headers = _coordinator(
        client, db_session, "priya@connectsphere.test", "Priya Nair"
    )
    event_id = _submit(client, organiser_headers)

    client.post(f"/events/assigned/{event_id}/release", headers=outgoing_headers)

    body = client.get(f"/events/assigned/{event_id}", headers=replacement_headers).json()
    entries = [e for e in body["activity"] if "Reassigned from Sam Tan" in (e["note"] or "")]
    assert len(entries) == 1
    assert entries[0]["created_at"] is not None

    replacement_notifications = client.get("/notifications", headers=replacement_headers).json()
    assert any(n["event_id"] == event_id for n in replacement_notifications)

    outgoing_notifications = client.get("/notifications", headers=outgoing_headers).json()
    reassigned_away = [n for n in outgoing_notifications if n["type"] == "event_reassigned_away"]
    assert len(reassigned_away) == 1
    assert "Priya Nair" in reassigned_away[0]["message"]


def test_cannot_release_an_event_not_assigned_to_you(client, db_session):
    """Same 404-not-403 rule as every other assigned-event endpoint."""
    organiser, organiser_headers = _organiser(client, db_session)
    _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")
    _other, other_headers = _coordinator(client, db_session, "other@connectsphere.test", "Other One")
    event_id = _submit(client, organiser_headers)

    res = client.post(f"/events/assigned/{event_id}/release", headers=other_headers)

    assert res.status_code == 404


def test_cannot_release_an_unassigned_event(client, db_session):
    organiser, organiser_headers = _organiser(client, db_session)
    event_id = _submit(client, organiser_headers)  # no coordinator exists yet -> unassigned
    _, coordinator_headers = _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")

    res = client.post(f"/events/assigned/{event_id}/release", headers=coordinator_headers)

    assert res.status_code == 404


def test_cannot_release_a_finished_event(client, db_session):
    organiser, organiser_headers = _organiser(client, db_session)
    outgoing, outgoing_headers = _coordinator(
        client, db_session, "sam@connectsphere.test", "Sam Tan"
    )
    event_id = _submit(client, organiser_headers)
    event = db_session.get(Event, event_id)
    event.status = "completed"
    db_session.commit()

    res = client.post(f"/events/assigned/{event_id}/release", headers=outgoing_headers)

    assert res.status_code == 409
    assert db_session.get(Event, event_id).coordinator_id == outgoing.id


def test_anonymous_cannot_release_an_event(client):
    assert client.post("/events/assigned/1/release").status_code == 401
