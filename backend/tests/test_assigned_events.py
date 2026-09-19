"""Tests for the "View Assigned Event Details" story (Event Coordinator).

    As an Event Coordinator, I want to view the full details of an event
    assigned to me, so that I can understand its requirements and plan
    accordingly.

Each test name states the acceptance criterion it covers, so a criterion can
be traced to the test that proves it (see the S3 AC markers in the
docstrings, and docs/test-cases-coordinator-assigned-events.md).
"""

from app.core.roles import Role
from app.models.events import Event
from app.models.user import User

# A request with every mandatory field filled in, plus the optional ones, so
# that "the Coordinator can see every requirement" is testable against a
# request that actually carries them all.
COMPLETE = {
    "name": "Regional Partner Conference",
    "purpose": "Annual partner briefing",
    "event_type": "conference",
    "description": "A full-day briefing for our regional partners.",
    "programme": "0900 registration, 0930 keynote, 1100 breakouts",
    "proposed_start": "2026-11-02T09:00:00Z",
    "proposed_end": "2026-11-02T17:00:00Z",
    "expected_attendance": 120,
    "venue_requirements": "Main hall, stage, podium",
    "room_layout_preference": "theatre",
    "accessibility_needs": "Step-free access, hearing loop",
    "equipment_requirements": "2 projectors, 4 radio mics",
    "special_arrangements": "Halal catering",
    "registration_enabled": True,
}


def _user(client, db_session, role, email, name="Test User"):
    """Register a user, promote them to `role`, and return (user, headers).

    Registration always assigns `attendee` (by design -- a client can never
    pick its own role), so the role is set directly here, the same way
    scripts/create_admin.py bootstraps the first Organiser. The re-login is
    what makes the returned token reflect the new role.
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


def _submitted_event(client, organiser_headers, **overrides) -> int:
    """Create a complete request as the Organiser and submit it.

    Going through the API rather than inserting a row means the activity log
    these tests read back is the real one written by the submit endpoint.
    """
    event_id = client.post(
        "/events", json={**COMPLETE, **overrides}, headers=organiser_headers
    ).json()["id"]
    assert client.post(f"/events/{event_id}/submit", headers=organiser_headers).status_code == 200
    return event_id


def _assign(db_session, event_id: int, coordinator: User) -> None:
    """Put `coordinator` on the event.

    Written directly because there is no "assign a Coordinator" endpoint yet
    -- that is its own story. This sets exactly the column that story will
    set, so these tests do not need rewriting when it lands.
    """
    db_session.get(Event, event_id).coordinator_id = coordinator.id
    db_session.commit()


def _setup(client, db_session):
    """The common fixture: one Organiser, one Coordinator, one event
    submitted by the former and assigned to the latter.

    The Coordinator is created and assigned AFTER submission, not before:
    since the "Mark myself unavailable" story, submitting auto-assigns
    whichever Coordinator is available at that moment (see
    app/services/assignment.py), and having one already exist here would
    have it picked up automatically -- which is exactly what several tests
    below need NOT to happen, so they can assign deliberately instead. With
    no Coordinator around yet, submission leaves the event unassigned, same
    as always.
    """
    organiser, organiser_headers = _user(
        client, db_session, Role.ORGANISER, "priya@connectsphere.test", name="Priya Menon"
    )
    event_id = _submitted_event(client, organiser_headers)
    coordinator, coordinator_headers = _user(
        client, db_session, Role.COORDINATOR, "sam@connectsphere.test", name="Sam Tan"
    )
    _assign(db_session, event_id, coordinator)
    return organiser, organiser_headers, coordinator, coordinator_headers, event_id


# --------------------------------------------------------------------------
# AC1 -- every requirement is visible
# --------------------------------------------------------------------------


def test_assigned_event_returns_every_requirement(client, db_session):
    """S3 AC1: name, purpose, description, date/time, expected attendance,
    venue requirements, accessibility needs, equipment requirements and
    registration needs are all available on one response."""
    *_, coordinator_headers, event_id = _setup(client, db_session)

    res = client.get(f"/events/assigned/{event_id}", headers=coordinator_headers)

    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "Regional Partner Conference"
    assert body["purpose"] == "Annual partner briefing"
    assert body["description"] == "A full-day briefing for our regional partners."
    assert body["proposed_start"] is not None
    assert body["proposed_end"] is not None
    assert body["expected_attendance"] == 120
    assert body["venue_requirements"] == "Main hall, stage, podium"
    assert body["accessibility_needs"] == "Step-free access, hearing loop"
    assert body["equipment_requirements"] == "2 projectors, 4 radio mics"
    assert body["registration_enabled"] is True


def test_assigned_event_returns_the_supporting_planning_fields(client, db_session):
    """S3 AC1: the optional fields an Organiser may have filled in are part
    of "the full details" too -- planning a room needs the layout
    preference, and catering needs the special arrangements."""
    *_, coordinator_headers, event_id = _setup(client, db_session)

    body = client.get(f"/events/assigned/{event_id}", headers=coordinator_headers).json()

    assert body["event_type"] == "conference"
    assert body["programme"] == "0900 registration, 0930 keynote, 1100 breakouts"
    assert body["room_layout_preference"] == "theatre"
    assert body["special_arrangements"] == "Halal catering"


# --------------------------------------------------------------------------
# AC2 -- the Organiser's name and contact details
# --------------------------------------------------------------------------


def test_assigned_event_includes_the_organisers_name_and_contact(client, db_session):
    """S3 AC2: the Coordinator can see who raised the request and how to
    reach them. `users` carries no phone number, so email is the contact
    detail -- see OrganiserContact in app/schemas/event.py."""
    organiser, *_, coordinator_headers, event_id = _setup(client, db_session)

    body = client.get(f"/events/assigned/{event_id}", headers=coordinator_headers).json()

    assert body["organiser"] == {
        "id": organiser.id,
        "name": "Priya Menon",
        "email": "priya@connectsphere.test",
    }


def test_organiser_contact_does_not_leak_the_password_hash(client, db_session):
    """OrganiserContact is a projection of `users`, not the row itself."""
    *_, coordinator_headers, event_id = _setup(client, db_session)

    body = client.get(f"/events/assigned/{event_id}", headers=coordinator_headers).json()

    assert set(body["organiser"]) == {"id", "name", "email"}


# --------------------------------------------------------------------------
# AC3 -- the current status
# --------------------------------------------------------------------------


def test_assigned_event_reports_its_current_status(client, db_session):
    """S3 AC3: the event's current status is part of the detail."""
    *_, coordinator_headers, event_id = _setup(client, db_session)

    body = client.get(f"/events/assigned/{event_id}", headers=coordinator_headers).json()

    assert body["status"] == "submitted"
    assert body["submitted_at"] is not None


