"""US4 - Mark Event as Completed.

Each test is named after the acceptance criterion it proves:

  AC1  a Confirmed Event whose end has passed becomes 'Event Completed'
  AC2  refused, Event unchanged, before its end or when not Confirmed
  AC3  refused, Event unchanged, for anyone but the assigned Coordinator
  AC4  an 'Event Completed' Event refuses every further status change
  AC5  the change is in the Activity Log with the author's name and the time
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.roles import Role
from app.models.enums import ChangeRequestStatus, EventStatus
from app.models.events import Event, EventChangeRequest, EventStatusHistory
from event_review_test_helpers import review_setup, user


def _set_confirmed_event_end(db_session, event_id, end_time):
    event = db_session.get(Event, event_id)
    event.status = EventStatus.safety_check_passed
    event.proposed_end = end_time
    db_session.commit()
    return event


def _completions(db_session, event_id):
    return (
        db_session.query(EventStatusHistory)
        .filter_by(event_id=event_id, to_status=EventStatus.event_completed)
        .count()
    )


def test_ac1_ac5_assigned_coordinator_completes_ended_confirmed_event_and_logs_activity(
    client, db_session
):
    organiser, organiser_headers, coordinator, coordinator_headers, event_id = review_setup(
        client, db_session
    )
    event = _set_confirmed_event_end(
        db_session, event_id, datetime(2020, 1, 1, 12, tzinfo=timezone.utc)
    )

    response = client.post(
        f"/events/{event_id}/complete", headers=coordinator_headers
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == EventStatus.event_completed
    history = (
        db_session.query(EventStatusHistory)
        .filter_by(event_id=event_id, to_status=EventStatus.event_completed)
        .one()
    )
    assert history.from_status == EventStatus.safety_check_passed
    assert history.changed_by == coordinator.id
    assert history.changed_by_user.name == coordinator.name
    assert history.created_at is not None

    activity = client.get(
        f"/events/{event_id}/activity", headers=organiser_headers
    )
    assert activity.status_code == 200
    completed_entry = next(
        row
        for row in activity.json()
        if row["to_status"] == EventStatus.event_completed
    )
    assert completed_entry["from_status"] == EventStatus.safety_check_passed
    assert completed_entry["changed_by_name"] == coordinator.name
    assert completed_entry["created_at"]

    repeated = client.post(
        f"/events/{event_id}/complete", headers=coordinator_headers
    )
    assert repeated.status_code == 409
    assert db_session.get(Event, event_id).status == EventStatus.event_completed
    assert _completions(db_session, event_id) == 1


@pytest.mark.parametrize(
    ("event_status", "end_time", "message"),
    [
        (
            EventStatus.safety_check_passed,
            datetime(2099, 1, 1, tzinfo=timezone.utc),
            "An event cannot be marked completed before its scheduled end time has passed.",
        ),
        (
            EventStatus.safety_check_passed,
            datetime.now(timezone.utc) + timedelta(minutes=5),
            "An event cannot be marked completed before its scheduled end time has passed.",
        ),
        (
            EventStatus.planning_event,
            datetime(2020, 1, 1, tzinfo=timezone.utc),
            "this event is 'Planning Event'.",
        ),
        (
            EventStatus.awaiting_safety_check,
            datetime(2020, 1, 1, tzinfo=timezone.utc),
            "this event is 'Awaiting Safety Check'.",
        ),
        (
            EventStatus.under_review,
            datetime(2020, 1, 1, tzinfo=timezone.utc),
            "this event is 'Under Review'.",
        ),
        (
            EventStatus.event_cancelled,
            datetime(2020, 1, 1, tzinfo=timezone.utc),
            "this event is 'Event Cancelled'.",
        ),
        (
            EventStatus.event_completed,
            datetime(2020, 1, 1, tzinfo=timezone.utc),
            "this event is 'Event Completed'.",
        ),
    ],
    ids=[
        "end-far-ahead",
        "end-minutes-ahead",
        "planning",
        "awaiting-safety-check",
        "under-review",
        "cancelled",
        "completed",
    ],
)
def test_ac2_completion_is_refused_before_end_or_from_an_invalid_status(
    client, db_session, event_status, end_time, message
):
    _, _, _, coordinator_headers, event_id = review_setup(client, db_session)
    event = db_session.get(Event, event_id)
    event.status = event_status
    event.proposed_end = end_time
    db_session.commit()

    response = client.post(
        f"/events/{event_id}/complete", headers=coordinator_headers
    )

    assert response.status_code == 409
    assert message in response.json()["detail"]
    db_session.refresh(event)
    assert event.status == event_status
    assert _completions(db_session, event_id) == 0


def test_ac3_only_the_assigned_coordinator_can_complete_an_event(client, db_session):
    _, _, _, _, event_id = review_setup(client, db_session)
    _set_confirmed_event_end(
        db_session, event_id, datetime(2020, 1, 1, tzinfo=timezone.utc)
    )
    _, other_headers = user(
        client,
        db_session,
        Role.COORDINATOR,
        "not-assigned-completion@example.com",
        "Other Coordinator",
    )

    response = client.post(
        f"/events/{event_id}/complete", headers=other_headers
    )

    assert response.status_code == 404
    assert db_session.get(Event, event_id).status == EventStatus.safety_check_passed
    assert _completions(db_session, event_id) == 0


@pytest.mark.parametrize(
    "role", [Role.COORDINATOR_LEAD, Role.ORGANISER, Role.SAFETY_OFFICER, Role.VENUE_STAFF]
)
def test_ac3_other_roles_cannot_complete_an_event(client, db_session, role):
    _, organiser_headers, _, _, event_id = review_setup(client, db_session)
    _set_confirmed_event_end(
        db_session, event_id, datetime(2020, 1, 1, tzinfo=timezone.utc)
    )
    if role is Role.ORGANISER:
        headers = organiser_headers
    else:
        _, headers = user(client, db_session, role, f"{role.value}-complete@example.com", "Other")

    response = client.post(f"/events/{event_id}/complete", headers=headers)

    assert response.status_code == 403
    assert db_session.get(Event, event_id).status == EventStatus.safety_check_passed
    assert _completions(db_session, event_id) == 0


def test_ac3_completion_needs_a_signed_in_user(client, db_session):
    _, _, _, _, event_id = review_setup(client, db_session)
    _set_confirmed_event_end(
        db_session, event_id, datetime(2020, 1, 1, tzinfo=timezone.utc)
    )

    assert client.post(f"/events/{event_id}/complete").status_code == 401
    assert db_session.get(Event, event_id).status == EventStatus.safety_check_passed


def test_ac4_a_completed_event_refuses_every_further_status_change(client, db_session):
    organiser, organiser_headers, coordinator, coordinator_headers, event_id = review_setup(
        client, db_session
    )
    _, lead_headers = user(
        client, db_session, Role.COORDINATOR_LEAD, "lead-complete@example.com", "Lead"
    )
    other, _ = user(client, db_session, Role.COORDINATOR, "spare@example.com", "Spare")
    _, officer_headers = user(
        client, db_session, Role.SAFETY_OFFICER, "officer-complete@example.com", "Officer"
    )
    _set_confirmed_event_end(
        db_session, event_id, datetime(2020, 1, 1, tzinfo=timezone.utc)
    )
    assert client.post(
        f"/events/{event_id}/complete", headers=coordinator_headers
    ).status_code == 200
    # left over from before completion; it must not be approvable now
    pending = EventChangeRequest(
        event_id=event_id,
        requested_by=organiser.id,
        description="Late change.",
        proposed_changes={"expected_attendance": 10},
    )
    db_session.add(pending)
    db_session.commit()
    entries_before = db_session.query(EventStatusHistory).filter_by(event_id=event_id).count()

    attempts = {
        "complete again": client.post(f"/events/{event_id}/complete", headers=coordinator_headers),
        "cancel": client.post(
            f"/events/{event_id}/cancel", headers=coordinator_headers, json={"reason": "Too late"}
        ),
        "submit for safety check": client.post(
            f"/events/{event_id}/confirm", headers=coordinator_headers
        ),
        "approve request": client.post(f"/events/{event_id}/approve", headers=coordinator_headers),
        "reject request": client.post(
            f"/events/{event_id}/reject", headers=coordinator_headers, json={"reason": "No"}
        ),
        "planning edit": client.patch(
            f"/events/assigned/{event_id}/planning",
            headers=coordinator_headers,
            json={"expected_attendance": 10},
        ),
        "approve change request": client.post(
            f"/events/change-requests/{pending.id}/approve", headers=coordinator_headers, json={}
        ),
        "new change request": client.post(
            f"/events/{event_id}/change-requests",
            headers=organiser_headers,
            json={"description": "More", "proposed_changes": {"expected_attendance": 5}},
        ),
        "safety check pass": client.post(
            f"/safety-checks/{event_id}/approve", headers=officer_headers
        ),
        "lead reassign": client.post(
            f"/lead/assignments/{event_id}/reassign",
            headers=lead_headers,
            json={"coordinator_id": other.id},
        ),
    }

    for action, response in attempts.items():
        assert response.status_code == 409, f"{action}: {response.status_code} {response.text}"
        assert isinstance(response.json()["detail"], str) and response.json()["detail"], action
    db_session.expire_all()
    event = db_session.get(Event, event_id)
    assert event.status == EventStatus.event_completed
    assert event.coordinator_id == coordinator.id
    assert event.expected_attendance != 10
    assert db_session.get(EventChangeRequest, pending.id).status == ChangeRequestStatus.pending
    assert (
        db_session.query(EventStatusHistory).filter_by(event_id=event_id).count()
        == entries_before
    )
