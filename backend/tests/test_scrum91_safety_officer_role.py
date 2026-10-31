"""Tests for SCRUM-91 "Create Safety Officer Role".

    As ConnectSphere, I want a Safety Officer role added to the system, so that
    only the Safety Officer can record Operational Safety Check decisions.
"""

import pytest

from app.core.roles import ROLE_LABELS, ROLE_PERMISSIONS, Permission, Role
from app.models.enums import EventStatus
from app.models.events import Event
from tests.event_review_test_helpers import user

OTHER_ROLES = [r for r in Role if r != Role.SAFETY_OFFICER]
DECISIONS = {
    "approve": None,
    "reject": {"reason": "Not safe."},
    "request-changes": {"reason": "Not safe.", "venue_booking_ids": [1], "equipment_request_ids": []},
}


def _officer(client, db_session):
    return user(client, db_session, Role.SAFETY_OFFICER, "safety@example.com", "Sasha Safety")


def test_ac1_an_account_is_given_the_role_with_its_own_permissions(client, db_session):
    _, headers = _officer(client, db_session)

    body = client.get("/auth/me", headers=headers).json()

    assert body["user"]["role"] == "safety_officer"
    assert body["permissions"] == [Permission.EVENT_READ.value]
    assert ROLE_LABELS[Role.SAFETY_OFFICER] == "Safety Officer"


def test_ac2_logging_in_works_as_for_other_internal_users(client, db_session):
    _officer(client, db_session)

    res = client.post("/auth/login", json={"email": "safety@example.com", "password": "password123"})

    assert res.status_code == 200 and res.json()["access_token"]
    assert client.cookies.get("refresh_token")


def test_ac2_logging_out_works_as_for_other_internal_users(client, db_session):
    _officer(client, db_session)

    assert client.post("/auth/logout").status_code == 204

    assert client.post("/auth/refresh").status_code == 401


def test_ac2_editing_the_profile_works_as_for_other_internal_users(client, db_session):
    _, headers = _officer(client, db_session)

    res = client.patch(
        "/users/me",
        json={"name": "Sasha Renamed", "department": "events_coordination"},
        headers=headers,
    )

    assert res.status_code == 200
    assert client.get("/auth/me", headers=headers).json()["user"]["name"] == "Sasha Renamed"


@pytest.mark.parametrize("decision", DECISIONS)
@pytest.mark.parametrize("role", OTHER_ROLES)
def test_ac3_anyone_else_is_refused_a_decision_and_the_event_stays_put(client, db_session, role, decision):
    owner, _ = user(client, db_session, Role.ORGANISER, "owner@example.com", "Owner")
    event = Event(name="Summit", organiser_id=owner.id, status=EventStatus.awaiting_safety_check)
    db_session.add(event)
    db_session.commit()
    _, headers = user(client, db_session, role, "other@example.com", "Other")

    res = client.post(f"/safety-checks/{event.id}/{decision}", json=DECISIONS[decision], headers=headers)

    assert res.status_code == 403
    db_session.expire_all()
    assert db_session.get(Event, event.id).status == EventStatus.awaiting_safety_check


@pytest.mark.parametrize("decision", DECISIONS)
def test_ac3_someone_not_logged_in_is_refused_a_decision(client, decision):
    assert client.post(f"/safety-checks/1/{decision}", json=DECISIONS[decision]).status_code == 401


@pytest.mark.parametrize(
    "role, expected",
    [
        (
            Role.COORDINATOR,
            {
                "event:read",
                "event:write",
                "venue:read",
                "venue:book",
                "equipment:read",
                "registration:read",
                "registration:manage",
            },
        ),
        (Role.VENUE_STAFF, {"venue:read", "venue:manage", "event:read"}),
        (Role.TECH_SUPPORT, {"equipment:read", "equipment:manage", "event:read"}),
        (Role.ATTENDEE, {"event:read", "venue:read", "registration:read"}),
    ],
)
def test_ac4_existing_roles_keep_exactly_the_access_they_had(role, expected):
    assert {p.value for p in ROLE_PERMISSIONS[role]} == expected


def test_ac4_the_organiser_still_holds_every_permission():
    assert ROLE_PERMISSIONS[Role.ORGANISER] == frozenset(Permission)
