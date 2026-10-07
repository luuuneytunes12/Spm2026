"""Unit cases for the Check Venue Suitability for an Event user story."""

from app.core.roles import Role
from app.models.events import Event
from app.models.user import User
from test_venue_search import _coordinator, _venue


def _assigned_event(db_session, coordinator: User, **overrides) -> Event:
    event = Event(
        name=overrides.pop("name", "Accessibility Workshop"),
        organiser_id=coordinator.id,
        coordinator_id=coordinator.id,
        expected_attendance=overrides.pop("expected_attendance", 80),
        room_layout_preference=overrides.pop("room_layout_preference", "Theatre"),
        accessibility_needs=overrides.pop(
            "accessibility_needs", "Wheelchair access, Hearing loop"
        ),
        venue_requirements=overrides.pop("venue_requirements", "Projector; Stage"),
        **overrides,
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    return event


def test_suitability_marks_a_venue_suitable_when_every_requirement_is_met(
    client, db_session
):
    headers = _coordinator(client, db_session)
    coordinator = db_session.query(User).filter(User.email == "coord@example.com").one()
    venue = _venue(
        db_session,
        "Accessible Hall",
        capacity=100,
        supported_layouts=["Theatre"],
        accessibility_features=["Wheelchair access", "Hearing loop"],
        facilities=["Projector", "Stage"],
    )
    event = _assigned_event(db_session, coordinator)

    response = client.get(
        f"/venues/{venue.id}/suitability/{event.id}",
        headers=headers,
    )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["suitable"] is True
    assert {check["category"] for check in result["checks"]} == {
        "capacity",
        "layout",
        "accessibility",
        "facility",
    }
    assert all(check["met"] for check in result["checks"])


def test_suitability_reports_each_unmet_requirement(client, db_session):
    headers = _coordinator(client, db_session)
    coordinator = db_session.query(User).filter(User.email == "coord@example.com").one()
    venue = _venue(
        db_session,
        "Small Hall",
        capacity=40,
        supported_layouts=["Boardroom"],
        accessibility_features=[],
        facilities=["Projector"],
    )
    event = _assigned_event(db_session, coordinator)

    response = client.get(f"/venues/{venue.id}/suitability/{event.id}", headers=headers)

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["suitable"] is False
    unmet = {(check["category"], check["requirement"]) for check in result["checks"] if not check["met"]}
    assert unmet == {
        ("capacity", "80 people"),
        ("layout", "Theatre"),
        ("accessibility", "Wheelchair access"),
        ("accessibility", "Hearing loop"),
        ("facility", "Stage"),
    }
    assert any("Insufficient capacity" in check["message"] for check in result["checks"])
    assert any("Unsupported layout" in check["message"] for check in result["checks"])
    assert any("Missing facility" in check["message"] for check in result["checks"])


def test_suitability_does_not_claim_success_when_attendance_is_missing(client, db_session):
    headers = _coordinator(client, db_session)
    coordinator = db_session.query(User).filter(User.email == "coord@example.com").one()
    venue = _venue(db_session, "Hall")
    event = _assigned_event(db_session, coordinator, expected_attendance=None)

    response = client.get(f"/venues/{venue.id}/suitability/{event.id}", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["suitable"] is False
    assert response.json()["checks"][0]["met"] is False
    assert "attendance is recorded" in response.json()["checks"][0]["message"]


def test_suitability_only_exposes_events_assigned_to_the_coordinator(client, db_session):
    headers = _coordinator(client, db_session)
    coordinator = db_session.query(User).filter(User.email == "coord@example.com").one()
    other = User(
        name="Other Coordinator",
        email="other-coordinator@example.com",
        password_hash="x",
        role=Role.COORDINATOR.value,
    )
    db_session.add(other)
    db_session.flush()
    venue = _venue(db_session, "Hall")
    event = _assigned_event(db_session, other)

    response = client.get(f"/venues/{venue.id}/suitability/{event.id}", headers=headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "Event not found"


def test_suitability_rejects_non_coordinator_roles(client, db_session):
    venue = _venue(db_session, "Hall")
    password = "password123"
    client.post(
        "/auth/register",
        json={"name": "Venue Staff", "email": "suitability-staff@example.com", "password": password},
    )
    staff = db_session.query(User).filter(User.email == "suitability-staff@example.com").one()
    staff.role = Role.VENUE_STAFF.value
    db_session.commit()
    token = client.post(
        "/auth/login",
        json={"email": "suitability-staff@example.com", "password": password},
    ).json()["access_token"]

    response = client.get(
        f"/venues/{venue.id}/suitability/1",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
