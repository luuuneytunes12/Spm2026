"""Backend tests for SCRUM-82, "View All Coordinator Assignments & Active
Events as Coordinator Lead".

  AC1 - active Events with a Coordinator are listed with name, Coordinator and
        status (active = Under Review, Awaiting Organiser Reply, Event
        Approved, Planning Event, Safety Check Passed)
  AC2 - filtering by a Coordinator shows only theirs, and how many
  AC3 - opening one shows what the Organiser entered plus the Organiser's
        contact details and current status, read-only
  AC4 - anyone without the Lead role is denied (screen data and direct
        request) and sees no Events

These tests do not use the `coordinator_auto_assign` fixture.
"""

import pytest

from app.core.roles import Role
from app.models.enums import EventStatus
from app.models.events import Event
from app.services.assignment_overview import (
    LEAD_ACTIVE_STATUSES,
    ActiveAssignments,
    CoordinatorAssignments,
    CoordinatorWorkload,
)
from event_review_test_helpers import user

LIST = "/lead/assignments"
ACTIVE = [
    EventStatus.under_review,
    EventStatus.changes_requested,
    EventStatus.approved,
    EventStatus.planning,
    EventStatus.confirmed,
]
INACTIVE = [EventStatus.draft, EventStatus.submitted, EventStatus.rejected, EventStatus.completed, EventStatus.cancelled]


@pytest.fixture()
def world(client, db_session):
    org, org_auth = user(client, db_session, Role.ORGANISER, "org@cs.local", "Olivia Organiser")
    sam, _ = user(client, db_session, Role.COORDINATOR, "sam@cs.local", "Sam Tan")
    priya, _ = user(client, db_session, Role.COORDINATOR, "priya@cs.local", "Priya Nair")
    _, lead_auth = user(client, db_session, Role.COORDINATOR_LEAD, "lead@cs.local", "Lena Lead")
    return {"org": org, "sam": sam, "priya": priya, "lead": lead_auth, "db": db_session}


def _event(w, status, coordinator=None, name="Event", **extra):
    e = Event(
        organiser_id=w["org"].id,
        coordinator_id=coordinator.id if coordinator else None,
        name=name,
        status=status,
        purpose="Annual partner briefing",
        description="A full-day briefing.",
        event_type="conference",
        expected_attendance=120,
        venue_requirements="Main hall",
        accessibility_needs="Step-free access",
        equipment_requirements="2 projectors",
        registration_enabled=True,
        **extra,
    )
    w["db"].add(e)
    w["db"].commit()
    return e


# --- AC1 -------------------------------------------------------------------


def test_ac1_lists_each_active_event_with_name_coordinator_and_status(client, world):
    e = _event(world, EventStatus.under_review, world["sam"], name="Partner Conference")
    body = client.get(LIST, headers=world["lead"]).json()
    assert [r["id"] for r in body] == [e.id]
    assert body[0]["name"] == "Partner Conference"
    assert body[0]["coordinator"]["name"] == "Sam Tan"
    assert body[0]["status"] == "under_review"


@pytest.mark.parametrize("status", ACTIVE)
def test_ac1_every_active_status_is_listed(client, world, status):
    _event(world, status, world["sam"])
    assert len(client.get(LIST, headers=world["lead"]).json()) == 1


@pytest.mark.parametrize("status", INACTIVE)
def test_ac1_inactive_statuses_are_not_listed(client, world, status):
    _event(world, status, world["sam"])
    assert client.get(LIST, headers=world["lead"]).json() == []


def test_ac1_an_event_without_a_coordinator_is_not_listed(client, world):
    _event(world, EventStatus.under_review, None)
    assert client.get(LIST, headers=world["lead"]).json() == []


def test_ac1_events_of_every_coordinator_are_listed(client, world):
    _event(world, EventStatus.under_review, world["sam"])
    _event(world, EventStatus.planning, world["priya"])
    assert {r["coordinator"]["name"] for r in client.get(LIST, headers=world["lead"]).json()} == {"Sam Tan", "Priya Nair"}


# --- AC2 -------------------------------------------------------------------


def test_ac2_filtering_by_a_coordinator_shows_only_their_active_events(client, world):
    mine = [_event(world, EventStatus.under_review, world["sam"], name=f"S{i}") for i in range(2)]
    _event(world, EventStatus.planning, world["priya"], name="P1")
    _event(world, EventStatus.completed, world["sam"], name="Finished")  # not active
    body = client.get(LIST, params={"coordinator_id": world["sam"].id}, headers=world["lead"]).json()
    assert {r["id"] for r in body} == {e.id for e in mine}
    assert len(body) == 2


def test_ac2_a_coordinator_with_no_active_events_gives_an_empty_list(client, world):
    _event(world, EventStatus.under_review, world["sam"])
    assert client.get(LIST, params={"coordinator_id": world["priya"].id}, headers=world["lead"]).json() == []


