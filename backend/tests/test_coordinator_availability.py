"""Tests for the coordinator assignment and availability stories.

Global unavailability (SCRUM-24):

    As an Event Coordinator, I want to mark myself as unavailable, so that
    I stop receiving new ones until I'm available again.

    - Marking "Unavailable" shows "Unavailable" on my profile until I mark
      myself "Available" again.
    - While unavailable I am excluded from the pool of assignable
      Coordinators; once available again I am included.
    - Each change is recorded with a timestamp, even with no active events.
    - It does NOT move events I already hold: it only stops NEW ones.

Coordinator assignment (originally written as ACs of the older "Mark
myself unavailable" story, kept here as numbered):
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
(PATCH /coordinators/me/availability -- takes the caller out of the pool for
NEW events only; nothing they already hold moves) and per-event release
(POST /events/assigned/{id}/release -- hands off just the one event,
leaving the caller's other work and general eligibility untouched).

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


def test_scrum24_ac2_unavailable_coordinator_is_never_assigned(client, db_session):
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
# Marking unavailable stops NEW events -- it does not move existing ones
# --------------------------------------------------------------------------


def _go_unavailable(client, headers):
    res = client.patch("/coordinators/me/availability", json={"is_available": False}, headers=headers)
    assert res.status_code == 200
    return res


def test_marking_unavailable_leaves_current_events_with_the_coordinator(client, db_session):
    organiser, organiser_headers = _organiser(client, db_session)
    holder, holder_headers = _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")
    other, other_headers = _coordinator(client, db_session, "priya@connectsphere.test", "Priya Nair")

    event_id = _submit(client, organiser_headers)
    assert db_session.get(Event, event_id).coordinator_id == holder.id

    res = _go_unavailable(client, holder_headers)

    assert res.json()["is_available"] is False
    assert db_session.get(Event, event_id).coordinator_id == holder.id
    assert [e["id"] for e in client.get("/events/assigned", headers=holder_headers).json()] == [event_id]
    assert client.get("/events/assigned", headers=other_headers).json() == []


def test_marking_unavailable_keeps_the_event_even_when_nobody_else_is_available(client, db_session):
    """No replacement is looked for, so nobody's absence can leave the
    event unassigned -- unlike declining a single event."""
    organiser, organiser_headers = _organiser(client, db_session)
    holder, holder_headers = _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")
    event_id = _submit(client, organiser_headers)

    _go_unavailable(client, holder_headers)

    assert db_session.get(Event, event_id).coordinator_id == holder.id
    body = client.get(f"/events/{event_id}", headers=organiser_headers).json()
    assert body["coordinator"]["id"] == holder.id


def test_marking_unavailable_leaves_no_trace_on_the_event_or_in_notifications(client, db_session):
    """Nothing was handed over, so there is nothing to log against the event
    and nobody to tell: not the Coordinator, the Organiser, or a bystander."""
    organiser, organiser_headers = _organiser(client, db_session)
    holder, holder_headers = _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")
    _other, other_headers = _coordinator(client, db_session, "priya@connectsphere.test", "Priya Nair")
    event_id = _submit(client, organiser_headers)
    before = {
        name: len(client.get("/notifications", headers=h).json())
        for name, h in (("organiser", organiser_headers), ("holder", holder_headers), ("other", other_headers))
    }
    log_before = client.get(f"/events/{event_id}/activity", headers=organiser_headers).json()

    _go_unavailable(client, holder_headers)

    after = {
        name: len(client.get("/notifications", headers=h).json())
        for name, h in (("organiser", organiser_headers), ("holder", holder_headers), ("other", other_headers))
    }
    assert after == before
    assert client.get(f"/events/{event_id}/activity", headers=organiser_headers).json() == log_before


def test_an_unavailable_coordinator_can_still_work_the_events_they_hold(client, db_session):
    organiser, organiser_headers = _organiser(client, db_session)
    holder, holder_headers = _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")
    event_id = _submit(client, organiser_headers)
    _go_unavailable(client, holder_headers)

    assert client.get(f"/events/assigned/{event_id}", headers=holder_headers).status_code == 200
    assert client.post(f"/events/{event_id}/approve", headers=holder_headers).status_code == 200


def test_scrum24_ac2_new_events_skip_the_unavailable_coordinator_but_old_ones_stay(client, db_session):
    organiser, organiser_headers = _organiser(client, db_session)
    holder, holder_headers = _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")
    other, _ = _coordinator(client, db_session, "priya@connectsphere.test", "Priya Nair")
    first_id = _submit(client, organiser_headers, name="Already assigned")
    assert db_session.get(Event, first_id).coordinator_id == holder.id
    _go_unavailable(client, holder_headers)

    second_id = _submit(client, organiser_headers, name="Submitted afterwards")

    assert db_session.get(Event, first_id).coordinator_id == holder.id  # unchanged
    assert db_session.get(Event, second_id).coordinator_id == other.id  # skipped Sam


def test_scrum24_ac1_profile_shows_unavailable_until_marked_available_again(client, db_session):
    """SCRUM-24 AC1: the status on the profile (GET /auth/me) is
    "Unavailable" from the moment it is set, survives a fresh login and
    unrelated activity, and only flips back when the Coordinator says so."""
    organiser, organiser_headers = _organiser(client, db_session)
    _sam, headers = _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")
    assert client.get("/auth/me", headers=headers).json()["user"]["is_available"] is True

    _go_unavailable(client, headers)
    assert client.get("/auth/me", headers=headers).json()["user"]["is_available"] is False

    # A brand-new session, and other people's activity, change nothing.
    token = client.post(
        "/auth/login", json={"email": "sam@connectsphere.test", "password": "password123"}
    ).json()["access_token"]
    fresh_headers = {"Authorization": f"Bearer {token}"}
    _submit(client, organiser_headers)
    assert client.get("/auth/me", headers=fresh_headers).json()["user"]["is_available"] is False

    client.patch("/coordinators/me/availability", json={"is_available": True}, headers=fresh_headers)
    assert client.get("/auth/me", headers=fresh_headers).json()["user"]["is_available"] is True


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


def test_scrum24_ac3_availability_can_be_turned_back_on(client, db_session):
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


def test_64_ac1_releasing_one_event_reassigns_only_that_one(client, db_session):
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
    assert "declined this event" in entries[0]["note"]
    assert "marked themselves unavailable" not in entries[0]["note"]

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


# --------------------------------------------------------------------------
# Availability history -- GET /coordinators/me/availability-history
# --------------------------------------------------------------------------


def test_scrum24_ac4_toggling_availability_with_zero_active_events_is_still_logged(client, db_session):
    """AC5: logged even when there's no event for event_status_history to
    attach a row to."""
    _, headers = _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")

    client.patch("/coordinators/me/availability", json={"is_available": False}, headers=headers)
    entries = client.get("/coordinators/me/availability-history", headers=headers).json()
    assert len(entries) == 1
    assert entries[0]["is_available"] is False
    assert entries[0]["created_at"] is not None

    client.patch("/coordinators/me/availability", json={"is_available": True}, headers=headers)
    entries = client.get("/coordinators/me/availability-history", headers=headers).json()
    assert len(entries) == 2


def test_scrum24_ac4_toggling_to_the_same_value_does_not_add_a_history_entry(client, db_session):
    _, headers = _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")

    client.patch("/coordinators/me/availability", json={"is_available": True}, headers=headers)
    entries = client.get("/coordinators/me/availability-history", headers=headers).json()
    assert entries == []


def test_availability_history_is_scoped_to_the_caller(client, db_session):
    _, sam_headers = _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")
    _, priya_headers = _coordinator(client, db_session, "priya@connectsphere.test", "Priya Nair")

    client.patch("/coordinators/me/availability", json={"is_available": False}, headers=sam_headers)

    assert len(client.get("/coordinators/me/availability-history", headers=sam_headers).json()) == 1
    assert client.get("/coordinators/me/availability-history", headers=priya_headers).json() == []


def test_scrum24_ac4_availability_history_orders_newest_first(client, db_session):
    _, headers = _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")

    client.patch("/coordinators/me/availability", json={"is_available": False}, headers=headers)
    client.patch("/coordinators/me/availability", json={"is_available": True}, headers=headers)

    entries = client.get("/coordinators/me/availability-history", headers=headers).json()
    assert [e["is_available"] for e in entries] == [True, False]


def test_only_a_coordinator_can_view_their_availability_history(client, db_session):
    _, organiser_headers = _organiser(client, db_session)
    assert client.get("/coordinators/me/availability-history", headers=organiser_headers).status_code == 403


def test_anonymous_cannot_view_availability_history(client):
    assert client.get("/coordinators/me/availability-history").status_code == 401


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


def test_release_pushes_to_both_coordinators(client, db_session):
    """Everyone in a hand-off hears about it live, not just on next load:
    both Coordinators, and the Organiser who needs to know who took over."""
    organiser, organiser_headers = _organiser(client, db_session)
    outgoing, outgoing_headers = _coordinator(
        client, db_session, "sam@connectsphere.test", "Sam Tan"
    )
    replacement, _ = _coordinator(client, db_session, "priya@connectsphere.test", "Priya Nair")
    event_id = _submit(client, organiser_headers)

    with patch.object(broker, "publish") as publish:
        client.post(f"/events/assigned/{event_id}/release", headers=outgoing_headers)

    pushed = {(user_id, payload["type"]) for user_id, payload in _pushed(publish)}
    assert pushed == {
        (replacement.id, "event_assigned"),
        (outgoing.id, "event_reassigned_away"),
        (organiser.id, "event_coordinator_assigned"),
    }


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


# --------------------------------------------------------------------------
# SCRUM-64 -- declining ONE event: AC2, AC3, AC4 stated in the ticket's words
# --------------------------------------------------------------------------


def test_64_ac2_a_coordinator_who_declined_still_receives_new_events(client, db_session):
    """After declining, the Coordinator is still in the pool: the next event
    submitted goes to them (they now hold the fewest, having just given one
    away), not around them."""
    organiser, organiser_headers = _organiser(client, db_session)
    decliner, decliner_headers = _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")
    other, _ = _coordinator(client, db_session, "priya@connectsphere.test", "Priya Nair")
    declined_id = _submit(client, organiser_headers, name="To be declined")
    assert db_session.get(Event, declined_id).coordinator_id == decliner.id

    client.post(f"/events/assigned/{declined_id}/release", headers=decliner_headers)
    assert db_session.get(Event, declined_id).coordinator_id == other.id

    new_id = _submit(client, organiser_headers, name="Submitted after the decline")

    assert db_session.get(Event, new_id).coordinator_id == decliner.id


def test_64_ac3_declining_does_not_change_the_profile_status(client, db_session):
    """The profile (GET /auth/me) still says available -- and the history a
    Coordinator sees of their own availability gains no entry, because
    nothing about their availability changed."""
    organiser, organiser_headers = _organiser(client, db_session)
    decliner, decliner_headers = _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")
    _coordinator(client, db_session, "priya@connectsphere.test", "Priya Nair")
    event_id = _submit(client, organiser_headers)
    history_before = client.get(
        "/coordinators/me/availability-history", headers=decliner_headers
    ).json()

    res = client.post(f"/events/assigned/{event_id}/release", headers=decliner_headers)

    assert res.status_code == 200
    assert client.get("/auth/me", headers=decliner_headers).json()["user"]["is_available"] is True
    assert (
        client.get("/coordinators/me/availability-history", headers=decliner_headers).json()
        == history_before
    )


def test_64_ac4_the_decline_is_logged_with_a_timestamp_and_the_decliners_name(client, db_session):
    """One entry, attributed to the Coordinator who declined, timestamped,
    and readable by the Organiser and the Coordinator who took over."""
    organiser, organiser_headers = _organiser(client, db_session)
    decliner, decliner_headers = _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")
    _other, other_headers = _coordinator(client, db_session, "priya@connectsphere.test", "Priya Nair")
    event_id = _submit(client, organiser_headers)

    client.post(f"/events/assigned/{event_id}/release", headers=decliner_headers)

    for headers, view in (
        (organiser_headers, lambda h: client.get(f"/events/{event_id}/activity", headers=h).json()),
        (
            other_headers,
            lambda h: client.get(f"/events/assigned/{event_id}", headers=h).json()["activity"],
        ),
    ):
        entries = [e for e in view(headers) if "declined this event" in (e["note"] or "")]
        assert len(entries) == 1
        assert entries[0]["changed_by_name"] == "Sam Tan"
        assert entries[0]["created_at"] is not None


def test_64_ac4_a_decline_is_logged_even_when_nobody_else_can_take_the_event(client, db_session):
    """The criterion is unconditional: "the decline is recorded in that
    event's activity log with a timestamp and my name". With no replacement
    the event becomes unassigned -- which is exactly when a record of who
    let go of it, and when, matters most."""
    organiser, organiser_headers = _organiser(client, db_session)
    decliner, decliner_headers = _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")
    event_id = _submit(client, organiser_headers)

    client.post(f"/events/assigned/{event_id}/release", headers=decliner_headers)

    assert db_session.get(Event, event_id).coordinator_id is None
    log = client.get(f"/events/{event_id}/activity", headers=organiser_headers).json()
    entries = [e for e in log if "declined this event" in (e["note"] or "")]
    assert len(entries) == 1
    assert entries[0]["changed_by_name"] == "Sam Tan"
    assert entries[0]["created_at"] is not None
    assert "unassigned" in entries[0]["note"]