# --------------------------------------------------------------------------
# AC4 -- the activity log
# --------------------------------------------------------------------------


def test_assigned_event_includes_its_activity_log(client, db_session):
    """S3 AC4: every recorded status change, with who made it and when."""
    organiser, *_, coordinator_headers, event_id = _setup(client, db_session)

    body = client.get(f"/events/assigned/{event_id}", headers=coordinator_headers).json()

    assert len(body["activity"]) == 1
    entry = body["activity"][0]
    assert entry["from_status"] == "draft"
    assert entry["to_status"] == "submitted"
    assert entry["changed_by_name"] == organiser.name
    assert entry["note"] == "Submitted by organiser."
    assert entry["created_at"] is not None


def test_activity_log_is_newest_first(client, db_session):
    """The log reads as "what happened most recently", so ordering is part
    of the contract rather than whatever the database returns."""
    from app.models.events import EventStatusHistory

    organiser, *_, coordinator, coordinator_headers, event_id = _setup(client, db_session)
    db_session.add(
        EventStatusHistory(
            event_id=event_id,
            changed_by=coordinator.id,
            from_status="submitted",
            to_status="under_review",
            note="Picked up for review.",
        )
    )
    db_session.commit()

    body = client.get(f"/events/assigned/{event_id}", headers=coordinator_headers).json()

    assert [e["to_status"] for e in body["activity"]] == ["under_review", "submitted"]
    assert body["activity"][0]["changed_by_name"] == "Sam Tan"


