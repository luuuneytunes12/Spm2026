"""Tests for the "See which coordinator is assigned" story (Event Organiser).

    As an Event Organiser, I want to see which coordinator has been
    assigned to my event, so that I know who owns my request.

Acceptance criteria:
    AC1 - Given my event is submitted, when a coordinator is assigned,
          then I can see their name and contact on my event page.
    AC2 - Given an Event Coordinator is assigned to my submitted event,
          then I receive a notification with the Event Coordinator's
          details.
    AC3 - Given a new Event Coordinator is reassigned to my Event, I can
          see name and contact of the new Event Coordinator.
    AC4 - Given a new Event Coordinator is assigned to my submitted event,
          then I receive a notification with the new Event Coordinator's
          details.

Assignment and reassignment both go through app/services/assignment.py
(assign_coordinator / reassign_event), which is shared with the "Mark
myself unavailable" story covered in test_coordinator_availability.py --
this file only tests what THIS story's ACs, above, actually promise the
Organiser, from the Organiser's own side of the fence.

Two different channels carry this information and are tested separately:

    * The event ACTIVITY LOG (GET /events/{id}/activity, and the coordinator's
      GET /events/assigned/{id}) is the event's shared record -- everyone
      involved in the event reads the same entries.
    * NOTIFICATIONS (GET /notifications) are role-specific -- each recipient
      gets a message worded for their role, and nobody gets someone else's.

Each test name states the acceptance criterion it covers.
"""

from app.core.roles import Role
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

    Mirrors the identical helper in test_coordinator_availability.py.
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


def _reassign_by_declining(client, event_id, outgoing_headers) -> None:
    res = client.post(f"/events/assigned/{event_id}/release", headers=outgoing_headers)
    assert res.status_code == 200


# --------------------------------------------------------------------------
# AC1 -- name and contact visible on the event page once assigned
# --------------------------------------------------------------------------


def test_ac1_organiser_sees_assigned_coordinators_name_and_contact(client, db_session):
    organiser, organiser_headers = _organiser(client, db_session)
    coordinator, _ = _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")

    event_id = _submit(client, organiser_headers)

    body = client.get(f"/events/{event_id}", headers=organiser_headers).json()
    assert body["coordinator"] == {
        "id": coordinator.id,
        "name": "Sam Tan",
        "email": "sam@connectsphere.test",
    }


def test_ac1_no_coordinator_shown_before_one_is_assigned(client, db_session):
    """Honest empty state while the request has not yet been picked up."""
    organiser, organiser_headers = _organiser(client, db_session)

    event_id = _submit(client, organiser_headers)

    body = client.get(f"/events/{event_id}", headers=organiser_headers).json()
    assert body["coordinator_id"] is None
    assert body["coordinator"] is None


# --------------------------------------------------------------------------
# AC2 -- notification with the coordinator's details on assignment
# --------------------------------------------------------------------------


def test_ac2_organiser_notified_with_assigned_coordinators_details(client, db_session):
    organiser, organiser_headers = _organiser(client, db_session)
    _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")

    event_id = _submit(client, organiser_headers)

    notifications = client.get("/notifications", headers=organiser_headers).json()
    assigned = [n for n in notifications if n["type"] == "event_coordinator_assigned"]
    assert len(assigned) == 1
    assert assigned[0]["event_id"] == event_id
    assert "Sam Tan" in assigned[0]["message"]
    assert "sam@connectsphere.test" in assigned[0]["message"]


def test_ac2_no_notification_when_nobody_is_available_to_assign(client, db_session):
    """No assignment happened, so there is nothing to notify the Organiser
    about -- submitting still succeeds, just silently unassigned."""
    organiser, organiser_headers = _organiser(client, db_session)

    _submit(client, organiser_headers)

    notifications = client.get("/notifications", headers=organiser_headers).json()
    assert [n for n in notifications if n["type"] == "event_coordinator_assigned"] == []


# --------------------------------------------------------------------------
# AC3 -- name and contact of the NEW coordinator visible after reassignment
# --------------------------------------------------------------------------


