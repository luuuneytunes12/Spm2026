"""SCRUM-37 - View Venue Availability Calendar (API cases).

SCRUM-37 AC1  calendar laid out by date and time -- tested here as the order
              and the buffered occupied period of each item (no UI layout)
SCRUM-37 AC2  confirmed bookings shown -- test_calendar_shows_confirmed_...
SCRUM-37 AC3  recorded unavailability shown -- same test
SCRUM-37 AC4  filter by date range -- test_calendar_excludes_... and the range tests
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import ProgrammingError

from app.core.roles import Role
from app.models.enums import BookingStatus, NotificationType
from app.models.events import Event
from app.models.notifications import Notification
from app.models.user import User
from app.models.venues import VenueBooking
from test_venue_search import _at, _block, _coordinator, _headers, _venue


def _window():
    return {"start": "2099-11-02T09:00:00Z", "end": "2099-11-02T17:00:00Z"}


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
        ("confirmed_booking", None, None),  # a Coordinator is not told which event
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


def test_calendar_shows_active_holds_for_each_venue_and_excludes_expired_holds(
    client, db_session
):
    headers = _coordinator(client, db_session)
    first_venue = _venue(db_session, "Calendar Hall")
    second_venue = _venue(db_session, "Second Hall")
    user = db_session.query(User).filter(User.email == "coord@example.com").one()
    event = Event(
        name="Multi-venue Workshop",
        organiser_id=user.id,
        coordinator_id=user.id,
    )
    db_session.add(event)
    db_session.flush()
    active_hold = VenueBooking(
        event_id=event.id,
        venue_id=first_venue.id,
        requested_by=user.id,
        start_time=_at(10),
        end_time=_at(11),
        status=BookingStatus.tentative_hold,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
    )
    expired_hold = VenueBooking(
        event_id=event.id,
        venue_id=second_venue.id,
        requested_by=user.id,
        start_time=_at(12),
        end_time=_at(13),
        status=BookingStatus.tentative_hold,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db_session.add_all([active_hold, expired_hold])
    db_session.commit()

    first_calendar = client.get(
        f"/venues/{first_venue.id}/availability", params=_window(), headers=headers
    )
    second_calendar = client.get(
        f"/venues/{second_venue.id}/availability", params=_window(), headers=headers
    )

    assert first_calendar.status_code == second_calendar.status_code == 200
    first_item = first_calendar.json()["items"][0]
    assert first_item["kind"] == "tentative_hold"
    assert first_item["event_id"] is None and first_item["event_name"] is None
    assert first_item["expires_at"] is not None
    assert second_calendar.json()["items"] == []
    assert db_session.get(VenueBooking, expired_hold.id).status == BookingStatus.hold_expired
    expiry_notification = (
        db_session.query(Notification)
        .filter_by(
            event_id=event.id,
            user_id=user.id,
            type=NotificationType.venue_hold_expired,
        )
        .one()
    )
    assert "expired" in expiry_notification.message.lower()


def test_scrum37_ac1_items_come_back_in_time_order_with_their_buffered_period(client, db_session):
    """SCRUM-37 AC1: the calendar lists busy periods in time order, and each
    booking's occupied period is widened by the venue's setup (30 min before)
    and turnaround (45 min after). Created later-first to prove the sort.
    Expected: 10:00-11:00 then 14:00-15:00, with 09:30-11:45 and 13:30-15:45."""
    headers = _coordinator(client, db_session)
    venue = _venue(db_session, "Layout Hall")
    venue.setup_minutes, venue.turnaround_minutes = 30, 45
    db_session.commit()
    user = db_session.query(User).filter(User.email == "coord@example.com").one()
    # One live booking per (event, venue) is a database rule, so each booking has its own event.
    for start, end in ((14, 15), (10, 11)):
        event = Event(name=f"Layout Workshop {start}:00", organiser_id=user.id)
        db_session.add(event)
        db_session.flush()
        db_session.add(
            VenueBooking(
                event_id=event.id, venue_id=venue.id, requested_by=user.id,
                start_time=_at(start), end_time=_at(end), status=BookingStatus.approved,
            )
        )
    db_session.commit()

    items = client.get(f"/venues/{venue.id}/availability", params=_window(), headers=headers).json()["items"]

    assert [item["start_time"][11:16] for item in items] == ["10:00", "14:00"]
    assert items[0]["occupied_start"].startswith("2099-11-02T09:30")
    assert items[0]["occupied_end"].startswith("2099-11-02T11:45")
    assert items[1]["occupied_start"].startswith("2099-11-02T13:30")
    assert items[1]["occupied_end"].startswith("2099-11-02T15:45")


def test_calendar_rejects_a_date_range_that_ends_before_it_starts(client, db_session):
    headers = _coordinator(client, db_session)
    venue = _venue(db_session, "Calendar Hall")

    response = client.get(
        f"/venues/{venue.id}/availability",
        params={"start": "2099-11-02T17:00:00Z", "end": "2099-11-02T09:00:00Z"},
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", "end"]


def test_calendar_reports_missing_expiry_column_and_logs_database_error(
    client, db_session, monkeypatch, caplog
):
    headers = _coordinator(client, db_session)
    venue = _venue(db_session, "Calendar Hall")

    def fail_expiring_holds(_db):
        raise ProgrammingError(
            "SELECT venue_bookings.expires_at",
            {},
            Exception("column venue_bookings.expires_at does not exist"),
        )

    monkeypatch.setattr("app.routers.venues.expire_tentative_holds", fail_expiring_holds)

    response = client.get(
        f"/venues/{venue.id}/availability",
        params=_window(),
        headers=headers,
    )

    assert response.status_code == 503
    assert "venue_bookings.expires_at" in response.json()["detail"]
    assert "backend/sql/019_multi_venue_tentative_holds.sql" in response.json()["detail"]
    assert "Failed to retrieve venue availability" in caplog.text
    assert "column venue_bookings.expires_at does not exist" in caplog.text


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
