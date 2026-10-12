"""Unit cases for Venue Staff recording venue unavailability."""

from app.core.roles import Role
from app.models.enums import BookingStatus, NotificationType
from app.models.events import Event
from app.models.notifications import Notification
from app.models.user import User
from app.models.venues import VenueBooking
from test_venue_search import _at, _coordinator, _headers, _venue


def test_recording_unavailability_preserves_booking_and_notifies_coordinator(
    client, db_session
):
    coordinator_headers = _coordinator(client, db_session)
    coordinator = db_session.query(User).filter(User.email == "coord@example.com").one()
    venue = _venue(db_session, "Riverside Hall")
    event = Event(name="Summer Festival", organiser_id=coordinator.id, coordinator_id=coordinator.id)
    db_session.add(event)
    db_session.flush()
    booking = VenueBooking(
        event_id=event.id,
        venue_id=venue.id,
        requested_by=coordinator.id,
        start_time=_at(10),
        end_time=_at(12),
        status=BookingStatus.approved,
    )
    db_session.add(booking)
    db_session.commit()
    staff_headers = _headers(
        client, db_session, Role.VENUE_STAFF, email="unavailability-staff@example.com"
    )

    response = client.post(
        f"/venues/{venue.id}/unavailability",
        headers=staff_headers,
        json={
            "start_time": _at(11).isoformat(),
            "end_time": _at(13).isoformat(),
            "reason": "Emergency maintenance",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["affected_booking_ids"] == [booking.id]
    assert response.json()["affected_event_ids"] == [event.id]
    db_session.refresh(booking)
    assert booking.status == BookingStatus.approved
    assert booking.event_id == event.id
    notification = (
        db_session.query(Notification)
        .filter_by(event_id=event.id, type=NotificationType.venue_unavailability_recorded)
        .one()
    )
    assert notification.user_id == coordinator.id
    assert "Emergency maintenance" in notification.message
    calendar = client.get(
        f"/venues/{venue.id}/availability",
        params={"start": _at(9).isoformat(), "end": _at(14).isoformat()},
        headers=coordinator_headers,
    )
    booking_item = next(
        item for item in calendar.json()["items"] if item["kind"] == "confirmed_booking"
    )
    assert booking_item["conflicts_with_unavailability"] is True


def test_only_venue_staff_can_record_unavailability(client, db_session):
    coordinator_headers = _coordinator(client, db_session)
    venue = _venue(db_session, "Riverside Hall")

    response = client.post(
        f"/venues/{venue.id}/unavailability",
        headers=coordinator_headers,
        json={
            "start_time": _at(11).isoformat(),
            "end_time": _at(13).isoformat(),
            "reason": "Renovation",
        },
    )

    assert response.status_code == 403
