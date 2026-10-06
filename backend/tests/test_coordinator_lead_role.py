"""Tests for the Event Coordinator Lead role story.

Traceability:
  AC1 - Given access control is set up, when an Event Coordinator Lead
        account is created, then it has the Event Coordinator Lead role,
        which can assign and reassign Event Requests and view all
        Coordinator Assignments.
  AC2 - Given a Lead account exists, when its user logs in, logs out or
        edits their profile, then each action works as it does for an
        Event Coordinator.
  AC3 - Given the Lead role is added, when a user with an existing role
        logs in, then the pages and actions available to that role are
        unchanged.

Existing roles that exist in code: Organiser, Coordinator, Venue Staff,
Technical Support Staff, Attendee. (Safety Officer is a label in the live
database enum but not yet a `Role` in code, so it has no behaviour to pin.)
"""

import pytest

from app.core.deps import permissions_for
from app.core.roles import (
    ROLE_LABELS,
    ROLE_PERMISSIONS,
    CoordinatorLeadProfile,
    CoordinatorProfile,
    Permission,
    Role,
    RoleProfile,
)
from app.models.user import User

PASSWORD = "password123"
ASSIGN = {Permission.ASSIGNMENT_MANAGE, Permission.ASSIGNMENT_VIEW_ALL}

# Frozen copy of every pre-existing role's grants, written out literally so
# that AC3 fails if any of them changes.
EXISTING_ROLE_PERMISSIONS = {
    Role.COORDINATOR: {
        "event:read", "event:write", "venue:read", "venue:book",
        "equipment:read", "registration:read", "registration:manage",
    },
    Role.VENUE_STAFF: {"venue:read", "venue:manage", "event:read"},
    Role.TECH_SUPPORT: {"equipment:read", "equipment:manage", "event:read"},
    Role.ATTENDEE: {"event:read", "venue:read", "registration:read"},
}
EXISTING_ROLES = [Role.ORGANISER, *EXISTING_ROLE_PERMISSIONS]


def _account(client, db_session, role: Role, email=None):
    """Register an account, give it `role`, and return (email, auth headers)."""
    email = email or f"{role.value}@cs.local"
    client.post("/auth/register", json={"name": "Test User", "email": email, "password": PASSWORD})
    db_session.query(User).filter(User.email == email).update({"role": role.value})
    db_session.commit()
    token = client.post("/auth/login", json={"email": email, "password": PASSWORD}).json()["access_token"]
    return email, {"Authorization": f"Bearer {token}"}


# --- AC1: the role exists and carries the Lead's powers -------------------


def test_ac1_role_value_matches_the_database_enum_label():
    assert Role.COORDINATOR_LEAD.value == "event_coordinator_lead"
    assert ROLE_LABELS[Role.COORDINATOR_LEAD] == "Event Coordinator Lead"


def test_ac1_lead_can_assign_and_reassign_and_view_all_assignments():
    granted = permissions_for(Role.COORDINATOR_LEAD.value)
    assert ASSIGN <= granted


def test_ac1_lead_account_reports_the_lead_role_and_assignment_permissions(client, db_session):
    _, auth = _account(client, db_session, Role.COORDINATOR_LEAD)
    body = client.get("/auth/me", headers=auth).json()
    assert body["user"]["role"] == "event_coordinator_lead"
    assert {"assignment:manage", "assignment:view_all"} <= set(body["permissions"])


def test_ac1_a_plain_coordinator_cannot_assign_or_view_all_assignments():
    assert not ASSIGN & permissions_for(Role.COORDINATOR.value)


def test_ac1_lead_profile_inherits_from_coordinator_profile():
    assert issubclass(CoordinatorLeadProfile, CoordinatorProfile)
    assert issubclass(CoordinatorProfile, RoleProfile)
    lead = CoordinatorLeadProfile()
    assert lead.permissions == CoordinatorProfile().permissions | ASSIGN
    assert ROLE_PERMISSIONS[Role.COORDINATOR_LEAD] == lead.permissions


# --- AC2: login, logout and profile editing behave as for a Coordinator --


@pytest.mark.parametrize("role", [Role.COORDINATOR, Role.COORDINATOR_LEAD])
def test_ac2_login_succeeds_and_sets_refresh_cookie(client, db_session, role):
    email, _ = _account(client, db_session, role)
    res = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert res.status_code == 200
    assert res.json()["access_token"]
    assert client.cookies.get("refresh_token")