def test_ac2_workload_counts_match_the_filtered_lists(client, world):
    for _ in range(2):
        _event(world, EventStatus.under_review, world["sam"])
    _event(world, EventStatus.completed, world["sam"])
    rows = {r["name"]: r["active_events"] for r in client.get("/lead/coordinators", headers=world["lead"]).json()}
    assert rows == {"Priya Nair": 0, "Sam Tan": 2}
    filtered = client.get(LIST, params={"coordinator_id": world["sam"].id}, headers=world["lead"]).json()
    assert len(filtered) == rows["Sam Tan"]


def test_ac2_workload_lists_only_coordinators(client, world):
    names = {r["name"] for r in client.get("/lead/coordinators", headers=world["lead"]).json()}
    assert names == {"Sam Tan", "Priya Nair"}  # not the Lead or the Organiser


# --- AC3 -------------------------------------------------------------------


def test_ac3_opening_an_event_shows_what_the_organiser_entered_and_their_contact(client, world):
    e = _event(world, EventStatus.approved, world["sam"], name="Review me")
    body = client.get(f"{LIST}/{e.id}", headers=world["lead"]).json()
    assert body["name"] == "Review me"
    assert body["purpose"] == "Annual partner briefing"
    assert body["description"] == "A full-day briefing."
    assert body["event_type"] == "conference"
    assert body["expected_attendance"] == 120
    assert body["venue_requirements"] == "Main hall"
    assert body["equipment_requirements"] == "2 projectors"
    assert body["accessibility_needs"] == "Step-free access"
    assert body["registration_enabled"] is True
    assert body["status"] == "approved"
    assert body["organiser"] == {"id": world["org"].id, "name": "Olivia Organiser", "email": "org@cs.local"}
    assert "proposed_start" in body and "equipment_items" in body


@pytest.mark.parametrize("method", ["put", "patch", "post", "delete"])
def test_ac3_it_is_read_only(client, world, method):
    e = _event(world, EventStatus.under_review, world["sam"], name="Untouched")
    res = client.request(method.upper(), f"{LIST}/{e.id}", headers=world["lead"], json={"name": "Hacked"})
    assert res.status_code == 405
    world["db"].refresh(e)
    assert e.name == "Untouched"


@pytest.mark.parametrize("status", INACTIVE)
def test_ac3_an_event_that_is_not_an_active_assignment_cannot_be_opened(client, world, status):
    e = _event(world, status, world["sam"])
    assert client.get(f"{LIST}/{e.id}", headers=world["lead"]).status_code == 404


def test_ac3_an_unassigned_event_cannot_be_opened_here(client, world):
    e = _event(world, EventStatus.under_review, None)
    assert client.get(f"{LIST}/{e.id}", headers=world["lead"]).status_code == 404


def test_ac3_an_unknown_id_is_a_404(client, world):
    assert client.get(f"{LIST}/99999", headers=world["lead"]).status_code == 404


# --- AC4 -------------------------------------------------------------------

PATHS = [LIST, f"{LIST}?coordinator_id=1", f"{LIST}/1", "/lead/coordinators"]


@pytest.mark.parametrize(
    "role", [Role.ORGANISER, Role.COORDINATOR, Role.VENUE_STAFF, Role.TECH_SUPPORT, Role.ATTENDEE]
)
def test_ac4_other_roles_are_denied_and_see_no_events(client, db_session, world, role):
    e = _event(world, EventStatus.under_review, world["sam"], name="Secret event")
    _, auth = user(client, db_session, role, f"x_{role.value}@cs.local", "Someone Else")
    for path in [LIST, f"{LIST}?coordinator_id={world['sam'].id}", f"{LIST}/{e.id}", "/lead/coordinators"]:
        res = client.get(path, headers=auth)
        assert res.status_code == 403, path
        assert "Secret event" not in res.text


@pytest.mark.parametrize("path", PATHS)
def test_ac4_unauthenticated_is_rejected(client, path):
    assert client.get(path).status_code == 401


# --- OOP and existing behaviour --------------------------------------------


def test_active_assignments_inherit_from_the_earlier_overview_class():
    assert issubclass(ActiveAssignments, CoordinatorAssignments)
    assert ActiveAssignments().coordinator_id is None and ActiveAssignments(5).coordinator_id == 5


def test_the_active_status_set_is_the_stories_definition():
    assert set(LEAD_ACTIVE_STATUSES) == set(ACTIVE)
    assert EventStatus.submitted not in LEAD_ACTIVE_STATUSES


def test_workload_is_a_plain_read_that_changes_nothing(client, world):
    e = _event(world, EventStatus.under_review, world["sam"])
    before = (e.status, e.coordinator_id, e.updated_at)
    CoordinatorWorkload().rows(world["db"])
    client.get(LIST, headers=world["lead"])
    world["db"].refresh(e)
    assert (e.status, e.coordinator_id, e.updated_at) == before
