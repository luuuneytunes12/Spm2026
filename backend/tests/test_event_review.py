"""Coordinator decisions and pre-decision Organiser corrections."""

from app.core.roles import Role
from app.models.events import Event, EventStatusHistory
from app.models.notifications import Notification
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


def _user(client, db_session, role, email, name):
    password = "password123"
    assert client.post(
        "/auth/register", json={"name": name, "email": email, "password": password}
    ).status_code == 201
    user = db_session.query(User).filter(User.email == email).one()
    user.role = role.value
    db_session.commit()
    token = client.post("/auth/login", json={"email": email, "password": password}).json()[
        "access_token"
    ]
    return user, {"Authorization": f"Bearer {token}"}


def _submitted_event(client, organiser_headers):
    event_id = client.post("/events", json=COMPLETE, headers=organiser_headers).json()["id"]
    assert client.post(f"/events/{event_id}/submit", headers=organiser_headers).status_code == 200
    return event_id


def _review_setup(client, db_session):
    organiser, organiser_headers = _user(
        client, db_session, Role.ORGANISER, "organiser@example.com", "Organiser"
    )
    coordinator, coordinator_headers = _user(
        client, db_session, Role.COORDINATOR, "coordinator@example.com", "Coordinator"
    )
    event_id = _submitted_event(client, organiser_headers)
    event = db_session.get(Event, event_id)
    assert event.coordinator_id == coordinator.id
    assert event.status == "under_review"
    return organiser, organiser_headers, coordinator, coordinator_headers, event_id


def test_coordinator_can_approve_assigned_request_and_notify_organiser(client, db_session):
    organiser, _, coordinator, coordinator_headers, event_id = _review_setup(client, db_session)

    response = client.post(f"/events/{event_id}/approve", headers=coordinator_headers)

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    decision = (
        db_session.query(EventStatusHistory)
        .filter_by(event_id=event_id, to_status="approved")
        .one()
    )
    assert decision.changed_by == coordinator.id
    notification = (
        db_session.query(Notification)
        .filter_by(event_id=event_id, type="event_approved")
        .one()
    )
    assert notification.user_id == organiser.id
    assert "has been approved" in notification.message


def test_coordinator_can_reject_with_recorded_reason_and_notify_organiser(client, db_session):
    organiser, organiser_headers, _, coordinator_headers, event_id = _review_setup(client, db_session)
    reason = "The requested venue is unavailable on that date."

    response = client.post(
        f"/events/{event_id}/reject", json={"reason": reason}, headers=coordinator_headers
    )

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    decision = (
        db_session.query(EventStatusHistory)
        .filter_by(event_id=event_id, to_status="rejected")
        .one()
    )
    assert decision.note == reason
    notification = (
        db_session.query(Notification)
        .filter_by(event_id=event_id, type="event_rejected")
        .one()
    )
    assert notification.user_id == organiser.id
    assert reason in notification.message

    activity = client.get(f"/events/{event_id}/activity", headers=organiser_headers)
    assert activity.status_code == 200
    rejection = next(entry for entry in activity.json() if entry["to_status"] == "rejected")
    assert rejection["note"] == reason
    assert rejection["changed_by_name"] == "Coordinator"


def test_rejection_requires_a_non_blank_reason(client, db_session):
    _, _, _, coordinator_headers, event_id = _review_setup(client, db_session)

    response = client.post(
        f"/events/{event_id}/reject", json={"reason": "   "}, headers=coordinator_headers
    )

    assert response.status_code == 422
    assert db_session.get(Event, event_id).status == "under_review"


def test_only_the_assigned_coordinator_can_decide(client, db_session):
    _, _, _, _, event_id = _review_setup(client, db_session)
    _, other_headers = _user(
        client, db_session, Role.COORDINATOR, "other-coordinator@example.com", "Other Coordinator"
    )

    response = client.post(f"/events/{event_id}/approve", headers=other_headers)

    assert response.status_code == 404
    assert db_session.get(Event, event_id).status == "under_review"


def test_organiser_cannot_read_another_organisers_event_activity(client, db_session):
    _, _, _, _, event_id = _review_setup(client, db_session)
    _, other_headers = _user(
        client, db_session, Role.ORGANISER, "other-organiser@example.com", "Other Organiser"
    )

    response = client.get(f"/events/{event_id}/activity", headers=other_headers)

    assert response.status_code == 404


def test_non_coordinator_cannot_approve(client, db_session):
    _, organiser_headers, _, _, event_id = _review_setup(client, db_session)

    response = client.post(f"/events/{event_id}/approve", headers=organiser_headers)

    assert response.status_code == 403
    assert db_session.get(Event, event_id).status == "under_review"


def test_organiser_can_correct_request_before_decision_and_it_is_logged(client, db_session):
    _, organiser_headers, coordinator, _, event_id = _review_setup(client, db_session)

    response = client.patch(
        f"/events/{event_id}", json={"name": "Corrected conference name"}, headers=organiser_headers
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Corrected conference name"
    assert response.json()["status"] == "under_review"
    correction = (
        db_session.query(EventStatusHistory)
        .filter_by(event_id=event_id, from_status="under_review", to_status="under_review")
        .one()
    )
    assert correction.changed_by != coordinator.id
    assert correction.note == "Updated by the Organiser before review was decided."


def test_decided_request_cannot_be_edited(client, db_session):
    _, organiser_headers, _, coordinator_headers, event_id = _review_setup(client, db_session)
    assert client.post(f"/events/{event_id}/approve", headers=coordinator_headers).status_code == 200

    response = client.patch(
        f"/events/{event_id}", json={"name": "Changed after approval"}, headers=organiser_headers
    )

    assert response.status_code == 409
    assert db_session.get(Event, event_id).name == COMPLETE["name"]