@pytest.mark.parametrize("role", [Role.COORDINATOR, Role.COORDINATOR_LEAD])
def test_ac2_wrong_password_is_rejected(client, db_session, role):
    email, _ = _account(client, db_session, role)
    assert client.post("/auth/login", json={"email": email, "password": "nope-nope"}).status_code == 401


@pytest.mark.parametrize("role", [Role.COORDINATOR, Role.COORDINATOR_LEAD])
def test_ac2_logout_clears_the_session(client, db_session, role):
    _account(client, db_session, role)
    assert client.cookies.get("refresh_token")
    assert client.post("/auth/logout").status_code == 204
    assert client.post("/auth/refresh").status_code == 401


@pytest.mark.parametrize("role", [Role.COORDINATOR, Role.COORDINATOR_LEAD])
def test_ac2_profile_edit_saves_and_persists_across_login(client, db_session, role):
    email, auth = _account(client, db_session, role)
    res = client.patch(
        "/users/me",
        json={"name": "Renamed Lead", "organisation": "Acme", "phone_country_code": "+65", "phone_number": "91234567"},
        headers=auth,
    )
    assert res.status_code == 200
    assert res.json()["name"] == "Renamed Lead"
    assert res.json()["role"] == role.value  # editing a profile never changes the role

    token = client.post("/auth/login", json={"email": email, "password": PASSWORD}).json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["user"]
    assert (me["name"], me["organisation"], me["phone_number"]) == ("Renamed Lead", "Acme", "91234567")


@pytest.mark.parametrize("role", [Role.COORDINATOR, Role.COORDINATOR_LEAD])
def test_ac2_invalid_profile_edit_is_rejected_and_nothing_saved(client, db_session, role):
    _, auth = _account(client, db_session, role)
    assert client.patch("/users/me", json={"email": "not-an-email"}, headers=auth).status_code == 422
    assert client.patch("/users/me", json={"name": "  "}, headers=auth).status_code == 422
    assert client.get("/auth/me", headers=auth).json()["user"]["name"] == "Test User"


def test_ac2_lead_holds_every_permission_a_coordinator_holds():
    assert permissions_for(Role.COORDINATOR.value) <= permissions_for(Role.COORDINATOR_LEAD.value)


# --- AC3: existing roles are unchanged -----------------------------------


@pytest.mark.parametrize("role", list(EXISTING_ROLE_PERMISSIONS))
def test_ac3_existing_role_permissions_are_unchanged(role):
    assert {str(p) for p in permissions_for(role.value)} == EXISTING_ROLE_PERMISSIONS[role]


def test_ac3_organiser_keeps_every_permission_it_had():
    previous = {p for p in Permission if p not in ASSIGN}
    assert previous <= permissions_for(Role.ORGANISER.value)


@pytest.mark.parametrize("role", EXISTING_ROLES)
def test_ac3_existing_role_logs_in_with_its_own_role_and_no_lead_powers(client, db_session, role):
    _, auth = _account(client, db_session, role)
    body = client.get("/auth/me", headers=auth).json()
    assert body["user"]["role"] == role.value
    if role is not Role.ORGANISER:  # Organiser is admin-equivalent: holds every permission
        assert not ASSIGN & {Permission(p) for p in body["permissions"]}


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        (Role.ORGANISER, 200),  # the one role allowed on this endpoint
        (Role.COORDINATOR, 403),
        (Role.VENUE_STAFF, 403),
        (Role.TECH_SUPPORT, 403),
        (Role.ATTENDEE, 403),
    ],
)
def test_ac3_role_gated_endpoint_access_is_unchanged(client, db_session, role, expected):
    _, auth = _account(client, db_session, role)
    assert client.get("/coordinators/available-count", headers=auth).status_code == expected


def test_ac3_lead_is_not_added_to_the_coordinator_assignment_pool(client, db_session):
    """Auto-assignment still picks only Coordinators, so no existing flow
    starts routing Event Requests to the Lead."""
    from app.services.assignment import available_coordinators

    _account(client, db_session, Role.COORDINATOR, "c@cs.local")
    _account(client, db_session, Role.COORDINATOR_LEAD, "l@cs.local")
    assert [u.email for u in available_coordinators(db_session).all()] == ["c@cs.local"]


def test_ac3_existing_role_values_are_unchanged():
    assert {r.value for r in Role if r is not Role.COORDINATOR_LEAD} == {
        "organiser", "coordinator", "venue_staff", "tech_support", "attendee",
    }
