"""Tests for SCRUM-62 "Set Up Role-Based Access Control (RBAC) Infrastructure".

    As a developer, I want a role-based access control system configured, so
    that the application can enforce role-specific permissions across all
    features.
"""

import pytest

from app.core.deps import permissions_for
from app.core.roles import (
    ROLE_LABELS,
    ROLE_PERMISSIONS,
    CoordinatorProfile,
    Permission,
    Role,
    RoleProfile,
    is_internal_staff,
    role_has,
)
from app.core.security import create_access_token
from tests.event_review_test_helpers import user

PROTECTED = [
    "/auth/me",
    "/notifications",
    "/events/assigned",
    "/lead/unassigned-queue",
    "/safety-checks",
    "/equipment",
    "/venues",
    "/registrations/events",
    "/users/staff",
]


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


# --- AC1 ----------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/users/staff", "/safety-checks", "/registrations/events"])
def test_ac1_an_organiser_is_denied_pages_for_other_roles(client, db_session, path):
    _, headers = user(client, db_session, Role.ORGANISER, "org@example.com", "Org")
    assert client.get(path, headers=headers).status_code == 403


# --- AC2 ----------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/events/assigned", "/venues", "/users/staff"])
def test_ac2_a_coordinator_can_use_coordinator_features(client, db_session, path):
    _, headers = user(client, db_session, Role.COORDINATOR, "coord@example.com", "Coord")
    assert client.get(path, headers=headers).status_code == 200


# --- AC3 ----------------------------------------------------------------------


@pytest.mark.parametrize("path", PROTECTED)
def test_ac3_someone_not_logged_in_is_refused(client, path):
    assert client.get(path).status_code == 401


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(create_access_token("not-a-number", Role.ATTENDEE.value), id="subject is not an id"),
        pytest.param(create_access_token(1, ""), id="no role in the token"),
        pytest.param("not-a-token", id="not a token at all"),
    ],
)
def test_ac3_an_unusable_token_counts_as_not_logged_in(client, token):
    assert client.get("/notifications", headers=_bearer(token)).status_code == 401


# --- AC4 ----------------------------------------------------------------------


@pytest.mark.parametrize("role", list(Role))
def test_ac4_a_user_is_given_exactly_their_roles_permissions(client, db_session, role):
    _, headers = user(client, db_session, role, "someone@example.com", "Someone")
    assert set(client.get("/auth/me", headers=headers).json()["permissions"]) == set(ROLE_PERMISSIONS[role])


def test_ac4_every_role_has_a_label_and_an_entry_in_the_permission_table():
    assert set(ROLE_LABELS) == set(Role)
    assert set(ROLE_PERMISSIONS) == set(Role)


def test_ac4_an_unknown_role_has_no_permissions():
    assert permissions_for("wizard") == frozenset()


def test_ac4_a_token_with_an_unknown_role_is_refused_by_a_role_check(client):
    token = create_access_token(1, "wizard")
    assert client.get("/safety-checks", headers=_bearer(token)).status_code == 403


def test_ac4_a_token_with_an_unknown_role_is_refused_by_a_permission_check(client):
    token = create_access_token(1, "wizard")
    assert client.get("/venues", headers=_bearer(token)).status_code == 403


@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize("permission", list(Permission))
def test_ac4_role_has_agrees_with_the_table(role, permission):
    assert role_has(role, permission) is (permission in ROLE_PERMISSIONS[role])


def test_ac4_a_role_not_in_the_table_has_nothing():
    assert role_has("wizard", Permission.EVENT_READ) is False


@pytest.mark.parametrize(
    "role, expected",
    [
        (Role.COORDINATOR, True),
        (Role.COORDINATOR_LEAD, True),
        (Role.VENUE_STAFF, True),
        (Role.TECH_SUPPORT, True),
        (Role.SAFETY_OFFICER, True),
        (Role.ORGANISER, False),
        (Role.ATTENDEE, False),
        ("wizard", False),
        (None, False),
    ],
)
def test_ac4_internal_staff_are_the_listed_roles_and_anything_else_fails_closed(role, expected):
    assert is_internal_staff(role) is expected


def test_ac4_a_profile_inherits_its_parents_grants_and_labels_itself():
    class Probe(CoordinatorProfile):
        role = Role.COORDINATOR
        extra_permissions = frozenset({Permission.VENUE_MANAGE})

    assert Probe().label == "Event Coordinator"
    assert Probe().permissions == ROLE_PERMISSIONS[Role.COORDINATOR] | {Permission.VENUE_MANAGE}


def test_ac4_a_bare_profile_grants_nothing():
    class Probe(RoleProfile):
        role = Role.ATTENDEE

    assert Probe().permissions == frozenset()
