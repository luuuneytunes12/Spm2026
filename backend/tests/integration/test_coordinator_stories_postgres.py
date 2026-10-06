"""SCRUM-23 / 28 acceptance criteria, on a real PostgreSQL engine.

The same criteria are proven fast on SQLite in tests/test_coordinator_assignment.py,
tests/test_assigned_events.py and tests/test_organiser_coordinator_visibility.py.
These repeat the ones that lean on the database itself -- timestamps,
foreign keys, persistence across separate sessions, ordering -- on the engine
production uses, with every request in its own session.

Each test name states the story and criterion it covers.
"""

from app.core.roles import Role
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