def test_ac3_organiser_sees_new_coordinators_name_and_contact_after_reassignment(client, db_session):
    organiser, organiser_headers = _organiser(client, db_session)
    outgoing, outgoing_headers = _coordinator(
        client, db_session, "sam@connectsphere.test", "Sam Tan"
    )
    replacement, _ = _coordinator(client, db_session, "priya@connectsphere.test", "Priya Nair")

    event_id = _submit(client, organiser_headers)
    assert client.get(f"/events/{event_id}", headers=organiser_headers).json()["coordinator"]["id"] == outgoing.id

    _reassign_by_declining(client, event_id, outgoing_headers)

    body = client.get(f"/events/{event_id}", headers=organiser_headers).json()
    assert body["coordinator"] == {
        "id": replacement.id,
        "name": "Priya Nair",
        "email": "priya@connectsphere.test",
    }


def test_ac3_organiser_sees_unassigned_when_reassignment_finds_nobody(client, db_session):
    """The flip side: declining with no other Coordinator available leaves
    the event unassigned rather than stuck with someone unavailable --
    the Organiser's page must reflect that honestly, not show stale data."""
    organiser, organiser_headers = _organiser(client, db_session)
    outgoing, outgoing_headers = _coordinator(
        client, db_session, "sam@connectsphere.test", "Sam Tan"
    )
    event_id = _submit(client, organiser_headers)

    _reassign_by_declining(client, event_id, outgoing_headers)

    body = client.get(f"/events/{event_id}", headers=organiser_headers).json()
    assert body["coordinator"] is None
    assert body["coordinator_id"] is None


# --------------------------------------------------------------------------
# AC4 -- notification with the NEW coordinator's details on reassignment
# --------------------------------------------------------------------------


def test_ac4_organiser_notified_with_new_coordinators_details_on_reassignment(client, db_session):
    organiser, organiser_headers = _organiser(client, db_session)
    outgoing, outgoing_headers = _coordinator(
        client, db_session, "sam@connectsphere.test", "Sam Tan"
    )
    _replacement, _ = _coordinator(client, db_session, "priya@connectsphere.test", "Priya Nair")
    event_id = _submit(client, organiser_headers)

    _reassign_by_declining(client, event_id, outgoing_headers)

    notifications = client.get("/notifications", headers=organiser_headers).json()
    assigned = [n for n in notifications if n["type"] == "event_coordinator_assigned"]
    assert len(assigned) == 2  # initial assignment, then reassignment
    reassignment_notice = assigned[0]  # newest first
    assert reassignment_notice["event_id"] == event_id
    assert "Priya Nair" in reassignment_notice["message"]
    assert "priya@connectsphere.test" in reassignment_notice["message"]


def test_ac4_no_second_notification_when_reassignment_finds_nobody(client, db_session):
    organiser, organiser_headers = _organiser(client, db_session)
    outgoing, outgoing_headers = _coordinator(
        client, db_session, "sam@connectsphere.test", "Sam Tan"
    )
    event_id = _submit(client, organiser_headers)

    _reassign_by_declining(client, event_id, outgoing_headers)

    notifications = client.get("/notifications", headers=organiser_headers).json()
    assigned = [n for n in notifications if n["type"] == "event_coordinator_assigned"]
    assert len(assigned) == 1  # only the initial assignment; nobody took over


# --------------------------------------------------------------------------
# AC2 / AC4 -- what the notification carries, and that it is well formed
# --------------------------------------------------------------------------


def test_ac2_notification_starts_unread_and_links_to_the_event(client, db_session):
    organiser, organiser_headers = _organiser(client, db_session)
    _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")

    event_id = _submit(client, organiser_headers, name="Partner Conference")

    notice = [
        n
        for n in client.get("/notifications", headers=organiser_headers).json()
        if n["type"] == "event_coordinator_assigned"
    ][0]
    assert notice["is_read"] is False
    assert notice["event_id"] == event_id
    assert "Partner Conference" in notice["message"]


