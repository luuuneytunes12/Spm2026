from app.core.roles import Role
from app.models.events import Event
from app.models.user import User

COMPLETE = {
    "name": "Regional Partner Conference",
    "purpose": "Annual partner briefing",
    "event_type": "conference",
    "proposed_start": "2026-11-02T09:00:00Z",
    "proposed_end": "2026-11-02T17:00:00Z",
    "expected_attendance": 120,
    "venue_requirements": "Main hall",
    "accessibility_needs": "Step-free access",
}


def user(client, db_session, role, email, name):
    password = "password123"
    assert client.post(
        "/auth/register", json={"name": name, "email": email, "password": password}
    ).status_code == 201
    record = db_session.query(User).filter(User.email == email).one()
    record.role = role.value
    db_session.commit()
    token = client.post("/auth/login", json={"email": email, "password": password}).json()[
        "access_token"
    ]
    return record, {"Authorization": f"Bearer {token}"}


def submitted_event(client, organiser_headers):
    event_id = client.post("/events", json=COMPLETE, headers=organiser_headers).json()["id"]
    assert client.post(f"/events/{event_id}/submit", headers=organiser_headers).status_code == 200
    return event_id


def review_setup(client, db_session):
    organiser, organiser_headers = user(
        client, db_session, Role.ORGANISER, "organiser@example.com", "Organiser"
    )
    coordinator, coordinator_headers = user(
        client, db_session, Role.COORDINATOR, "coordinator@example.com", "Coordinator"
    )
    event_id = submitted_event(client, organiser_headers)
    event = db_session.get(Event, event_id)
    assert event.coordinator_id == coordinator.id
    assert event.status == "under_review"
    return organiser, organiser_headers, coordinator, coordinator_headers, event_id