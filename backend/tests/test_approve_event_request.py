"""SCRUM-25: API-level tests for approving an event request.

Positive: the assigned coordinator approves and the organiser is notified.
Negative: other statuses, an unassigned event and unauthorised users fail
without changing the event. The test client uses an isolated test database;
this suite does not prove that the browser hides or disables the action.

Jira describes approval from Submitted; the current workflow first assigns
the event and changes it to Under Review. The tests describe the implemented
workflow, so the product owner should resolve that wording discrepancy.
"""

import pytest

from app.core.roles import Role
from app.models.enums import EventStatus
from app.models.events import Event, EventStatusHistory
from app.models.notifications import Notification
from event_review_test_helpers import review_setup, user

# These tests start from an event that already has a Coordinator; assignment is
# now the Lead's job, so submit alone no longer provides one (see conftest).
pytestmark = pytest.mark.usefixtures("coordinator_auto_assign")


def test_coordinator_can_approve_assigned_request_and_notify_organiser(client, db_session):
    """SCRUM-25 AC01/AC04: approval records the actor and notifies the owner."""
    organiser, _, coordinator, coordinator_headers, event_id = review_setup(client, db_session)
    event = db_session.get(Event, event_id)
    event.status = EventStatus.under_review
    db_session.commit()

    response = client.post(f"/events/{event_id}/approve", headers=coordinator_headers)

    assert response.status_code == 200
    assert response.json()["status"] == "event_approved"
    decision = (
        db_session.query(EventStatusHistory)
        .filter_by(event_id=event_id, to_status="event_approved")
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


@pytest.mark.parametrize(
    "status",
    [
        "draft",
        "submitted_awaiting_coordinator",
        "event_approved",
        "event_rejected",
        "event_cancelled",
    ],
)
def test_request_outside_reviewable_status_cannot_be_approved(client, db_session, status):
    """SCRUM-25 AC03: reject each listed invalid state without changing it."""
    _, _, _, coordinator_headers, event_id = review_setup(client, db_session)
    event = db_session.get(Event, event_id)
    event.status = EventStatus(status)
    db_session.commit()

    response = client.post(f"/events/{event_id}/approve", headers=coordinator_headers)

    assert response.status_code == 409
    assert db_session.get(Event, event_id).status == EventStatus(status)


def test_only_the_assigned_coordinator_can_approve(client, db_session):
    """A different coordinator cannot approve someone else's assigned event."""
    _, _, _, _, event_id = review_setup(client, db_session)
    _, other_headers = user(
        client,
        db_session,
        Role.COORDINATOR,
        "other-coordinator@example.com",
        "Other Coordinator",
    )

    response = client.post(f"/events/{event_id}/approve", headers=other_headers)

    assert response.status_code == 403
    assert db_session.get(Event, event_id).status == EventStatus.under_review


def test_unassigned_submitted_request_cannot_be_approved(client, db_session):
    """An unassigned submission must be assigned before it can be approved."""
    _, _, _, coordinator_headers, event_id = review_setup(client, db_session)
    event = db_session.get(Event, event_id)
    event.coordinator_id = None
    event.status = EventStatus.submitted_awaiting_coordinator
    db_session.commit()

    response = client.post(f"/events/{event_id}/approve", headers=coordinator_headers)

    assert response.status_code == 409
    assert db_session.get(Event, event_id).status == EventStatus.submitted_awaiting_coordinator


def test_non_coordinator_cannot_approve(client, db_session):
    """An organiser cannot bypass the coordinator-only approval decision."""
    _, organiser_headers, _, _, event_id = review_setup(client, db_session)

    response = client.post(f"/events/{event_id}/approve", headers=organiser_headers)

    assert response.status_code == 403
    assert db_session.get(Event, event_id).status == EventStatus.under_review