def test_ac2_notification_is_pushed_live_to_the_organiser(client, db_session):
    from unittest.mock import patch

    from app.services.notifications import broker

    organiser, organiser_headers = _organiser(client, db_session)
    _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")

    with patch.object(broker, "publish") as publish:
        _submit(client, organiser_headers)

    pushed = [
        call.args[1] for call in publish.call_args_list if call.args[0] == organiser.id
    ]
    assert [p["type"] for p in pushed] == ["event_coordinator_assigned"]
    assert "sam@connectsphere.test" in pushed[0]["message"]


def test_going_unavailable_does_not_change_the_organisers_coordinator(client, db_session):
    """Global unavailability (SCRUM-24) only stops NEW events, so it is not
    a reassignment: the Organiser's page still shows the same Coordinator
    and no "now coordinating" notification is sent."""
    organiser, organiser_headers = _organiser(client, db_session)
    holder, holder_headers = _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")
    _coordinator(client, db_session, "priya@connectsphere.test", "Priya Nair")
    event_id = _submit(client, organiser_headers)

    res = client.patch(
        "/coordinators/me/availability", json={"is_available": False}, headers=holder_headers
    )
    assert res.status_code == 200

    body = client.get(f"/events/{event_id}", headers=organiser_headers).json()
    assert body["coordinator"]["id"] == holder.id
    assert _types(client, organiser_headers) == ["event_coordinator_assigned"]  # just the first


def test_ac4_every_reassignment_notifies_again(client, db_session):
    """Three Coordinators, two hand-offs: one notification for the first
    assignment plus one per reassignment, newest first."""
    organiser, organiser_headers = _organiser(client, db_session)
    headers_by_name = {
        name: _coordinator(client, db_session, f"{name.split()[0].lower()}@connectsphere.test", name)[1]
        for name in ("Sam Tan", "Priya Nair", "Lee Wong")
    }
    event_id = _submit(client, organiser_headers)

    def current_owner() -> dict:
        return client.get(f"/events/{event_id}", headers=organiser_headers).json()["coordinator"]

    # Whoever holds it declines, twice -- the pool is only three deep.
    _reassign_by_declining(client, event_id, headers_by_name[current_owner()["name"]])
    _reassign_by_declining(client, event_id, headers_by_name[current_owner()["name"]])

    final_owner = current_owner()
    assigned = [
        n
        for n in client.get("/notifications", headers=organiser_headers).json()
        if n["type"] == "event_coordinator_assigned"
    ]
    assert len(assigned) == 3
    assert final_owner["email"] in assigned[0]["message"]  # newest notification = current owner


# --------------------------------------------------------------------------
# Activity log: the SHARED record of the assignment
# --------------------------------------------------------------------------


def test_assignment_is_in_the_activity_log_the_organiser_can_read(client, db_session):
    organiser, organiser_headers = _organiser(client, db_session)
    _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")

    event_id = _submit(client, organiser_headers)

    log = client.get(f"/events/{event_id}/activity", headers=organiser_headers).json()
    assert any(entry["note"] == "Assigned to Sam Tan." for entry in log)


def test_reassignment_is_in_the_activity_log_the_organiser_can_read(client, db_session):
    organiser, organiser_headers = _organiser(client, db_session)
    _outgoing, outgoing_headers = _coordinator(
        client, db_session, "sam@connectsphere.test", "Sam Tan"
    )
    _coordinator(client, db_session, "priya@connectsphere.test", "Priya Nair")
    event_id = _submit(client, organiser_headers)

    _reassign_by_declining(client, event_id, outgoing_headers)

    log = client.get(f"/events/{event_id}/activity", headers=organiser_headers).json()
    assert log[0]["note"].startswith("Reassigned from Sam Tan to Priya Nair")  # newest first


def test_the_activity_log_is_one_record_seen_by_organiser_and_coordinator(client, db_session):
    """Shared, not per-role: the Coordinator reads the very same entries the
    Organiser does. (Contrast with notifications, below.)"""
    organiser, organiser_headers = _organiser(client, db_session)
    _coordinator_user, coordinator_headers = _coordinator(
        client, db_session, "sam@connectsphere.test", "Sam Tan"
    )
    event_id = _submit(client, organiser_headers)

    organiser_log = client.get(f"/events/{event_id}/activity", headers=organiser_headers).json()
    coordinator_log = client.get(
        f"/events/assigned/{event_id}", headers=coordinator_headers
    ).json()["activity"]

    assert organiser_log == coordinator_log
    assert any(entry["note"] == "Assigned to Sam Tan." for entry in coordinator_log)


