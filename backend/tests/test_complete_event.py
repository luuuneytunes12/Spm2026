from datetime import datetime, timezone

import pytest

from app.core.roles import Role
from app.models.enums import EventStatus
from app.models.events import Event, EventStatusHistory
from event_review_test_helpers import review_setup, user


def _set_confirmed_event_end(db_session, event_id, end_time):
    event = db_session.get(Event, event_id)
    event.status = EventStatus.safety_check_passed
    event.proposed_end = end_time
    db_session.commit()
    return event


def test_assigned_coordinator_completes_ended_confirmed_event_and_logs_activity(
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
    assert (
        db_session.query(EventStatusHistory)
        .filter_by(event_id=event_id, to_status=EventStatus.event_completed)
        .count()
        == 1
    )


@pytest.mark.parametrize(
    ("event_status", "end_time"),
    [
        (
            EventStatus.safety_check_passed,
            datetime(2099, 1, 1, tzinfo=timezone.utc),
        ),
        (
            EventStatus.planning_event,
            datetime(2020, 1, 1, tzinfo=timezone.utc),
        ),
        (
            EventStatus.event_completed,
            datetime(2020, 1, 1, tzinfo=timezone.utc),
        ),
    ],
)
def test_completion_is_refused_before_end_or_from_an_invalid_status(
    client, db_session, event_status, end_time
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
    db_session.refresh(event)
    assert event.status == event_status
    assert (
        db_session.query(EventStatusHistory)
        .filter_by(event_id=event_id, to_status=EventStatus.event_completed)
        .count()
        == 0
    )


def test_only_the_assigned_coordinator_can_complete_an_event(client, db_session):
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
