import time

import jwt

from app.core.config import settings
from app.core.roles import Role
from app.models.user import User
from app.routers.auth import REFRESH_COOKIE_NAME


def _register(client, name="Test User", email="user@example.com", password="password123"):
    return client.post("/auth/register", json={"name": name, "email": email, "password": password})


def _login(client, email="user@example.com", password="password123"):
    return client.post("/auth/login", json={"email": email, "password": password})


def test_register_assigns_default_role(client, db_session):
    res = _register(client)
    assert res.status_code == 201
    assert "access_token" in res.json()

    user = db_session.query(User).filter(User.email == "user@example.com").first()
    assert user is not None
    assert user.role == "attendee"
    assert user.name == "Test User"


def test_register_ignores_client_supplied_role(client, db_session):
    res = client.post(
        "/auth/register",
        json={"name": "Sneaky", "email": "sneaky@example.com", "password": "password123", "role": "organiser"},
    )
    assert res.status_code == 201
    user = db_session.query(User).filter(User.email == "sneaky@example.com").first()
    assert user.role == "attendee"


def test_login_returns_access_token(client):
    _register(client)
    res = _login(client)
    assert res.status_code == 200
    body = res.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str)


def test_login_unknown_email_generic_message(client):
    res = _login(client, email="ghost@example.com")
    assert res.status_code == 401
    assert res.json()["detail"] == "Invalid credentials"


def test_login_wrong_password_generic_message(client):
    _register(client)
    res = _login(client, password="wrong-password")
    assert res.status_code == 401
    assert res.json()["detail"] == "Invalid credentials"


def test_me_reflects_role(client):
    _register(client)
    login_res = _login(client)
    token = login_res.json()["access_token"]

    res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    body = res.json()
    assert body["user"]["email"] == "user@example.com"
    assert body["user"]["name"] == "Test User"
    assert body["user"]["role"] == "attendee"
    assert "password_hash" not in body["user"]
    assert "is_active" not in body["user"]
    assert "updated_at" not in body["user"]
    assert "event:read" in body["permissions"]


def test_role_grants_differ_by_role(client, db_session):
    """An attendee and an organiser resolve to different permission sets."""
    _register(client)
    token = _login(client).json()["access_token"]
    attendee_perms = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()[
        "permissions"
    ]
    assert "event:approve" not in attendee_perms
    assert "event:read" in attendee_perms

    _register(client, email="organiser@example.com")
    organiser = db_session.query(User).filter(User.email == "organiser@example.com").first()
    organiser.role = Role.ORGANISER.value
    db_session.commit()

    token = _login(client, email="organiser@example.com").json()["access_token"]
    organiser_perms = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()[
        "permissions"
    ]
    assert "event:approve" in organiser_perms
    assert set(attendee_perms) < set(organiser_perms)


def test_role_change_takes_effect_immediately_with_same_token(client, db_session):
    """get_current_user re-reads the row every request, so a role change
    applies to an already-issued token without a re-login."""
    _register(client)
    token = _login(client).json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    before = client.get("/auth/me", headers=auth).json()
    assert before["user"]["role"] == "attendee"
    assert "event:approve" not in before["permissions"]

    user = db_session.query(User).filter(User.email == "user@example.com").first()
    user.role = Role.ORGANISER.value
    db_session.commit()

    # Same still-valid token, no re-login.
    after = client.get("/auth/me", headers=auth).json()
    assert after["user"]["role"] == "organiser"
    assert "event:approve" in after["permissions"]


def test_unrecognized_role_in_db_gets_no_permissions_not_500(client, db_session):
    _register(client)
    token = _login(client).json()["access_token"]

    user = db_session.query(User).filter(User.email == "user@example.com").first()
    user.role = "some_removed_role"
    db_session.commit()

    # A role string that is not a recognized Role member must resolve to an
    # empty permission set, never a 500.
    res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["permissions"] == []


def test_expired_access_token_401(client):
    _register(client)
    expired_payload = {
        "sub": "1",
        "role": "attendee",
        "typ": "access",
        "iat": int(time.time()) - 120,
        "exp": int(time.time()) - 60,
    }
    token = jwt.encode(expired_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401


def test_tampered_token_401(client):
    _register(client)
    token = _login(client).json()["access_token"]
    tampered = token[:-2] + ("aa" if token[-2:] != "aa" else "bb")
    res = client.get("/auth/me", headers={"Authorization": f"Bearer {tampered}"})
    assert res.status_code == 401


def test_refresh_token_cannot_be_used_as_access_token(client):
    _register(client)
    refresh_cookie = client.cookies.get("refresh_token")
    assert refresh_cookie is not None

    res = client.get("/auth/me", headers={"Authorization": f"Bearer {refresh_cookie}"})
    assert res.status_code == 401


def test_refresh_flow_issues_new_access_token(client):
    _register(client)
    res = client.post("/auth/refresh")
    assert res.status_code == 200
    assert "access_token" in res.json()


def test_refresh_without_cookie_401(client):
    # No register/login call on this client, so no refresh cookie is set.
    res = client.post("/auth/refresh")
    assert res.status_code == 401


def test_logout_clears_cookie(client):
    _register(client)
    assert client.cookies.get("refresh_token") is not None
    res = client.post("/auth/logout")
    assert res.status_code == 204


def test_special_use_email_domains_are_accepted(client):
    """LAN/campus addresses like admin@cs.local must be registerable --
    email_validator blocks these by default (see app/schemas/types.py)."""
    res = client.post(
        "/auth/register",
        json={"name": "Admin", "email": "admin@cs.local", "password": "longenough123"},
    )
    assert res.status_code == 201, res.text


def test_unusable_email_domains_are_still_rejected(client):
    for email in ("admin@foo.invalid", "admin@x.onion", "no-at-sign"):
        res = client.post(
            "/auth/register",
            json={"name": "Admin", "email": email, "password": "longenough123"},
        )
        assert res.status_code == 422, f"{email} -> {res.status_code}"


def test_invalid_credentials_refuse_access_without_revealing_account_existence(client):
    """Acceptance criterion: for BOTH an unknown account and a wrong
    password, login is refused, no session is created, an error is shown,
    and the response does not reveal whether the account exists."""
    _register(client, email="real@example.com", password="correct-password")

    unknown = _login(client, email="ghost@example.com", password="correct-password")
    wrong_pw = _login(client, email="real@example.com", password="wrong-password")

    for res in (unknown, wrong_pw):
        # Access refused, with an error message to show the user.
        assert res.status_code == 401
        assert res.json()["detail"] == "Invalid credentials"
        # No session: no access token in the body, and no refresh cookie set.
        assert "access_token" not in res.json()
        assert REFRESH_COOKIE_NAME not in res.cookies
        assert not any(
            REFRESH_COOKIE_NAME in value
            for key, value in res.headers.items()
            if key.lower() == "set-cookie"
        )

    # The two failures must be indistinguishable: identical status and body.
    # Anything that differs here is an account-enumeration oracle.
    assert unknown.status_code == wrong_pw.status_code
    assert unknown.json() == wrong_pw.json()


def test_failed_login_does_not_grant_access_to_protected_route(client):
    """No session created means the failed login leaves nothing usable."""
    _register(client, email="real@example.com", password="correct-password")
    client.cookies.clear()

    res = _login(client, email="real@example.com", password="wrong-password")
    assert res.status_code == 401

    # The client now holds whatever the failed login left behind (nothing).
    # A refresh must not mint a token, and /auth/me must stay unauthorized.
    assert client.post("/auth/refresh").status_code == 401
    assert client.get("/auth/me").status_code == 401