# --------------------------------------------------------------------------
# Notifications: ROLE-SPECIFIC -- each recipient gets only their own
# --------------------------------------------------------------------------


def _types(client, headers) -> list[str]:
    return [n["type"] for n in client.get("/notifications", headers=headers).json()]


def test_assignment_sends_each_role_its_own_notification(client, db_session):
    organiser, organiser_headers = _organiser(client, db_session)
    _coordinator_user, coordinator_headers = _coordinator(
        client, db_session, "sam@connectsphere.test", "Sam Tan"
    )

    _submit(client, organiser_headers)

    # Organiser: who is coordinating. Coordinator: that they were assigned.
    assert _types(client, organiser_headers) == ["event_coordinator_assigned"]
    assert _types(client, coordinator_headers) == ["event_assigned"]


def test_the_organisers_notification_is_worded_for_the_organiser(client, db_session):
    organiser, organiser_headers = _organiser(client, db_session)
    _coordinator_user, coordinator_headers = _coordinator(
        client, db_session, "sam@connectsphere.test", "Sam Tan"
    )
    _submit(client, organiser_headers)

    organiser_msg = client.get("/notifications", headers=organiser_headers).json()[0]["message"]
    coordinator_msg = client.get("/notifications", headers=coordinator_headers).json()[0]["message"]

    assert "is now coordinating" in organiser_msg
    assert "You have been assigned" in coordinator_msg
    assert organiser_msg != coordinator_msg


def test_reassignment_sends_the_outgoing_coordinator_only_their_own_notice(client, db_session):
    """The outgoing Coordinator hears it moved on; they do not get the
    Organiser's "who is coordinating" message."""
    organiser, organiser_headers = _organiser(client, db_session)
    _outgoing, outgoing_headers = _coordinator(
        client, db_session, "sam@connectsphere.test", "Sam Tan"
    )
    _replacement, replacement_headers = _coordinator(
        client, db_session, "priya@connectsphere.test", "Priya Nair"
    )
    event_id = _submit(client, organiser_headers)

    _reassign_by_declining(client, event_id, outgoing_headers)

    assert sorted(_types(client, outgoing_headers)) == ["event_assigned", "event_reassigned_away"]
    assert _types(client, replacement_headers) == ["event_assigned"]
    assert "event_coordinator_assigned" not in _types(client, outgoing_headers)
    assert "event_coordinator_assigned" not in _types(client, replacement_headers)


def test_an_unrelated_organiser_and_coordinator_are_not_notified(client, db_session):
    organiser, organiser_headers = _organiser(client, db_session)
    _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")
    _bystander_org, bystander_org_headers = _user(
        client, db_session, Role.ORGANISER, "other@connectsphere.test", name="Other Organiser"
    )
    _bystander_coord, bystander_coord_headers = _user(
        client, db_session, Role.COORDINATOR, "zed@connectsphere.test", name="Zed Lim"
    )
    _submit(client, organiser_headers)

    assert _types(client, bystander_org_headers) == []
    assert "event_coordinator_assigned" not in _types(client, bystander_coord_headers)


def test_another_organiser_cannot_see_the_coordinator_on_my_event(client, db_session):
    """The name/contact are for the event's own Organiser only."""
    organiser, organiser_headers = _organiser(client, db_session)
    _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")
    _other, other_headers = _user(
        client, db_session, Role.ORGANISER, "other@connectsphere.test", name="Other Organiser"
    )
    event_id = _submit(client, organiser_headers)

    assert client.get(f"/events/{event_id}", headers=other_headers).status_code == 404
    assert client.get(f"/events/{event_id}/activity", headers=other_headers).status_code == 404


def test_anonymous_cannot_read_the_coordinator_or_the_notification(client, db_session):
    organiser, organiser_headers = _organiser(client, db_session)
    _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")
    event_id = _submit(client, organiser_headers)

    assert client.get(f"/events/{event_id}").status_code == 401
    assert client.get("/notifications").status_code == 401