def test_activity_log_is_empty_rather_than_absent_for_an_untouched_event(client, db_session):
    """A draft that has never changed status has an empty log, not a
    missing one -- the UI renders an empty state, not an error."""
    organiser, organiser_headers = _user(
        client, db_session, Role.ORGANISER, "org2@connectsphere.test"
    )
    coordinator, coordinator_headers = _user(
        client, db_session, Role.COORDINATOR, "coord2@connectsphere.test"
    )
    event_id = client.post("/events", json=COMPLETE, headers=organiser_headers).json()["id"]
    _assign(db_session, event_id, coordinator)

    body = client.get(f"/events/assigned/{event_id}", headers=coordinator_headers).json()

    assert body["status"] == "draft"
    assert body["activity"] == []


# --------------------------------------------------------------------------
# AC5 -- events that are not assigned to me
# --------------------------------------------------------------------------


def test_coordinator_cannot_view_an_event_assigned_to_someone_else(client, db_session):
    """S3 AC5: assignment is per row, not per role."""
    *_, event_id = _setup(client, db_session)
    _, other_headers = _user(client, db_session, Role.COORDINATOR, "other@connectsphere.test")

    res = client.get(f"/events/assigned/{event_id}", headers=other_headers)

    # 404 not 403: "not yours" and "does not exist" are indistinguishable,
    # so this cannot be used to probe which ids exist.
    assert res.status_code == 404


def test_coordinator_cannot_view_an_unassigned_event(client, db_session):
    """S3 AC5: an event with no Coordinator at all is not "assigned to me".

    No Coordinator exists yet at submission time, so auto-assignment (see
    the "Mark myself unavailable" story) finds nobody available and the
    event stays genuinely unassigned -- the Coordinator created afterward
    was never the one it went to.
    """
    organiser, organiser_headers = _user(
        client, db_session, Role.ORGANISER, "org3@connectsphere.test"
    )
    event_id = _submitted_event(client, organiser_headers)
    _, coordinator_headers = _user(client, db_session, Role.COORDINATOR, "coord3@connectsphere.test")

    assert client.get(f"/events/assigned/{event_id}", headers=coordinator_headers).status_code == 404


def test_assigned_list_contains_only_my_events(client, db_session):
    """S3 AC5: the list a Coordinator navigates from is scoped the same way
    as the detail view -- one Coordinator's assignment never bleeds into
    another's list.

    A second submitted request, made once a second Coordinator exists, is
    auto-assigned to THEM (the lighter-loaded one, per
    app/services/assignment.py) rather than to `coordinator` -- see the
    "Mark myself unavailable" story. That is exactly the scoping this test
    checks: each Coordinator's list holds only what is actually theirs.
    """
    _, organiser_headers, coordinator, coordinator_headers, mine = _setup(client, db_session)
    _, other_coordinator_headers = _user(
        client, db_session, Role.COORDINATOR, "other2@connectsphere.test"
    )
    other_event_id = _submitted_event(client, organiser_headers)  # auto-assigned to other2

    res = client.get("/events/assigned", headers=coordinator_headers)

    assert res.status_code == 200
    assert [e["id"] for e in res.json()] == [mine]
    # The other Coordinator sees the request auto-assigned to them, and
    # nothing that belongs to `coordinator`.
    assert [e["id"] for e in client.get("/events/assigned", headers=other_coordinator_headers).json()] == [
        other_event_id
    ]


def test_the_organiser_of_an_event_is_not_its_coordinator(client, db_session):
    """Raising a request does not make you its Coordinator. The Organiser
    keeps reading it through GET /events/{id}, which is unaffected."""
    _, organiser_headers, *_, event_id = _setup(client, db_session)

    assert client.get(f"/events/assigned/{event_id}", headers=organiser_headers).status_code == 404
    assert client.get(f"/events/{event_id}", headers=organiser_headers).status_code == 200


def test_anonymous_cannot_view_assigned_events(client):
    """Not logged in -> 401, no event information revealed."""
    assert client.get("/events/assigned").status_code == 401
    assert client.get("/events/assigned/1").status_code == 401


def test_assigned_is_not_captured_as_an_event_id(client, db_session):
    """`/events/assigned` is a route, not `/events/{event_id}` with
    event_id="assigned" -- which would be a 422, not a list."""
    *_, coordinator_headers, _ = _setup(client, db_session)

    res = client.get("/events/assigned", headers=coordinator_headers)

    assert res.status_code == 200
    assert isinstance(res.json(), list)
