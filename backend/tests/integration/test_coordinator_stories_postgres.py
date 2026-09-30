"""SCRUM-23 / 24 / 28 / 64 acceptance criteria, on a real PostgreSQL engine.

The same criteria are proven fast on SQLite in tests/test_coordinator_availability.py,
tests/test_assigned_events.py and tests/test_organiser_coordinator_visibility.py.
These repeat the ones that lean on the database itself -- timestamps,
foreign keys, persistence across separate sessions, ordering -- on the engine
production uses, with every request in its own session.

Each test name states the story and criterion it covers.
"""

from datetime import datetime, timedelta

from app.core.roles import Role
from app.models.events import Event, EventStatusHistory
from app.models.notifications import Notification
from tests.integration.conftest import submit_event


def _setup(make_user):
    organiser, org_h = make_user(Role.ORGANISER, "org@connectsphere.test", "Priya Menon")
    sam, sam_h = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")
    priya, priya_h = make_user(Role.COORDINATOR, "priya@connectsphere.test", "Priya Nair")
    return organiser, org_h, sam, sam_h, priya, priya_h


# --------------------------------------------------------------------------
# SCRUM-23 -- the Organiser sees, and is told, who their coordinator is
# --------------------------------------------------------------------------


def test_scrum23_ac1_organiser_sees_the_assigned_coordinators_name_and_contact(client, make_user):
    _o, org_h, sam, _sh, _p, _ph = _setup(make_user)

    event_id = submit_event(client, org_h)

    body = client.get(f"/events/{event_id}", headers=org_h).json()
    assert body["coordinator"] == {"id": sam.id, "name": "Sam Tan", "email": "sam@connectsphere.test"}


def test_scrum23_ac2_organiser_is_notified_with_the_coordinators_details(client, make_user):
    _o, org_h, _s, _sh, _p, _ph = _setup(make_user)

    event_id = submit_event(client, org_h)

    [notice] = [
        n for n in client.get("/notifications", headers=org_h).json()
        if n["type"] == "event_coordinator_assigned"
    ]
    assert notice["event_id"] == event_id
    assert "Sam Tan" in notice["message"] and "sam@connectsphere.test" in notice["message"]


def test_scrum23_ac3_and_ac4_after_a_reassignment_the_organiser_sees_and_is_told_the_new_one(
    client, make_user
):
    _o, org_h, _s, sam_h, priya, _ph = _setup(make_user)
    event_id = submit_event(client, org_h)

    assert client.post(f"/events/assigned/{event_id}/release", headers=sam_h).status_code == 200

    body = client.get(f"/events/{event_id}", headers=org_h).json()
    assert body["coordinator"]["id"] == priya.id  # AC3
    newest = client.get("/notifications", headers=org_h).json()[0]
    assert newest["type"] == "event_coordinator_assigned"  # AC4
    assert "priya@connectsphere.test" in newest["message"]


def test_scrum23_notifications_are_role_specific_and_the_log_is_shared(client, make_user):
    _o, org_h, _s, sam_h, _p, _ph = _setup(make_user)
    event_id = submit_event(client, org_h)

    org_types = [n["type"] for n in client.get("/notifications", headers=org_h).json()]
    sam_types = [n["type"] for n in client.get("/notifications", headers=sam_h).json()]
    assert org_types == ["event_coordinator_assigned"]
    assert sam_types == ["event_assigned"]

    organiser_log = client.get(f"/events/{event_id}/activity", headers=org_h).json()
    coordinator_log = client.get(f"/events/assigned/{event_id}", headers=sam_h).json()["activity"]
    assert organiser_log == coordinator_log


# --------------------------------------------------------------------------
# SCRUM-24 -- global unavailability
# --------------------------------------------------------------------------


def test_scrum24_ac1_profile_status_persists_across_separate_sessions(client, make_user):
    _o, _oh, _s, sam_h, _p, _ph = _setup(make_user)

    client.patch("/coordinators/me/availability", json={"is_available": False}, headers=sam_h)

    for _ in range(3):  # each call is a brand-new session and connection
        assert client.get("/auth/me", headers=sam_h).json()["user"]["is_available"] is False
    client.patch("/coordinators/me/availability", json={"is_available": True}, headers=sam_h)
    assert client.get("/auth/me", headers=sam_h).json()["user"]["is_available"] is True


def test_scrum24_ac2_and_ac3_an_unavailable_coordinator_is_left_out_then_back_in(client, make_user):
    _o, org_h, sam, sam_h, priya, _ph = _setup(make_user)

    client.patch("/coordinators/me/availability", json={"is_available": False}, headers=sam_h)
    left_out = submit_event(client, org_h, name="While Sam is away")
    client.patch("/coordinators/me/availability", json={"is_available": True}, headers=sam_h)
    back_in = submit_event(client, org_h, name="After Sam returns")

    assert client.get(f"/events/{left_out}", headers=org_h).json()["coordinator"]["id"] == priya.id
    # Priya now holds one and Sam none, so the lighter-loaded Sam gets the next.
    assert client.get(f"/events/{back_in}", headers=org_h).json()["coordinator"]["id"] == sam.id


