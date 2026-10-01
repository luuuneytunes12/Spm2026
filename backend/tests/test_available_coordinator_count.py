"""Tests for the Organiser's "coordinators available" pool.

A debugging aid: it tells an Organiser which Coordinators a newly
submitted event could be assigned to right now, and how many (0 explains a
request that sits "Not yet assigned"). It must always match the pool that
assignment itself draws from -- see `available_coordinators` in
app/services/assignment.py -- so the tests also check it against who
actually gets picked.

Endpoint: GET /coordinators/available-count
          -> {"available": N, "coordinators": [{"id", "name", "email"}, ...]}
"""

from app.core.roles import Role
from app.models.events import Event
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
    password = "password123"
    res = client.post("/auth/register", json={"name": name, "email": email, "password": password})
    assert res.status_code == 201
    user = db_session.query(User).filter(User.email == email).one()
    user.role = role.value
    db_session.commit()
    token = client.post("/auth/login", json={"email": email, "password": password}).json()[
        "access_token"
    ]
    return user, {"Authorization": f"Bearer {token}"}


def _organiser(client, db_session):
    return _user(client, db_session, Role.ORGANISER, "org@connectsphere.test", "Priya Menon")


def _coordinator(client, db_session, email, name):
    return _user(client, db_session, Role.COORDINATOR, email, name)


def _count(client, headers) -> int:
    res = client.get("/coordinators/available-count", headers=headers)
    assert res.status_code == 200
    return res.json()["available"]


def _set_available(client, headers, value: bool) -> None:
    res = client.patch("/coordinators/me/availability", json={"is_available": value}, headers=headers)
    assert res.status_code == 200


def test_the_count_is_zero_when_there_are_no_coordinators(client, db_session):
    _org, organiser_headers = _organiser(client, db_session)

    assert _count(client, organiser_headers) == 0


def test_the_count_is_the_number_of_available_coordinators(client, db_session):
    _org, organiser_headers = _organiser(client, db_session)
    _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")
    _coordinator(client, db_session, "priya@connectsphere.test", "Priya Nair")

    assert _count(client, organiser_headers) == 2


def test_the_count_ignores_users_who_are_not_coordinators(client, db_session):
    _org, organiser_headers = _organiser(client, db_session)
    _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")
    _user(client, db_session, Role.ATTENDEE, "att@connectsphere.test", "An Attendee")
    _user(client, db_session, Role.VENUE_STAFF, "venue@connectsphere.test", "Venue Staff")
    _user(client, db_session, Role.ORGANISER, "org2@connectsphere.test", "Second Organiser")

    assert _count(client, organiser_headers) == 1


def test_going_unavailable_lowers_the_count_and_coming_back_raises_it(client, db_session):
    _org, organiser_headers = _organiser(client, db_session)
    _sam, sam_headers = _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")
    _coordinator(client, db_session, "priya@connectsphere.test", "Priya Nair")
    assert _count(client, organiser_headers) == 2

    _set_available(client, sam_headers, False)
    assert _count(client, organiser_headers) == 1

    _set_available(client, sam_headers, True)
    assert _count(client, organiser_headers) == 2


def test_declining_one_event_does_not_change_the_count(client, db_session):
    """Declining an event (SCRUM-64) leaves the Coordinator in the pool."""
    _org, organiser_headers = _organiser(client, db_session)
    _sam, sam_headers = _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")
    _coordinator(client, db_session, "priya@connectsphere.test", "Priya Nair")
    event_id = client.post("/events", json=COMPLETE, headers=organiser_headers).json()["id"]
    client.post(f"/events/{event_id}/submit", headers=organiser_headers)

    client.post(f"/events/assigned/{event_id}/release", headers=sam_headers)

    assert _count(client, organiser_headers) == 2


def test_zero_available_means_a_submitted_event_stays_unassigned(client, db_session):
    """The count explains the "Not yet assigned" state it exists to debug."""
    _org, organiser_headers = _organiser(client, db_session)
    _sam, sam_headers = _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")
    _set_available(client, sam_headers, False)
    assert _count(client, organiser_headers) == 0

    event_id = client.post("/events", json=COMPLETE, headers=organiser_headers).json()["id"]
    client.post(f"/events/{event_id}/submit", headers=organiser_headers)

    assert db_session.get(Event, event_id).coordinator_id is None


