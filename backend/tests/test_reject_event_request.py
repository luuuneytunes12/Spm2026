"""Unit tests for rejecting an event request with a recorded reason."""

import pytest

from app.core.roles import Role
from app.models.events import Event, EventStatusHistory
from app.models.notifications import Notification
from event_review_test_helpers import review_setup, user


def test_rejection_requires_a_non_blank_reason(client, db_session):
    _, _, _, coordinator_headers, event_id = review_setup(client, db_session)

    response = client.post(
        f"/events/{event_id}/reject", json={"reason": "   "}, headers=coordinator_headers
    )

    assert response.status_code == 422
    assert db_session.get(Event, event_id).status == "under_review"


def test_rejection_records_reason_notifies_organiser_and_logs_coordinator(
    client, db_session
):
    organiser, organiser_headers, coordinator, coordinator_headers, event_id = review_setup(
        client, db_session
    )
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
    assert decision.changed_by == coordinator.id
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


def test_only_the_assigned_coordinator_can_reject(client, db_session):
    _, _, _, _, event_id = review_setup(client, db_session)
    _, other_headers = user(
        client,
        db_session,
        Role.COORDINATOR,
        "other-coordinator@example.com",
        "Other Coordinator",
    )

    response = client.post(
        f"/events/{event_id}/reject", json={"reason": "Unavailable."}, headers=other_headers
    )

    assert response.status_code == 404
    assert db_session.get(Event, event_id).status == "under_review"


def test_organiser_cannot_read_another_organisers_rejection_activity(client, db_session):
    _, _, _, _, event_id = review_setup(client, db_session)
    _, other_headers = user(
        client, db_session, Role.ORGANISER, "other-organiser@example.com", "Other Organiser"
    )

    response = client.get(f"/events/{event_id}/activity", headers=other_headers)

    assert response.status_code == 404