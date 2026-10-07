"""Unit tests for rejecting an event request with a recorded reason."""

import pytest

from app.core.roles import Role
from app.models.enums import BookingStatus, EventStatus
from app.models.events import Event, EventStatusHistory
from app.models.notifications import Notification
from app.models.venues import VenueBooking
from event_review_test_helpers import review_setup, user
from tests.test_venue_booking_request import _submit, _venue

# These tests start from an event that already has a Coordinator; assignment is
# now the Lead's job, so submit alone no longer provides one (see conftest).
pytestmark = pytest.mark.usefixtures("coordinator_auto_assign")


def test_rejection_requires_a_non_blank_reason(client, db_session):
    _, _, _, coordinator_headers, event_id = review_setup(client, db_session)

    response = client.post(
        f"/events/{event_id}/reject", json={"reason": "   "}, headers=coordinator_headers
    )

    assert response.status_code == 422
    assert db_session.get(Event, event_id).status == EventStatus.submitted_awaiting_coordinator


def test_rejection_records_reason_notifies_organiser_and_logs_coordinator(
    client, db_session
):
    organiser, organiser_headers, coordinator, coordinator_headers, event_id = review_setup(
        client, db_session
    )
    event = db_session.get(Event, event_id)
    event.status = EventStatus.submitted_awaiting_coordinator
    db_session.commit()
    reason = "The requested venue is unavailable on that date."

    response = client.post(
        f"/events/{event_id}/reject", json={"reason": reason}, headers=coordinator_headers
    )

    assert response.status_code == 200
    assert response.json()["status"] == "event_rejected"
    decision = (
        db_session.query(EventStatusHistory)
        .filter_by(event_id=event_id, to_status="event_rejected")
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
    rejection = next(entry for entry in activity.json() if entry["to_status"] == "event_rejected")
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

    assert response.status_code == 403
    assert db_session.get(Event, event_id).status == EventStatus.submitted_awaiting_coordinator


def test_coordinator_lead_is_view_only_for_event_rejection(client, db_session):
    _, _, _, _, event_id = review_setup(client, db_session)
    _, lead_headers = user(
        client,
        db_session,
        Role.COORDINATOR_LEAD,
        "lead@example.com",
        "Coordinator Lead",
    )

    response = client.post(
        f"/events/{event_id}/reject",
        json={"reason": "This should not be permitted."},
        headers=lead_headers,
    )

    assert response.status_code == 403
    assert db_session.get(Event, event_id).status == EventStatus.submitted_awaiting_coordinator


def test_event_rejection_releases_all_of_its_live_venue_bookings(client, db_session):
    _, _, coordinator, coordinator_headers, event_id = review_setup(client, db_session)
    event = db_session.get(Event, event_id)
    first_venue = _venue(db_session, "Main Hall")
    second_venue = _venue(db_session, "Garden Hall")
    approved = VenueBooking(
        event_id=event_id,
        venue_id=first_venue.id,
        requested_by=coordinator.id,
        start_time=event.proposed_start,
        end_time=event.proposed_end,
        status=BookingStatus.approved,
    )
    hold = VenueBooking(
        event_id=event_id,
        venue_id=second_venue.id,
        requested_by=coordinator.id,
        start_time=event.proposed_start,
        end_time=event.proposed_end,
        status=BookingStatus.tentative_hold,
        expires_at=event.proposed_end,
    )
    db_session.add_all([approved, hold])
    db_session.commit()

    response = client.post(
        f"/events/{event_id}/reject",
        json={"reason": "The request cannot proceed."},
        headers=coordinator_headers,
    )

    assert response.status_code == 200
    db_session.refresh(approved)
    db_session.refresh(hold)
    assert approved.status == hold.status == BookingStatus.cancelled
    assert db_session.get(Event, event_id).name == "Regional Partner Conference"


def test_organiser_cannot_read_another_organisers_rejection_activity(client, db_session):
    _, _, _, _, event_id = review_setup(client, db_session)
    _, other_headers = user(
        client, db_session, Role.ORGANISER, "other-organiser@example.com", "Other Organiser"
    )

    response = client.get(f"/events/{event_id}/activity", headers=other_headers)

    assert response.status_code == 404