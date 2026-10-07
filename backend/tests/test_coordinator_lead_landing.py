"""Backend tests for the Event Coordinator Lead landing-page story.

Story: as a Lead, I want a landing page after login with shortcuts to
unassigned Event Requests and all Coordinator Assignments.

  AC1 - login lands on the Lead page, welcoming first name + role
        (frontend: LandingPage tests, e2e TC-CLL-1e; the role -> home-page
        mapping is in frontend/src/lib/roles.test.ts)
  AC2 - shortcuts to Unassigned Requests and all Coordinator Assignments
        each lead to a working feature -> the two endpoints below
  AC3 - with unassigned requests, the shortcut shows how many -> the count
        is the length of the unassigned list
  AC4 - with none, no number is shown -> the unassigned list is empty

Existing behaviour is pinned too: only the Lead may read these views, and
reading them changes nothing.
"""

import pytest

from app.core.roles import Role
from app.models.enums import EventStatus
from app.models.events import Event
from app.models.user import User
from app.services.assignment_overview import (
    CoordinatorAssignments,
    EventListing,
    UnassignedRequests,
)

PASSWORD = "password123"


def _account(client, db_session, role: Role, email: str, name="Test User"):
    client.post("/auth/register", json={"name": name, "email": email, "password": PASSWORD})
    user = db_session.query(User).filter(User.email == email).one()
    user.role = role.value
    db_session.commit()
    token = client.post("/auth/login", json={"email": email, "password": PASSWORD}).json()["access_token"]
    return user, {"Authorization": f"Bearer {token}"}


def _event(db_session, organiser, *, status=EventStatus.submitted_awaiting_coordinator, coordinator=None, name="Event"):
    event = Event(
        organiser_id=organiser.id,
        coordinator_id=coordinator.id if coordinator else None,
        name=name,
        status=status,
    )
    db_session.add(event)
    db_session.commit()
    return event


@pytest.fixture()
def world(client, db_session):
    lead, lead_auth = _account(client, db_session, Role.COORDINATOR_LEAD, "lead@cs.local", "Lena Lead")
    organiser, _ = _account(client, db_session, Role.ORGANISER, "org@cs.local", "Olivia Organiser")
    coordinator, _ = _account(client, db_session, Role.COORDINATOR, "coord@cs.local", "Sam Tan")
    return {"lead_auth": lead_auth, "organiser": organiser, "coordinator": coordinator}


# --- AC2: the two shortcuts lead somewhere that works ---------------------


def test_ac2_unassigned_requests_lists_only_active_unassigned_events(client, db_session, world):
    org, coord = world["organiser"], world["coordinator"]
    wanted = _event(db_session, org, name="Needs a coordinator")
    _event(db_session, org, name="Already assigned", coordinator=coord)
    _event(db_session, org, name="Still a draft", status=EventStatus.draft)
    _event(db_session, org, name="Was rejected", status=EventStatus.event_rejected)

    res = client.get("/lead/unassigned-requests", headers=world["lead_auth"])
    assert res.status_code == 200
    body = res.json()
    assert [e["id"] for e in body] == [wanted.id]
    assert body[0]["coordinator"] is None
    assert body[0]["organiser"]["name"] == "Olivia Organiser"


def test_ac2_assignments_lists_active_assigned_events_with_their_coordinator(client, db_session, world):
    org, coord = world["organiser"], world["coordinator"]
    held = _event(db_session, org, name="Held", coordinator=coord, status=EventStatus.under_review)
    _event(db_session, org, name="Unassigned")
    _event(db_session, org, name="Done", coordinator=coord, status=EventStatus.event_completed)

    res = client.get("/lead/assignments", headers=world["lead_auth"])
    assert res.status_code == 200
    body = res.json()
    assert [e["id"] for e in body] == [held.id]
    assert body[0]["coordinator"]["name"] == "Sam Tan"
    assert body[0]["status"] == "under_review"


def test_ac2_assignments_include_every_coordinators_events(client, db_session, world):
    org = world["organiser"]
    other, _ = _account(client, db_session, Role.COORDINATOR, "c2@cs.local", "Priya Nair")
    _event(db_session, org, coordinator=world["coordinator"], status=EventStatus.under_review)
    _event(db_session, org, coordinator=other, status=EventStatus.planning_event)
    body = client.get("/lead/assignments", headers=world["lead_auth"]).json()
    assert {e["coordinator"]["name"] for e in body} == {"Sam Tan", "Priya Nair"}


# --- AC3 / AC4: the number on the Unassigned Requests shortcut ------------


def test_ac3_count_is_the_number_of_unassigned_requests(client, db_session, world):
    for i in range(3):
        _event(db_session, world["organiser"], name=f"Unassigned {i}")
    assert len(client.get("/lead/unassigned-requests", headers=world["lead_auth"]).json()) == 3


def test_ac4_no_unassigned_requests_gives_an_empty_list(client, db_session, world):
    _event(db_session, world["organiser"], coordinator=world["coordinator"])
    assert client.get("/lead/unassigned-requests", headers=world["lead_auth"]).json() == []


def test_ac4_no_events_at_all_gives_empty_lists(client, world):
    assert client.get("/lead/unassigned-requests", headers=world["lead_auth"]).json() == []
    assert client.get("/lead/assignments", headers=world["lead_auth"]).json() == []


# --- Negative: only the Lead may read these views --------------------------


@pytest.mark.parametrize("path", ["/lead/unassigned-requests", "/lead/assignments"])
@pytest.mark.parametrize(
    "role", [Role.ORGANISER, Role.COORDINATOR, Role.VENUE_STAFF, Role.TECH_SUPPORT, Role.ATTENDEE]
)
def test_other_roles_are_forbidden(client, db_session, role, path):
    _, auth = _account(client, db_session, role, f"{role.value}@cs.local")
    assert client.get(path, headers=auth).status_code == 403


@pytest.mark.parametrize("path", ["/lead/unassigned-requests", "/lead/assignments"])
def test_unauthenticated_is_rejected(client, path):
    assert client.get(path).status_code == 401


def test_reading_the_views_changes_nothing(client, db_session, world):
    event = _event(db_session, world["organiser"])
    before = (event.status, event.coordinator_id, event.updated_at)
    client.get("/lead/unassigned-requests", headers=world["lead_auth"])
    client.get("/lead/assignments", headers=world["lead_auth"])
    db_session.refresh(event)
    assert (event.status, event.coordinator_id, event.updated_at) == before


# --- OOP: the two views inherit one listing --------------------------------


def test_views_inherit_from_the_shared_listing():
    assert issubclass(UnassignedRequests, EventListing)
    assert issubclass(CoordinatorAssignments, EventListing)
    assert UnassignedRequests.narrow is not EventListing.narrow


def test_unassigned_and_assigned_views_never_overlap(client, db_session, world):
    org = world["organiser"]
    _event(db_session, org)
    _event(db_session, org, coordinator=world["coordinator"])
    unassigned = {e.id for e in UnassignedRequests().rows(db_session)}
    assigned = {e.id for e in CoordinatorAssignments().rows(db_session)}
    assert unassigned and assigned and not unassigned & assigned
