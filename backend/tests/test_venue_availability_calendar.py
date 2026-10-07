"""Unit cases for the View Venue Availability Calendar user story."""

from app.core.roles import Role
from app.models.enums import BookingStatus
from app.models.events import Event
from app.models.user import User
from app.models.venues import VenueBooking
from test_venue_search import _at, _block, _coordinator, _headers, _venue


def _window():
    return {"start": "2026-11-02T09:00:00Z", "end": "2026-11-02T17:00:00Z"}


def test_calendar_shows_confirmed_bookings_and_recorded_unavailability(client, db_session):
    headers = _coordinator(client, db_session)
    venue = _venue(db_session, "Calendar Hall")
    other_venue = _venue(db_session, "Other Hall")
    user = db_session.query(User).filter(User.email == "coord@example.com").one()
    event = Event(name="Planning Workshop", organiser_id=user.id)
    db_session.add(event)
    db_session.flush()
    db_session.add(
        VenueBooking(
            event_id=event.id,
            venue_id=venue.id,
            requested_by=user.id,
            start_time=_at(10),
            end_time=_at(11),
            status=BookingStatus.approved,
        )
    )
    db_session.commit()
    _block(db_session, venue, _at(14), _at(15))
    _block(db_session, other_venue, _at(12), _at(13))

    response = client.get(f"/venues/{venue.id}/availability", params=_window(), headers=headers)

    assert response.status_code == 200, response.text
    assert [
        (item["kind"], item["event_name"], item["reason"])
        for item in response.json()["items"]
    ] == [
        ("confirmed_booking", "Planning Workshop", None),
        ("unavailability", None, "Maintenance"),
    ]


def test_calendar_excludes_unconfirmed_bookings_and_records_outside_the_range(
    client, db_session
):
    headers = _coordinator(client, db_session)
    venue = _venue(db_session, "Calendar Hall")
    user = db_session.query(User).filter(User.email == "coord@example.com").one()
    event = Event(name="Pending Workshop", organiser_id=user.id)
    db_session.add(event)
    db_session.flush()
    db_session.add(
        VenueBooking(
            event_id=event.id,
            venue_id=venue.id,
            requested_by=user.id,
            start_time=_at(10),
            end_time=_at(11),
            status=BookingStatus.pending,
        )
    )
    db_session.commit()
    _block(db_session, venue, _at(18), _at(19))

    response = client.get(f"/venues/{venue.id}/availability", params=_window(), headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["items"] == []


def test_calendar_rejects_a_date_range_that_ends_before_it_starts(client, db_session):
    headers = _coordinator(client, db_session)
    venue = _venue(db_session, "Calendar Hall")

    response = client.get(
        f"/venues/{venue.id}/availability",
        params={"start": "2026-11-02T17:00:00Z", "end": "2026-11-02T09:00:00Z"},
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", "end"]


def test_calendar_is_limited_to_internal_roles(client, db_session):
    venue = _venue(db_session, "Calendar Hall")
    headers = _coordinator(client, db_session)
    response = client.get(f"/venues/{venue.id}/availability", params=_window(), headers=headers)
    assert response.status_code == 200

    staff_headers = _headers(
        client, db_session, Role.VENUE_STAFF, email="calendar-staff@example.com"
    )
    staff_response = client.get(
        f"/venues/{venue.id}/availability", params=_window(), headers=staff_headers
    )
    assert staff_response.status_code == 200

    password = "password123"
    client.post(
        "/auth/register",
        json={"name": "Attendee", "email": "calendar-attendee@example.com", "password": password},
    )
    attendee = db_session.query(User).filter(User.email == "calendar-attendee@example.com").one()
    attendee.role = Role.ATTENDEE.value
    db_session.commit()
    token = client.post(
        "/auth/login",
        json={"email": "calendar-attendee@example.com", "password": password},
    ).json()["access_token"]

    denied = client.get(
        f"/venues/{venue.id}/availability",
        params=_window(),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert denied.status_code == 403