def test_scrum24_going_unavailable_does_not_move_events_already_held(client, make_user):
    _o, org_h, sam, sam_h, _p, _ph = _setup(make_user)
    event_id = submit_event(client, org_h)

    client.patch("/coordinators/me/availability", json={"is_available": False}, headers=sam_h)

    assert client.get(f"/events/{event_id}", headers=org_h).json()["coordinator"]["id"] == sam.id


def test_scrum24_ac4_each_change_is_logged_with_a_timestamp_even_with_no_events(client, make_user):
    _o, _oh, _s, sam_h, _p, _ph = _setup(make_user)

    client.patch("/coordinators/me/availability", json={"is_available": False}, headers=sam_h)
    client.patch("/coordinators/me/availability", json={"is_available": True}, headers=sam_h)

    history = client.get("/coordinators/me/availability-history", headers=sam_h).json()
    assert [h["is_available"] for h in history] == [True, False]  # newest first
    stamps = [datetime.fromisoformat(h["created_at"]) for h in history]
    assert all(s.tzinfo is not None for s in stamps)
    assert abs(datetime.now(stamps[0].tzinfo) - stamps[0]) < timedelta(minutes=5)


# --------------------------------------------------------------------------
# SCRUM-28 -- the Coordinator's full view
# --------------------------------------------------------------------------


def test_scrum28_ac1_to_ac4_the_assigned_event_carries_everything(client, make_user):
    _o, org_h, _s, sam_h, _p, _ph = _setup(make_user)
    event_id = submit_event(client, org_h, description="A full-day briefing.", registration_enabled=True)

    body = client.get(f"/events/assigned/{event_id}", headers=sam_h).json()

    for field in (
        "name", "purpose", "description", "proposed_start", "proposed_end", "expected_attendance",
        "venue_requirements", "accessibility_needs", "equipment_requirements", "registration_enabled",
    ):
        assert body[field] is not None, field
    assert body["organiser"] == {"id": 1, "name": "Priya Menon", "email": "org@connectsphere.test"}
    assert body["status"] == "under_review"
    assert [e["to_status"] for e in body["activity"]][0] == "under_review"  # newest first


def test_scrum28_ac5_an_event_assigned_to_someone_else_is_not_visible(client, make_user):
    _o, org_h, _s, _sh, _p, priya_h = _setup(make_user)
    event_id = submit_event(client, org_h)  # goes to Sam, the lighter id

    assert client.get(f"/events/assigned/{event_id}", headers=priya_h).status_code == 404
    assert client.get("/events/assigned", headers=priya_h).json() == []


# --------------------------------------------------------------------------
# SCRUM-64 -- declining one event
# --------------------------------------------------------------------------


def test_scrum64_ac1_to_ac4_declining_reassigns_one_event_and_records_who_and_when(
    client, make_user, db
):
    _o, org_h, sam, sam_h, priya, _ph = _setup(make_user)
    event_id = submit_event(client, org_h)

    assert client.post(f"/events/assigned/{event_id}/release", headers=sam_h).status_code == 200

    assert db.get(Event, event_id).coordinator_id == priya.id  # AC1
    assert client.get("/auth/me", headers=sam_h).json()["user"]["is_available"] is True  # AC3
    next_id = submit_event(client, org_h, name="Next")  # AC2: still in the pool
    assert db.get(Event, next_id).coordinator_id == sam.id
    entries = (
        db.query(EventStatusHistory)
        .filter(EventStatusHistory.event_id == event_id, EventStatusHistory.note.like("%declined this event%"))
        .all()
    )
    assert len(entries) == 1  # AC4
    assert entries[0].changed_by == sam.id and entries[0].created_at is not None


def test_scrum64_ac4_a_decline_with_nobody_to_take_over_is_still_recorded(client, make_user, db):
    organiser, org_h = make_user(Role.ORGANISER, "org@connectsphere.test", "Priya Menon")
    sam, sam_h = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")
    event_id = submit_event(client, org_h)

    client.post(f"/events/assigned/{event_id}/release", headers=sam_h)

    assert db.get(Event, event_id).coordinator_id is None
    [entry] = (
        db.query(EventStatusHistory)
        .filter(EventStatusHistory.event_id == event_id, EventStatusHistory.note.like("%declined this event%"))
        .all()
    )
    assert entry.changed_by == sam.id
    assert db.query(Notification).filter(Notification.type == "event_coordinator_assigned").count() == 1


def test_scrum64_a_declined_event_cannot_be_declined_again_by_the_same_coordinator(client, make_user):
    _o, org_h, _s, sam_h, _p, _ph = _setup(make_user)
    event_id = submit_event(client, org_h)
    assert client.post(f"/events/assigned/{event_id}/release", headers=sam_h).status_code == 200

    again = client.post(f"/events/assigned/{event_id}/release", headers=sam_h)

    assert again.status_code == 404  # no longer Sam's -- and nothing changed
