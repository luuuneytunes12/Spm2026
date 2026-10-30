"""Tests for SCRUM-63 "Log Out System", on the server's side of it.

    As a registered user, I want to log out of my account, so that my session
    ends and no one else can use my account upon log out.

The redirect to the login page is the browser's:
frontend/src/auth/Logout.test.tsx.
"""

import pytest

from app.core.roles import Role
from app.core.security import create_refresh_token
from app.models.user import User
from tests.event_review_test_helpers import user

ROLES = [Role.ORGANISER, Role.COORDINATOR, Role.VENUE_STAFF, Role.TECH_SUPPORT]


@pytest.mark.parametrize("role", ROLES)
def test_ac1_logging_out_ends_the_session(client, db_session, role):
    user(client, db_session, role, "someone@example.com", "Someone")
    assert client.post("/auth/refresh").status_code == 200

    assert client.post("/auth/logout").status_code == 204

    assert client.cookies.get("refresh_token") is None
    assert client.post("/auth/refresh").status_code == 401


def test_ac1_logging_out_twice_is_harmless(client, db_session):
    user(client, db_session, Role.ORGANISER, "someone@example.com", "Someone")
    assert client.post("/auth/logout").status_code == 204
    assert client.post("/auth/logout").status_code == 204


def test_ac2_after_logging_out_no_new_token_can_be_issued_to_open_a_page(client, db_session):
    user(client, db_session, Role.ORGANISER, "someone@example.com", "Someone")
    client.post("/auth/logout")

    res = client.post("/auth/refresh")

    assert res.status_code == 401
    assert "access_token" not in res.json()


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(create_refresh_token("not-a-number", "attendee"), id="subject is not an id"),
        pytest.param(create_refresh_token(999999, "attendee"), id="account no longer exists"),
    ],
)
def test_ac2_a_refresh_cookie_that_names_no_account_is_refused(client, token):
    client.cookies.set("refresh_token", token)
    assert client.post("/auth/refresh").status_code == 401


def test_ac2_an_access_token_for_a_deleted_account_cannot_read_the_profile(client, db_session):
    record, headers = user(client, db_session, Role.ORGANISER, "someone@example.com", "Someone")
    db_session.delete(db_session.get(User, record.id))
    db_session.commit()

    assert client.get("/auth/me", headers=headers).status_code == 401
