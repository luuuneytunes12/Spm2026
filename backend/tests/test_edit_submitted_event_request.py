"""Unit tests for editing a submitted event request before review is decided."""

import pytest

from app.core.roles import Role
from app.models.enums import EventStatus
from app.models.events import Event, EventStatusHistory
from event_review_test_helpers import COMPLETE, review_setup, submitted_event, user


def test_organiser_can_correct_submitted_request_and_status_stays_submitted(client, db_session):
    _, organiser_headers = user(
        client, db_session, Role.ORGANISER, "organiser@example.com", "Organiser"
    )
    event_id = submitted_event(client, organiser_headers)

    response = client.patch(
        f"/events/{event_id}", json={"name": "Corrected conference name"}, headers=organiser_headers
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Corrected conference name"
    assert response.json()["status"] == "submitted"


def test_organiser_can_correct_request_under_review_and_it_is_logged(client, db_session):
    _, organiser_headers, coordinator, _, event_id = review_setup(client, db_session)

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


@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_decided_request_cannot_be_edited(client, db_session, decision):
    _, organiser_headers, _, coordinator_headers, event_id = review_setup(client, db_session)
    payload = {"reason": "The requested venue is unavailable."} if decision == "reject" else None
    assert (
        client.post(f"/events/{event_id}/{decision}", json=payload, headers=coordinator_headers).status_code
        == 200
    )

    response = client.patch(
        f"/events/{event_id}", json={"name": "Changed after decision"}, headers=organiser_headers
    )

    assert response.status_code == 409
    assert db_session.get(Event, event_id).name == COMPLETE["name"]
    expected_status = EventStatus.approved if decision == "approve" else EventStatus.rejected
    assert db_session.get(Event, event_id).status == expected_status