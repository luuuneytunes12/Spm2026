"""
Traceability (see docs/test-cases-edit-profile.md):
  TC-EP-1a..1d -- AC1, any profile field can be updated and is reflected
  TC-EP-2a..2b -- AC2, an invalid email is rejected and nothing is saved
  TC-EP-3a..3d -- AC3, an invalid phone number is rejected and nothing is saved
  TC-EP-4a     -- AC4, a saved change survives logout/login
"""

from app.models.user import User


def _register(client, name="Test User", email="user@example.com", password="password123"):
    return client.post("/auth/register", json={"name": name, "email": email, "password": password})


def _login(client, email="user@example.com", password="password123"):
    return client.post("/auth/login", json={"email": email, "password": password})


def _auth_headers(client, **login_kwargs) -> dict:
    token = _login(client, **login_kwargs).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _register_and_auth(client, **kwargs) -> dict:
    _register(client, **kwargs)
    login_kwargs = {}
    if "email" in kwargs:
        login_kwargs["email"] = kwargs["email"]
    if "password" in kwargs:
        login_kwargs["password"] = kwargs["password"]
    return _auth_headers(client, **login_kwargs)


# --- AC1: any profile field can be changed and is reflected immediately --


def test_updates_name_and_organisation(client):
    auth = _register_and_auth(client)
    res = client.patch("/users/me", json={"name": "New Name", "organisation": "Acme Inc"}, headers=auth)
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "New Name"
    assert body["organisation"] == "Acme Inc"


def test_updates_email(client, db_session):
    auth = _register_and_auth(client)
    res = client.patch("/users/me", json={"email": "new@example.com"}, headers=auth)
    assert res.status_code == 200
    assert res.json()["email"] == "new@example.com"

    user = db_session.query(User).filter(User.email == "new@example.com").first()
    assert user is not None


def test_updates_phone_and_communication_preference(client):
    auth = _register_and_auth(client)
    res = client.patch(
        "/users/me",
        json={
            "phone_country_code": "+65",
            "phone_number": "91234567",
            "communication_preference": "sms",
        },
        headers=auth,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["phone_country_code"] == "+65"
    assert body["phone_number"] == "91234567"
    assert body["communication_preference"] == "sms"


def test_change_is_reflected_on_the_next_read(client):
    """AC1: "...then the changes are saved and reflected directly on his
    profile page" -- modelled here as a subsequent GET /auth/me."""
    auth = _register_and_auth(client)
    client.patch("/users/me", json={"name": "Reflected Name"}, headers=auth)

    res = client.get("/auth/me", headers=auth)
    assert res.json()["user"]["name"] == "Reflected Name"


def test_partial_update_leaves_other_fields_untouched(client):
    auth = _register_and_auth(client)
    client.patch("/users/me", json={"organisation": "Acme Inc"}, headers=auth)

    res = client.patch("/users/me", json={"name": "Only Name Changed"}, headers=auth)
    body = res.json()
    assert body["name"] == "Only Name Changed"
    assert body["organisation"] == "Acme Inc"


# --- AC2: an invalid email format is rejected, nothing saved ------------


def test_invalid_email_format_is_rejected(client, db_session):
    auth = _register_and_auth(client)
    res = client.patch("/users/me", json={"name": "Should Not Save", "email": "not-an-email"}, headers=auth)
    assert res.status_code == 422
    assert any("email" in str(item.get("loc")) for item in res.json()["detail"])

    user = db_session.query(User).filter(User.email == "user@example.com").first()
    assert user.name == "Test User"  # unchanged: the whole request was rejected


def test_email_already_registered_to_another_user_is_rejected(client):
    _register(client, name="First", email="taken@example.com")
    auth = _register_and_auth(client, name="Second", email="second@example.com")

    res = client.patch("/users/me", json={"email": "taken@example.com"}, headers=auth)
    assert res.status_code == 409


# --- AC3: an invalid phone number is rejected, nothing saved -------------


def test_phone_number_with_letters_is_rejected(client, db_session):
    auth = _register_and_auth(client)
    res = client.patch(
        "/users/me",
        json={"name": "Should Not Save", "phone_country_code": "+65", "phone_number": "9123abcd"},
        headers=auth,
    )
    assert res.status_code == 422
    assert any("phone_number" in str(item.get("loc")) for item in res.json()["detail"])

    user = db_session.query(User).filter(User.email == "user@example.com").first()
    assert user.name == "Test User"


def test_phone_number_with_wrong_digit_count_for_country_is_rejected(client):
    auth = _register_and_auth(client)
    # Singapore numbers are 8 digits; this is 5.
    res = client.patch(
        "/users/me", json={"phone_country_code": "+65", "phone_number": "12345"}, headers=auth
    )
    assert res.status_code == 422
    assert any("phone_number" in str(item.get("loc")) for item in res.json()["detail"])


def test_unsupported_country_code_is_rejected(client):
    auth = _register_and_auth(client)
    res = client.patch(
        "/users/me", json={"phone_country_code": "+999", "phone_number": "12345678"}, headers=auth
    )
    assert res.status_code == 422


def test_phone_number_valid_for_its_country_code_is_accepted(client):
    auth = _register_and_auth(client)
    # US/Canada expects exactly 10 digits.
    res = client.patch(
        "/users/me", json={"phone_country_code": "+1", "phone_number": "4155552671"}, headers=auth
    )
    assert res.status_code == 200
    assert res.json()["phone_number"] == "4155552671"


def test_phone_number_without_a_country_code_is_rejected(client):
    auth = _register_and_auth(client)
    res = client.patch("/users/me", json={"phone_number": "91234567"}, headers=auth)
    assert res.status_code == 422


# --- AC4: a saved change survives logout and a fresh login ---------------


def test_profile_update_persists_across_logout_and_login(client):
    auth = _register_and_auth(client)
    client.patch(
        "/users/me",
        json={"name": "Persisted Name", "organisation": "Persisted Org"},
        headers=auth,
    )

    assert client.post("/auth/logout").status_code == 204

    new_auth = _auth_headers(client)
    res = client.get("/auth/me", headers=new_auth)
    body = res.json()["user"]
    assert body["name"] == "Persisted Name"
    assert body["organisation"] == "Persisted Org"


# --- Other behaviour a reviewer would expect ------------------------------


def test_unauthenticated_request_is_rejected(client):
    res = client.patch("/users/me", json={"name": "Nope"})
    assert res.status_code == 401


def test_blank_name_is_rejected(client):
    auth = _register_and_auth(client)
    res = client.patch("/users/me", json={"name": "   "}, headers=auth)
    assert res.status_code == 422


def test_unsupported_communication_preference_is_rejected(client):
    auth = _register_and_auth(client)
    res = client.patch("/users/me", json={"communication_preference": "carrier_pigeon"}, headers=auth)
    assert res.status_code == 422
