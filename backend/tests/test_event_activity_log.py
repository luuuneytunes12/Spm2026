"""US1 - View Event Status Activity Log.

Each test is named after the acceptance criterion it proves:

  AC1  each status change shows who performed it and the system timestamp
  AC2  a clarification message or Event Coordinator note shows with author and time
  AC3  an entry cannot be changed or removed by anyone
  AC4  the log shows the Event's current status
  AC5  status change, (re)assignment, Tentative Hold expiry, venue
       unavailability flag and Safety Check outcome each show what, who and when
  AC6  refused unless the Lead or the assigned Coordinator (the Organiser
       may still read their own Event's log)
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Depends
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.error_handlers import _database_error_response
from app.core.roles import Role
from app.domain.errors import ImmutableRecord
from app.main import app
from app.models.enums import BookingStatus, EventStatus
from app.models.events import ACTIVITY_LOG_IMMUTABLE_MESSAGE, Event, EventStatusHistory
from app.models.user import User
from app.models.venues import Venue, VenueBooking
from app.services.venue_holds import expire_tentative_holds
from event_review_test_helpers import submitted_event


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


def _entry(db_session, event, actor, note="Submitted."):
    entry = EventStatusHistory(
        event_id=event.id,
        changed_by=actor.id,
        from_status=EventStatus.draft,
        to_status=EventStatus.submitted_awaiting_coordinator,
        note=note,
    )
    db_session.add(entry)
    db_session.commit()
    return entry


# --- AC1 / AC6: who may read the log -------------------------------------------


def test_ac1_ac6_activity_log_is_shared_with_assigned_coordinator_and_lead(
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


@pytest.mark.parametrize(
    "role",
    [Role.COORDINATOR, Role.ORGANISER, Role.ATTENDEE, Role.VENUE_STAFF, Role.TECH_SUPPORT],
)
def test_ac6_activity_log_is_refused_to_anyone_not_involved_in_the_event(
    client, db_session, role
):
    organiser, _ = _user(
        client, db_session, Role.ORGANISER, "owner@ac6.test", "Owner"
    )
    coordinator, _ = _user(
        client, db_session, Role.COORDINATOR, "assigned@ac6.test", "Assigned"
    )
    _, outsider_headers = _user(
        client, db_session, role, f"outsider-{role.value}@ac6.test", "Outsider"
    )
    event = _event(db_session, organiser, coordinator)
    _entry(db_session, event, organiser, note="Private history.")

    response = client.get(f"/events/{event.id}/activity", headers=outsider_headers)

    # 404, not 403: "not yours" and "does not exist" look the same, and no
    # entry leaks in the body.
    assert response.status_code == 404
    assert response.json() == {"detail": "Event not found"}
    assert "Private history." not in response.text


def test_ac6_activity_log_of_an_event_that_does_not_exist_is_not_found(client, db_session):
    _, lead_headers = _user(
        client, db_session, Role.COORDINATOR_LEAD, "lead@missing.test", "Lead"
    )

    response = client.get("/events/999999/activity", headers=lead_headers)

    assert response.status_code == 404
    assert response.json() == {"detail": "Event not found"}


def test_ac6_activity_log_needs_a_signed_in_user(client, db_session):
    organiser, _ = _user(
        client, db_session, Role.ORGANISER, "owner@anon.test", "Owner"
    )
    event = _event(db_session, organiser)

    assert client.get(f"/events/{event.id}/activity").status_code == 401


def test_ac6_a_reassigned_away_coordinator_can_no_longer_read_the_log(client, db_session):
    organiser, _ = _user(
        client, db_session, Role.ORGANISER, "owner@moved.test", "Owner"
    )
    first, first_headers = _user(
        client, db_session, Role.COORDINATOR, "first@moved.test", "First"
    )
    second, _ = _user(
        client, db_session, Role.COORDINATOR, "second@moved.test", "Second"
    )
    event = _event(db_session, organiser, first)
    assert client.get(f"/events/{event.id}/activity", headers=first_headers).status_code == 200

    event.coordinator_id = second.id
    db_session.commit()

    assert client.get(f"/events/{event.id}/activity", headers=first_headers).status_code == 404


# --- AC4: the current status -----------------------------------------------------


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
    assert response.json()["status"] == EventStatus.submitted_awaiting_coordinator


def test_ac4_assigned_coordinator_sees_the_current_status_with_the_log(client, db_session):
    organiser, _ = _user(
        client, db_session, Role.ORGANISER, "owner@status.test", "Owner"
    )
    coordinator, coordinator_headers = _user(
        client, db_session, Role.COORDINATOR, "coordinator@status.test", "Coordinator"
    )
    event = _event(db_session, organiser, coordinator, status=EventStatus.planning_event)
    _entry(db_session, event, organiser)

    response = client.get(f"/events/assigned/{event.id}", headers=coordinator_headers)

    assert response.status_code == 200
    assert response.json()["status"] == EventStatus.planning_event
    assert len(response.json()["activity"]) == 1


# --- AC2: clarification message and Coordinator note ------------------------------


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


def test_ac2_a_decision_without_a_note_adds_no_empty_note_entry(client, db_session):
    organiser, organiser_headers = _user(
        client, db_session, Role.ORGANISER, "owner@nonote.test", "Owner"
    )
    coordinator, coordinator_headers = _user(
        client, db_session, Role.COORDINATOR, "coordinator@nonote.test", "Coordinator"
    )
    event = _event(db_session, organiser, coordinator)
    request_id = client.post(
        f"/events/{event.id}/change-requests",
        json={"description": "Small fix.", "proposed_changes": {"purpose": "Fixed"}},
        headers=organiser_headers,
    ).json()["id"]

    assert client.post(
        f"/events/change-requests/{request_id}/reject",
        json={"review_notes": "   "},
        headers=coordinator_headers,
    ).status_code == 200

    notes = [e["note"] for e in client.get(f"/events/{event.id}/activity", headers=organiser_headers).json()]
    assert not any(note.startswith("Event Coordinator note:") for note in notes)


# --- AC3: entries cannot be changed or removed -----------------------------------


def test_ac3_event_activity_log_rows_cannot_be_updated_or_deleted(client, db_session):
    organiser, _ = _user(
        client, db_session, Role.ORGANISER, "immutable@activity.test", "Immutable Owner"
    )
    event = _event(db_session, organiser)
    entry = _entry(db_session, event, organiser)

    entry.note = "Changed."
    with pytest.raises(ImmutableRecord, match="cannot be changed or removed"):
        db_session.flush()
    db_session.rollback()

    entry = db_session.query(EventStatusHistory).filter_by(event_id=event.id).one()
    db_session.delete(entry)
    with pytest.raises(ImmutableRecord, match="cannot be changed or removed"):
        db_session.flush()
    db_session.rollback()

    assert db_session.query(EventStatusHistory).filter_by(event_id=event.id).one().note == "Submitted."


@pytest.fixture()
def tampering_routes():
    """Two throwaway endpoints that try to edit or delete a log entry, to show
    what a caller would get if any code path ever did."""

    def _edit(entry_id: int, db: Session = Depends(get_db)) -> None:
        db.get(EventStatusHistory, entry_id).note = "Tampered."
        db.commit()

    def _delete(entry_id: int, db: Session = Depends(get_db)) -> None:
        db.delete(db.get(EventStatusHistory, entry_id))
        db.commit()

    before = len(app.router.routes)
    app.add_api_route("/__test__/activity/{entry_id}", _edit, methods=["PATCH"])
    app.add_api_route("/__test__/activity/{entry_id}", _delete, methods=["DELETE"])
    yield
    del app.router.routes[before:]


@pytest.mark.parametrize("method", ["PATCH", "DELETE"])
def test_ac3_an_attempt_through_the_api_is_a_readable_409_not_a_crash(
    client, db_session, tampering_routes, method
):
    organiser, _ = _user(
        client, db_session, Role.ORGANISER, f"tamper-{method.lower()}@activity.test", "Owner"
    )
    event = _event(db_session, organiser)
    entry = _entry(db_session, event, organiser)

    response = client.request(method, f"/__test__/activity/{entry.id}")

    assert response.status_code == 409
    assert response.json() == {"detail": ACTIVITY_LOG_IMMUTABLE_MESSAGE}
    db_session.rollback()
    assert db_session.get(EventStatusHistory, entry.id).note == "Submitted."


def test_ac3_the_database_refusal_is_reported_with_the_same_readable_message():
    refusal = DBAPIError("update event_status_history", {}, Exception(
        "Event activity log entries are immutable"
    ))

    response = asyncio.run(_database_error_response(None, refusal))

    assert response.status_code == 409
    assert json.loads(response.body) == {"detail": ACTIVITY_LOG_IMMUTABLE_MESSAGE}


def test_ac3_frozen_literal_other_database_errors_are_not_disguised():
    other = DBAPIError("insert into events", {}, Exception("connection reset"))

    with pytest.raises(DBAPIError, match="connection reset"):
        asyncio.run(_database_error_response(None, other))


# --- AC1 / AC5: each kind of entry shows what, who and when ----------------------


def test_ac1_ac5_each_kind_of_event_shows_what_happened_who_and_when(client, db_session):
    _, organiser_headers = _user(
        client, db_session, Role.ORGANISER, "owner@ac5.test", "Olive Organiser"
    )
    _, lead_headers = _user(
        client, db_session, Role.COORDINATOR_LEAD, "lead@ac5.test", "Lena Lead"
    )
    first, _ = _user(
        client, db_session, Role.COORDINATOR, "first@ac5.test", "First Coordinator"
    )
    second, second_headers = _user(
        client, db_session, Role.COORDINATOR, "second@ac5.test", "Second Coordinator"
    )
    staff, staff_headers = _user(
        client, db_session, Role.VENUE_STAFF, "staff@ac5.test", "Vera Staff"
    )
    _, officer_headers = _user(
        client, db_session, Role.SAFETY_OFFICER, "officer@ac5.test", "Sam Safety"
    )
    event_id = submitted_event(client, organiser_headers)

    # assignment and reassignment, through the Lead's own endpoints
    assert client.post(
        f"/lead/unassigned-queue/{event_id}/assign",
        json={"coordinator_id": first.id},
        headers=lead_headers,
    ).status_code == 200
    assert client.post(
        f"/lead/assignments/{event_id}/reassign",
        json={"coordinator_id": second.id},
        headers=lead_headers,
    ).status_code == 200

    # planning, with an approved booking and a hold that has lapsed
    start = datetime(2099, 3, 1, 9, tzinfo=timezone.utc)
    end = start + timedelta(hours=8)
    event = db_session.get(Event, event_id)
    event.status = EventStatus.planning_event
    event.proposed_start, event.proposed_end = start, end
    hall = Venue(name="Riverside Hall", location="Block A", capacity=500)
    room = Venue(name="Garden Room", location="Block B", capacity=500)
    db_session.add_all([hall, room])
    db_session.flush()
    db_session.add_all([
        VenueBooking(
            event_id=event_id, venue_id=hall.id, requested_by=second.id,
            start_time=start, end_time=end, status=BookingStatus.approved,
            reviewed_by=staff.id, reviewed_at=datetime.now(timezone.utc),
        ),
        VenueBooking(
            event_id=event_id, venue_id=room.id, requested_by=second.id,
            start_time=start, end_time=end, status=BookingStatus.tentative_hold,
            expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        ),
    ])
    db_session.commit()

    # Tentative Hold expiry, by the system
    assert expire_tentative_holds(db_session) == 1

    # venue unavailability flag, by Venue Staff
    assert client.post(
        f"/venues/{hall.id}/unavailability",
        json={
            "start_time": (start - timedelta(hours=1)).isoformat(),
            "end_time": (end + timedelta(hours=1)).isoformat(),
            "reason_category": "Maintenance",
        },
        headers=staff_headers,
    ).status_code == 201

    # Safety Check outcome, by the Safety Officer
    event = db_session.get(Event, event_id)
    event.status = EventStatus.awaiting_safety_check
    db_session.commit()
    assert client.post(
        f"/safety-checks/{event_id}/reject",
        json={"reason": "Fire exits blocked."},
        headers=officer_headers,
    ).status_code == 200

    entries = client.get(f"/events/{event_id}/activity", headers=second_headers).json()

    def find(note_part):
        matches = [e for e in entries if note_part in (e["note"] or "")]
        assert matches, f"no Activity Log entry mentions {note_part!r}: {entries}"
        return matches[0]

    expected = {
        "Assigned to First Coordinator": "Lena Lead",
        "Reassigned from First Coordinator to Second Coordinator": "Lena Lead",
        "Tentative hold on 'Garden Room' expired.": "System",
        "Venue booking 'Riverside Hall' flagged": "Vera Staff",
        "Safety arrangement rejected: Fire exits blocked.": "Sam Safety",
    }
    for note_part, actor in expected.items():
        entry = find(note_part)
        assert entry["changed_by_name"] == actor, note_part
        assert entry["created_at"], note_part

    safety = find("Safety arrangement rejected")
    assert safety["from_status"] == EventStatus.awaiting_safety_check
    assert safety["to_status"] == EventStatus.planning_event
    submitted = next(e for e in entries if e["to_status"] == EventStatus.submitted_awaiting_coordinator)
    assert submitted["from_status"] == EventStatus.draft
    assert submitted["changed_by_name"] == "Olive Organiser"
