"""Tests for the "View Venue Details" story.

    As an internal user (Event Coordinator & Venue Staff), I want to view the
    details of a venue so that I can assess whether it suits an event's
    requirements.

Each test name states the acceptance criterion it covers (see
docs/test-cases-venue-details.md).
"""

import pytest

from app.core.roles import Role
from app.models.user import User
from app.models.venues import Venue


def _headers(client, db_session, role, email="user@example.com"):
    password = "password123"
    res = client.post(
        "/auth/register", json={"name": "Test User", "email": email, "password": password}
    )
    assert res.status_code == 201
    user = db_session.query(User).filter(User.email == email).one()
    user.role = role.value
    db_session.commit()
    token = client.post("/auth/login", json={"email": email, "password": password}).json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


def _venue(db_session, name="Marina Hall", **overrides) -> Venue:
    """There is no endpoint that creates venues yet (VENUE_MANAGE is a
    separate story), so they go in through the model."""
    venue = Venue(
        name=name,
        location=overrides.pop("location", "10 Bayfront Ave, Level 3"),
        capacity=overrides.pop("capacity", 250),
        supported_layouts=overrides.pop("supported_layouts", ["Theatre", "Banquet"]),
        facilities=overrides.pop("facilities", ["Stage", "Projector"]),
        accessibility_features=overrides.pop(
            "accessibility_features", ["Wheelchair access", "Hearing loop"]
        ),
        operating_hours=overrides.pop("operating_hours", "Mon-Fri 08:00-22:00"),
        **overrides,
    )
    db_session.add(venue)
    db_session.commit()
    db_session.refresh(venue)
    return venue


INTERNAL_ROLES = [Role.COORDINATOR, Role.VENUE_STAFF]


# --- AC1: name, location and capacity ---------------------------------------


@pytest.mark.parametrize("role", INTERNAL_ROLES)
def test_internal_user_sees_name_location_and_capacity(client, db_session, role):
    venue = _venue(db_session)
    headers = _headers(client, db_session, role)

    listed = client.get("/venues", headers=headers)
    detail = client.get(f"/venues/{venue.id}", headers=headers)

    assert listed.status_code == 200
    assert listed.json() == [
        {
            "id": venue.id,
            "name": "Marina Hall",
            "location": "10 Bayfront Ave, Level 3",
            "capacity": 250,
            # Added by "Search and Filter Venues": each result shows its
            # facilities (that story's AC4). Still an exact match, so any
            # other change to the list row fails here.
            "facilities": ["Stage", "Projector"],
            "is_active": True,
        }
    ]
    assert detail.status_code == 200
    body = detail.json()
    assert (body["name"], body["location"], body["capacity"]) == (
        "Marina Hall",
        "10 Bayfront Ave, Level 3",
        250,
    )


def test_venue_list_is_alphabetical_and_includes_inactive(client, db_session):
    _venue(db_session, "Sentosa Pavilion")
    _venue(db_session, "Changi Room", is_active=False)
    headers = _headers(client, db_session, Role.COORDINATOR)

    rows = client.get("/venues", headers=headers).json()

    assert [(r["name"], r["is_active"]) for r in rows] == [
        ("Changi Room", False),
        ("Sentosa Pavilion", True),
    ]


# --- AC2: layouts, facilities, accessibility ---------------------------------


def test_detail_shows_layouts_facilities_and_accessibility(client, db_session):
    venue = _venue(db_session)
    headers = _headers(client, db_session, Role.VENUE_STAFF)

    body = client.get(f"/venues/{venue.id}", headers=headers).json()

    assert body["supported_layouts"] == ["Theatre", "Banquet"]
    assert body["facilities"] == ["Stage", "Projector"]
    assert body["accessibility_features"] == ["Wheelchair access", "Hearing loop"]


def test_detail_returns_empty_lists_when_nothing_recorded(client, db_session):
    venue = _venue(
        db_session, supported_layouts=[], facilities=[], accessibility_features=[]
    )
    headers = _headers(client, db_session, Role.COORDINATOR)

    body = client.get(f"/venues/{venue.id}", headers=headers).json()

    assert body["supported_layouts"] == []
    assert body["facilities"] == []
    assert body["accessibility_features"] == []


# --- AC3: operating hours ----------------------------------------------------


def test_detail_shows_operating_hours(client, db_session):
    venue = _venue(db_session, operating_hours="Mon-Fri 08:00-22:00\nSat 09:00-18:00")
    headers = _headers(client, db_session, Role.COORDINATOR)

    body = client.get(f"/venues/{venue.id}", headers=headers).json()

    assert body["operating_hours"] == "Mon-Fri 08:00-22:00\nSat 09:00-18:00"


def test_detail_operating_hours_may_be_unrecorded(client, db_session):
    venue = _venue(db_session, operating_hours=None)
    headers = _headers(client, db_session, Role.COORDINATOR)

    assert client.get(f"/venues/{venue.id}", headers=headers).json()["operating_hours"] is None


# --- Guards ------------------------------------------------------------------


def test_unknown_venue_is_not_found(client, db_session):
    headers = _headers(client, db_session, Role.COORDINATOR)

    assert client.get("/venues/999", headers=headers).status_code == 404


@pytest.mark.parametrize("role", [Role.ATTENDEE, Role.ORGANISER, Role.TECH_SUPPORT])
def test_non_internal_roles_cannot_view_venues(client, db_session, role):
    venue = _venue(db_session)
    headers = _headers(client, db_session, role)

    assert client.get("/venues", headers=headers).status_code == 403
    assert client.get(f"/venues/{venue.id}", headers=headers).status_code == 403


def test_unauthenticated_request_is_rejected(client, db_session):
    assert client.get("/venues").status_code == 401
