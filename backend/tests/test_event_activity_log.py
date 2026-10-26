import pytest

from app.core.roles import Role
from app.models.enums import EventStatus
from app.models.events import Event, EventStatusHistory
from app.models.user import User


def _user(client, db_session, role, email, name):
    password = "password123"
    assert client.post(
        "/auth/register", json={"name": name, "email": email, "password": password}
    ).status_code == 201
    user = db_session.query(User).filter_by(email=email).one()
    user.role = role.value
    db_session.commit()
    token = client.post(
        "/auth/login", json={"email": email, "password": password}
    ).json()["access_token"]
    return user, {"Authorization": f"Bearer {token}"}


def _event(db_session, organiser, coordinator=None, status=EventStatus.under_review):
    event = Event(
        organiser_id=organiser.id,
        coordinator_id=coordinator.id if coordinator else None,
        name="Activity Log Event",
        status=status,
    )
    db_session.add(event)
    db_session.commit()
    return event


def test_ac1_ac4_activity_log_is_shared_with_assigned_coordinator_and_lead(
    client, db_session
):
    organiser, organiser_headers = _user(
        client, db_session, Role.ORGANISER, "organiser@activity.test", "Organiser"
    )
    coordinator, coordinator_headers = _user(
        client, db_session, Role.COORDINATOR, "coordinator@activity.test", "Coordinator"
    )
    lead, lead_headers = _user(
        client, db_session, Role.COORDINATOR_LEAD, "lead@activity.test", "Lead"
    )
    _, other_coordinator_headers = _user(
        client,
        db_session,
        Role.COORDINATOR,
        "other-coordinator@activity.test",
        "Other Coordinator",
    )
    event = _event(db_session, organiser, coordinator)
    db_session.add(
        EventStatusHistory(
            event_id=event.id,
            changed_by=organiser.id,
            from_status=EventStatus.submitted_awaiting_coordinator,
            to_status=EventStatus.under_review,
            note="Assigned for review.",
        )
    )
    db_session.commit()

    organiser_log = client.get(
        f"/events/{event.id}/activity", headers=organiser_headers
    )
    coordinator_log = client.get(
        f"/events/{event.id}/activity", headers=coordinator_headers
    )
    lead_log = client.get(f"/events/{event.id}/activity", headers=lead_headers)

    assert organiser_log.status_code == coordinator_log.status_code == lead_log.status_code == 200
    assert organiser_log.json() == coordinator_log.json() == lead_log.json()
    assert lead_log.json()[0]["changed_by_name"] == "Organiser"
    assert lead_log.json()[0]["created_at"] is not None
    assert client.get(
        f"/events/{event.id}/activity", headers=other_coordinator_headers
    ).status_code == 404


def test_ac4_coordinator_lead_event_detail_includes_activity(client, db_session):
    organiser, _ = _user(
        client, db_session, Role.ORGANISER, "queue-owner@activity.test", "Queue Owner"
    )
    lead, lead_headers = _user(
        client, db_session, Role.COORDINATOR_LEAD, "queue-lead@activity.test", "Queue Lead"
    )
    event = _event(
        db_session,
        organiser,
        status=EventStatus.submitted_awaiting_coordinator,
    )
    db_session.add(
        EventStatusHistory(
            event_id=event.id,
            changed_by=organiser.id,
            from_status=EventStatus.draft,
            to_status=EventStatus.submitted_awaiting_coordinator,
            note="Submitted by organiser.",
        )
    )
    db_session.commit()

    response = client.get(
        f"/lead/unassigned-queue/{event.id}", headers=lead_headers
    )

    assert response.status_code == 200
    assert response.json()["activity"][0]["changed_by_name"] == "Queue Owner"


def test_ac2_saved_clarification_and_coordinator_note_are_activity_entries(
    client, db_session
):
    organiser, organiser_headers = _user(
        client, db_session, Role.ORGANISER, "message-owner@activity.test", "Message Owner"
    )
    coordinator, coordinator_headers = _user(
        client,
        db_session,
        Role.COORDINATOR,
        "message-coordinator@activity.test",
        "Message Coordinator",
    )
    event = _event(db_session, organiser, coordinator)

    request_response = client.post(
        f"/events/{event.id}/change-requests",
        json={
            "description": "Please clarify the access arrangements.",
            "proposed_changes": {"purpose": "Clarified purpose"},
        },
        headers=organiser_headers,
    )
    assert request_response.status_code == 201, request_response.text
    request_id = request_response.json()["id"]
    decision = client.post(
        f"/events/change-requests/{request_id}/approve",
        json={"review_notes": "Access arrangements reviewed and accepted."},
        headers=coordinator_headers,
    )
    assert decision.status_code == 200, decision.text

    entries = client.get(
        f"/events/{event.id}/activity", headers=organiser_headers
    ).json()
    messages = {entry["note"]: entry for entry in entries}

    clarification = messages["Clarification message: Please clarify the access arrangements."]
    coordinator_note = messages[
        "Event Coordinator note: Access arrangements reviewed and accepted."
    ]
    assert clarification["changed_by_name"] == "Message Owner"
    assert coordinator_note["changed_by_name"] == "Message Coordinator"
    assert clarification["created_at"] is not None
    assert coordinator_note["created_at"] is not None

def test_ac3_event_activity_log_rows_cannot_be_updated_or_deleted(client, db_session):
    organiser, _ = _user(
        client, db_session, Role.ORGANISER, "immutable@activity.test", "Immutable Owner"
    )
    event = _event(db_session, organiser)
    entry = EventStatusHistory(
        event_id=event.id,
        changed_by=organiser.id,
        from_status=EventStatus.draft,
        to_status=EventStatus.submitted_awaiting_coordinator,
        note="Submitted.",
    )
    db_session.add(entry)
    db_session.commit()

    entry.note = "Changed."
    with pytest.raises(ValueError, match="immutable"):
        db_session.flush()
    db_session.rollback()

    entry = db_session.query(EventStatusHistory).filter_by(event_id=event.id).one()
    db_session.delete(entry)
    with pytest.raises(ValueError, match="immutable"):
        db_session.flush()
    db_session.rollback()
