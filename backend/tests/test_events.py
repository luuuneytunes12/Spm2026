"""Tests for the "Draft an Event Request" / "Submit an Event Request" stories.

Each test name states the acceptance criterion it covers, so a story can be
traced to the tests that prove it (see the S1/S2 AC markers in the
docstrings).
"""

from app.core.roles import Role
from app.models.events import Event, EventStatusHistory
from app.models.user import User

# A request with every mandatory field filled in.
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


def _organiser(client, db_session, email="org@example.com"):
    """Register a user and promote them to Organiser.

    Registration always assigns `attendee` (by design -- a client can never
    pick its own role), so the role is set directly here, the same way
    scripts/create_admin.py bootstraps the first Organiser.
    """
    res = client.post(
        "/auth/register", json={"name": "Org User", "email": email, "password": "password123"}
    )
    assert res.status_code == 201
    user = db_session.query(User).filter(User.email == email).one()
    user.role = Role.ORGANISER.value
    db_session.commit()
    # Re-login so the returned token reflects the new role.
    token = client.post("/auth/login", json={"email": email, "password": "password123"}).json()[
        "access_token"
    ]
    return user, {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------
# Story 1 -- Draft an Event Request
# --------------------------------------------------------------------------


def test_draft_saves_with_almost_everything_empty(client, db_session):
    """S1 AC2: an INCOMPLETE request can be saved as a draft.

    The core of the story: no name, no dates, no attendance -- just a
    purpose. This is the case the original NOT NULL columns made
    impossible (see sql/003_events_draft_fields.sql).
    """
    _, headers = _organiser(client, db_session)

    res = client.post("/events", json={"purpose": "Something about robotics"}, headers=headers)

    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "draft"
    assert body["name"] is None
    assert body["proposed_start"] is None
    assert body["expected_attendance"] is None


def test_draft_reopens_with_all_previous_input_intact(client, db_session):
    """S1 AC2: a draft can be reopened later with previous input intact."""
    _, headers = _organiser(client, db_session)
    partial = {
        "purpose": "Team offsite",
        "event_type": "workshop",
        "programme": "0900 keynote, 1030 breakouts",
        "room_layout_preference": "classroom",
        "special_arrangements": "Halal catering",
    }
    event_id = client.post("/events", json=partial, headers=headers).json()["id"]

    res = client.get(f"/events/{event_id}", headers=headers)

    assert res.status_code == 200
    body = res.json()
    for field, value in partial.items():
        assert body[field] == value


def test_draft_can_be_edited_and_completed_over_time(client, db_session):
    """S1: requirements are captured over time, across several saves."""
    _, headers = _organiser(client, db_session)
    event_id = client.post("/events", json={"purpose": "Phase one"}, headers=headers).json()["id"]

    client.patch(f"/events/{event_id}", json={"name": "Phase two name"}, headers=headers)
    res = client.patch(f"/events/{event_id}", json={"expected_attendance": 40}, headers=headers)

    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "Phase two name"
    assert body["expected_attendance"] == 40
    # The earlier value survived both subsequent edits.
    assert body["purpose"] == "Phase one"
    assert body["status"] == "draft"


def test_patch_omitting_a_field_does_not_clear_it(client, db_session):
    """S1 AC2: 'all previous input intact' -- a partial edit must not null
    out fields the form did not send."""
    _, headers = _organiser(client, db_session)
    event_id = client.post(
        "/events", json={"purpose": "Keep me", "programme": "Keep me too"}, headers=headers
    ).json()["id"]

    res = client.patch(f"/events/{event_id}", json={"name": "New name"}, headers=headers)

    assert res.json()["purpose"] == "Keep me"
    assert res.json()["programme"] == "Keep me too"


def test_draft_does_not_appear_in_the_review_queue(client, db_session):
    """S1 AC3: a draft must not appear in the Coordinator's submitted queue."""
    _, headers = _organiser(client, db_session)
    client.post("/events", json={"purpose": "Still deciding"}, headers=headers)

    res = client.get("/events/queue", headers=headers)

    assert res.status_code == 200
    assert res.json() == []


def test_draft_appears_in_the_queue_only_once_submitted(client, db_session):
    """S1 AC3: '...until it is submitted'."""
    _, headers = _organiser(client, db_session)
    event_id = client.post("/events", json=COMPLETE, headers=headers).json()["id"]
    assert client.get("/events/queue", headers=headers).json() == []

    client.post(f"/events/{event_id}/submit", headers=headers)

    queue = client.get("/events/queue", headers=headers).json()
    assert [e["id"] for e in queue] == [event_id]


# --------------------------------------------------------------------------
# Story 2 -- Submit an Event Request
# --------------------------------------------------------------------------


def test_submit_blocked_when_mandatory_fields_missing(client, db_session):
    """S2 AC1: submission is blocked and the missing fields are flagged."""
    _, headers = _organiser(client, db_session)
    event_id = client.post("/events", json={"purpose": "Bare draft"}, headers=headers).json()["id"]

    res = client.post(f"/events/{event_id}/submit", headers=headers)

    assert res.status_code == 422
    flagged = {item["loc"][-1] for item in res.json()["detail"]}
    # Every mandatory field except the one that was filled in.
    assert flagged == {
        "name",
        "event_type",
        "proposed_start",
        "proposed_end",
        "expected_attendance",
        "venue_requirements",
        "accessibility_needs",
        "equipment_requirements",
    }
    # Blocked means blocked: still a draft.
    assert db_session.get(Event, event_id).status == "draft"


def test_submit_treats_whitespace_only_as_missing(client, db_session):
    """S2 AC1: a field left as spaces is not 'filled in'."""
    _, headers = _organiser(client, db_session)
    payload = {**COMPLETE, "venue_requirements": "   "}
    event_id = client.post("/events", json=payload, headers=headers).json()["id"]

    res = client.post(f"/events/{event_id}/submit", headers=headers)

    assert res.status_code == 422
    assert {i["loc"][-1] for i in res.json()["detail"]} == {"venue_requirements"}


def test_submit_sets_status_to_submitted(client, db_session):
    """S2 AC2: with all mandatory fields complete, status becomes Submitted."""
    _, headers = _organiser(client, db_session)
    event_id = client.post("/events", json=COMPLETE, headers=headers).json()["id"]

    res = client.post(f"/events/{event_id}/submit", headers=headers)

    assert res.status_code == 200
    assert res.json()["status"] == "submitted"
    assert res.json()["submitted_at"] is not None


def test_submitted_request_moves_from_drafts_to_submitted_list(client, db_session):
    """S2 AC3: it appears under Submitted Requests, and no longer under Drafts."""
    _, headers = _organiser(client, db_session)
    event_id = client.post("/events", json=COMPLETE, headers=headers).json()["id"]
    assert [e["id"] for e in client.get("/events?status=draft", headers=headers).json()] == [event_id]

    client.post(f"/events/{event_id}/submit", headers=headers)

    drafts = client.get("/events?status=draft", headers=headers).json()
    submitted = client.get("/events?status=submitted", headers=headers).json()
    assert [e["id"] for e in drafts] == []
    assert [e["id"] for e in submitted] == [event_id]


def test_submit_records_status_history(client, db_session):
    """The draft -> submitted transition is recorded with who and when."""
    user, headers = _organiser(client, db_session)
    event_id = client.post("/events", json=COMPLETE, headers=headers).json()["id"]

    client.post(f"/events/{event_id}/submit", headers=headers)

    history = db_session.query(EventStatusHistory).filter_by(event_id=event_id).all()
    assert len(history) == 1
    assert history[0].from_status == "draft"
    assert history[0].to_status == "submitted"
    assert history[0].changed_by == user.id


def test_submitting_twice_is_rejected(client, db_session):
    """Only a draft can be submitted -- a resubmit must not reset submitted_at."""
    _, headers = _organiser(client, db_session)
    event_id = client.post("/events", json=COMPLETE, headers=headers).json()["id"]
    first = client.post(f"/events/{event_id}/submit", headers=headers).json()

    res = client.post(f"/events/{event_id}/submit", headers=headers)

    assert res.status_code == 409
    assert db_session.get(Event, event_id).submitted_at is not None
    assert client.get(f"/events/{event_id}", headers=headers).json()["submitted_at"] == first["submitted_at"]


def test_submitted_request_cannot_be_edited(client, db_session):
    """A submitted request is under review; edits go through change requests."""
    _, headers = _organiser(client, db_session)
    event_id = client.post("/events", json=COMPLETE, headers=headers).json()["id"]
    client.post(f"/events/{event_id}/submit", headers=headers)

    res = client.patch(f"/events/{event_id}", json={"name": "Sneaky rename"}, headers=headers)

    assert res.status_code == 409
    assert db_session.get(Event, event_id).name == COMPLETE["name"]


# --------------------------------------------------------------------------
# Access control & validation
# --------------------------------------------------------------------------


def test_organiser_cannot_see_another_organisers_draft(client, db_session):
    """EVENT_WRITE alone is not enough -- ownership is enforced per row."""
    _, headers_a = _organiser(client, db_session, email="a@example.com")
    event_id = client.post("/events", json={"purpose": "Private"}, headers=headers_a).json()["id"]
    _, headers_b = _organiser(client, db_session, email="b@example.com")

    res = client.get(f"/events/{event_id}", headers=headers_b)

    # 404 not 403: "not yours" and "does not exist" are indistinguishable,
    # so this cannot be used to probe which ids exist.
    assert res.status_code == 404
    assert client.get("/events", headers=headers_b).json() == []


def test_attendee_cannot_create_an_event_request(client, db_session):
    """Attendees hold EVENT_READ but not EVENT_WRITE."""
    client.post(
        "/auth/register",
        json={"name": "Attendee", "email": "att@example.com", "password": "password123"},
    )
    token = client.post(
        "/auth/login", json={"email": "att@example.com", "password": "password123"}
    ).json()["access_token"]

    res = client.post(
        "/events", json={"purpose": "Nope"}, headers={"Authorization": f"Bearer {token}"}
    )

    assert res.status_code == 403


def test_anonymous_cannot_list_events(client):
    """Not logged in -> 401, no event information revealed."""
    assert client.get("/events").status_code == 401


def test_end_before_start_is_rejected_cleanly(client, db_session):
    """Mirrors the database CHECK -- a 422, not a 500 from an IntegrityError."""
    _, headers = _organiser(client, db_session)
    payload = {
        **COMPLETE,
        "proposed_start": "2026-11-02T17:00:00Z",
        "proposed_end": "2026-11-02T09:00:00Z",
    }

    res = client.post("/events", json=payload, headers=headers)

    assert res.status_code == 422


def test_zero_attendance_is_rejected_cleanly(client, db_session):
    """Mirrors the `expected_attendance > 0` database CHECK."""
    _, headers = _organiser(client, db_session)

    res = client.post("/events", json={**COMPLETE, "expected_attendance": 0}, headers=headers)

    assert res.status_code == 422