def test_a_positive_count_means_a_submitted_event_gets_a_coordinator(client, db_session):
    _org, organiser_headers = _organiser(client, db_session)
    _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")
    assert _count(client, organiser_headers) == 1

    event_id = client.post("/events", json=COMPLETE, headers=organiser_headers).json()["id"]
    client.post(f"/events/{event_id}/submit", headers=organiser_headers)

    assert db_session.get(Event, event_id).coordinator_id is not None


def _pool(client, headers) -> list[dict]:
    return client.get("/coordinators/available-count", headers=headers).json()["coordinators"]


def test_the_pool_lists_each_available_coordinator_by_name_and_email(client, db_session):
    _org, organiser_headers = _organiser(client, db_session)
    sam, _ = _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")
    priya, _ = _coordinator(client, db_session, "priya@connectsphere.test", "Priya Nair")

    body = client.get("/coordinators/available-count", headers=organiser_headers).json()

    assert body["available"] == 2
    assert body["coordinators"] == [
        {"id": sam.id, "name": "Sam Tan", "email": "sam@connectsphere.test"},
        {"id": priya.id, "name": "Priya Nair", "email": "priya@connectsphere.test"},
    ]


def test_the_count_always_equals_the_length_of_the_list(client, db_session):
    _org, organiser_headers = _organiser(client, db_session)
    _sam, sam_headers = _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")
    _coordinator(client, db_session, "priya@connectsphere.test", "Priya Nair")

    for available in (True, False, True):
        _set_available(client, sam_headers, available)
        body = client.get("/coordinators/available-count", headers=organiser_headers).json()
        assert body["available"] == len(body["coordinators"])


def test_an_unavailable_coordinator_leaves_the_list_and_returns_when_available(client, db_session):
    _org, organiser_headers = _organiser(client, db_session)
    _sam, sam_headers = _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")
    _coordinator(client, db_session, "priya@connectsphere.test", "Priya Nair")

    _set_available(client, sam_headers, False)
    assert [c["name"] for c in _pool(client, organiser_headers)] == ["Priya Nair"]

    _set_available(client, sam_headers, True)
    assert [c["name"] for c in _pool(client, organiser_headers)] == ["Sam Tan", "Priya Nair"]


def test_the_list_is_empty_when_nobody_is_available(client, db_session):
    _org, organiser_headers = _organiser(client, db_session)
    _sam, sam_headers = _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")
    _set_available(client, sam_headers, False)

    body = client.get("/coordinators/available-count", headers=organiser_headers).json()

    assert body == {"available": 0, "coordinators": []}


def test_the_listed_coordinator_is_who_a_new_event_actually_goes_to(client, db_session):
    """The list is not a guess: with one Coordinator in the pool, that is
    exactly who a new submission is assigned to."""
    _org, organiser_headers = _organiser(client, db_session)
    _sam, sam_headers = _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")
    priya, _ = _coordinator(client, db_session, "priya@connectsphere.test", "Priya Nair")
    _set_available(client, sam_headers, False)
    [listed] = _pool(client, organiser_headers)

    event_id = client.post("/events", json=COMPLETE, headers=organiser_headers).json()["id"]
    client.post(f"/events/{event_id}/submit", headers=organiser_headers)

    assert listed["id"] == priya.id
    assert db_session.get(Event, event_id).coordinator_id == listed["id"]


def test_the_list_exposes_only_id_name_and_email(client, db_session):
    """No password hash, role, availability flag or workload leaks out."""
    _org, organiser_headers = _organiser(client, db_session)
    _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")

    [entry] = _pool(client, organiser_headers)

    assert set(entry) == {"id", "name", "email"}


def test_a_coordinator_cannot_read_the_count(client, db_session):
    _sam, sam_headers = _coordinator(client, db_session, "sam@connectsphere.test", "Sam Tan")

    assert client.get("/coordinators/available-count", headers=sam_headers).status_code == 403


def test_an_attendee_cannot_read_the_count(client, db_session):
    _att, att_headers = _user(client, db_session, Role.ATTENDEE, "att@connectsphere.test")

    assert client.get("/coordinators/available-count", headers=att_headers).status_code == 403


def test_an_anonymous_caller_cannot_read_the_count(client):
    assert client.get("/coordinators/available-count").status_code == 401
