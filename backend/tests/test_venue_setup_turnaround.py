"""Tests for "Configure Venue Setup & Turnaround Time" (SCRUM-78), AC1-AC6."""

import pytest

from app.core.roles import Role
from app.models.enums import BookingStatus, EventStatus
from app.models.events import Event
from app.models.venues import VenueBooking
from tests.event_review_test_helpers import review_setup, user
from tests.test_venue_booking_request import _submit, _venue
from tests.test_venue_search import WINDOW, _at, _booking, _headers, _names

pytestmark = pytest.mark.usefixtures("coordinator_auto_assign")


def _put(client, headers, venue_id, body):
    return client.put(f"/venues/{venue_id}/setup-turnaround", json=body, headers=headers)


def _staff(client, db_session):
    return _headers(client, db_session, Role.VENUE_STAFF, "vs@example.com")


def _row(db_session, venue):
    db_session.expire_all()
    return venue.setup_minutes, venue.turnaround_minutes


# --- AC1 ---------------------------------------------------------------------


def test_ac1_venue_staff_save_setup_and_turnaround(client, db_session):
    venue = _venue(db_session)
    staff_h = _staff(client, db_session)
    res = _put(client, staff_h, venue.id, {"setup_minutes": 30, "turnaround_minutes": 45})
    assert res.status_code == 200
    assert res.json()["setup_minutes"] == 30 and res.json()["turnaround_minutes"] == 45
    assert _row(db_session, venue) == (30, 45)
    assert venue.setup_turnaround_updated_by is not None  # actor recorded
    assert venue.setup_turnaround_updated_at is not None


def test_ac1_zero_is_valid_and_saving_again_is_idempotent(client, db_session):
    venue = _venue(db_session)
    staff_h = _staff(client, db_session)
    body = {"setup_minutes": 0, "turnaround_minutes": 15}
    first = _put(client, staff_h, venue.id, body)
    second = _put(client, staff_h, venue.id, body)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert _row(db_session, venue) == (0, 15)


def test_ac1_unknown_venue_is_404(client, db_session):
    staff_h = _staff(client, db_session)
    assert _put(client, staff_h, 9999, {"setup_minutes": 1, "turnaround_minutes": 1}).status_code == 404


def test_ac1_only_venue_staff_may_save(client, db_session):
    venue = _venue(db_session)
    coord_h = _headers(client, db_session, Role.COORDINATOR, "c@example.com")
    res = _put(client, coord_h, venue.id, {"setup_minutes": 30, "turnaround_minutes": 45})
    assert res.status_code == 403
    assert _row(db_session, venue) == (None, None)
    attendee = client.post(
        "/auth/register", json={"name": "A", "email": "a@example.com", "password": "password123"}
    )
    assert attendee.status_code == 201
    token = client.post("/auth/login", json={"email": "a@example.com", "password": "password123"}).json()[
        "access_token"
    ]
    attendee_h = {"Authorization": f"Bearer {token}"}
    assert _put(client, attendee_h, venue.id, {"setup_minutes": 1, "turnaround_minutes": 1}).status_code == 403
    assert client.put(f"/venues/{venue.id}/setup-turnaround", json={}).status_code == 401


# --- AC2: validation, no partial write ---------------------------------------


@pytest.mark.parametrize(
    "body, field",
    [
        ({"setup_minutes": None, "turnaround_minutes": 10}, "setup_minutes"),
        ({"setup_minutes": 10}, "turnaround_minutes"),
        ({"setup_minutes": 10, "turnaround_minutes": None}, "turnaround_minutes"),
        ({}, "setup_minutes"),
        ({"setup_minutes": "", "turnaround_minutes": 10}, "setup_minutes"),
        ({"setup_minutes": -1, "turnaround_minutes": 10}, "setup_minutes"),
        ({"setup_minutes": 10, "turnaround_minutes": -5}, "turnaround_minutes"),
        ({"setup_minutes": 10.5, "turnaround_minutes": 10}, "setup_minutes"),
        ({"setup_minutes": 10, "turnaround_minutes": 2.5}, "turnaround_minutes"),
        ({"setup_minutes": "10", "turnaround_minutes": 10}, "setup_minutes"),
        ({"setup_minutes": True, "turnaround_minutes": 10}, "setup_minutes"),
    ],
)
def test_ac2_invalid_values_are_blocked_with_no_partial_write(client, db_session, body, field):
    venue = _venue(db_session, setup_minutes=5, turnaround_minutes=6)
    staff_h = _staff(client, db_session)
    res = _put(client, staff_h, venue.id, body)
    assert res.status_code == 422
    assert ["body", field] in [err["loc"] for err in res.json()["detail"]]
    assert _row(db_session, venue) == (5, 6)  # untouched, the valid half too
    assert venue.setup_turnaround_updated_at is None


# --- AC3 / AC4: not set; internal users see both -------------------------------


def test_ac3_ac4_unset_venue_reads_null_and_internal_users_see_values(client, db_session):
    venue = _venue(db_session)
    staff_h = _staff(client, db_session)
    coord_h = _headers(client, db_session, Role.COORDINATOR, "c@example.com")
    for h in (staff_h, coord_h):
        body = client.get(f"/venues/{venue.id}", headers=h).json()
        assert body["setup_minutes"] is None and body["turnaround_minutes"] is None
    _put(client, staff_h, venue.id, {"setup_minutes": 30, "turnaround_minutes": 45})
    for h in (staff_h, coord_h):
        body = client.get(f"/venues/{venue.id}", headers=h).json()
        assert (body["setup_minutes"], body["turnaround_minutes"]) == (30, 45)


def test_ac4_attendees_still_cannot_view_a_venue(client, db_session):
    venue = _venue(db_session)
    client.post("/auth/register", json={"name": "A", "email": "a@example.com", "password": "password123"})
    token = client.post("/auth/login", json={"email": "a@example.com", "password": "password123"}).json()[
        "access_token"
    ]
    assert client.get(f"/venues/{venue.id}", headers={"Authorization": f"Bearer {token}"}).status_code == 403


def test_ac3_unset_venue_search_unchanged_frozen_literal(client, db_session):
    """Null buffers: exactly the pre-story behaviour (touching edges free)."""
    venue = _venue(db_session, "Plain Hall")
    coord_h = _headers(client, db_session, Role.COORDINATOR, "c@example.com")
    _booking(db_session, venue, _at(7), _at(9))
    assert _names(client.get("/venues", params=WINDOW, headers=coord_h)) == ["Plain Hall"]
    _booking(db_session, venue, _at(16), _at(18))
    assert _names(client.get("/venues", params=WINDOW, headers=coord_h)) == []


# --- AC5: occupancy used by search and approval -------------------------------


def test_ac5_search_window_includes_setup_and_turnaround(client, db_session):
    venue = _venue(db_session, "Buffered Hall", setup_minutes=30, turnaround_minutes=45)
    coord_h = _headers(client, db_session, Role.COORDINATOR, "c@example.com")
    # Existing booking 06:00-08:00 holds the hall until 08:45; searching from
    # 09:00 needs it from 08:30 -> clash. Unbuffered it would be free.
    _booking(db_session, venue, _at(6), _at(8))
    assert _names(client.get("/venues", params=WINDOW, headers=coord_h)) == []
    # Search starting 09:30 occupies from 09:00; the booking ends occupied 08:45.
    res = client.get(
        "/venues", params={"start": "2026-11-02T09:30:00Z", "end": "2026-11-02T17:00:00Z"}, headers=coord_h
    )
    assert _names(res) == ["Buffered Hall"]


def test_ac5_a_booking_after_the_window_is_buffered_too(client, db_session):
    venue = _venue(db_session, "Buffered Hall", setup_minutes=30, turnaround_minutes=45)
    coord_h = _headers(client, db_session, Role.COORDINATOR, "c@example.com")
    _booking(db_session, venue, _at(17), _at(19))  # touches the window end
    assert _names(client.get("/venues", params=WINDOW, headers=coord_h)) == []  # 17:45 turnaround vs 17:00 start-30


def _two_bookings(client, db_session, setup, turnaround, gap_start_hour):
    """An approved booking 10:00-12:00, and a pending one starting at
    `gap_start_hour` for the same venue."""
    _, org_h, coordinator, coord_h, event_id = review_setup(client, db_session)
    event = db_session.get(Event, event_id)
    event.status = EventStatus.event_approved
    event.proposed_start = _at(gap_start_hour)
    event.proposed_end = _at(gap_start_hour + 2)
    _, staff_h = user(client, db_session, Role.VENUE_STAFF, "staff@example.com", "Vera")
    venue = _venue(db_session, setup_minutes=setup, turnaround_minutes=turnaround)
    _booking(db_session, venue, _at(10), _at(12))
    booking_id = _submit(client, coord_h, event_id, venue.id).json()["id"]
    return staff_h, booking_id


def test_ac5_approval_is_refused_when_the_buffers_leave_no_room(client, db_session):
    staff_h, booking_id = _two_bookings(client, db_session, 30, 45, 13)  # 13:00 -30 = 12:30 < 12:45
    res = client.post(f"/venue-bookings/{booking_id}/approve", headers=staff_h)
    assert res.status_code == 409
    assert db_session.get(VenueBooking, booking_id).status == BookingStatus.pending


def test_ac5_approval_succeeds_when_buffers_fit(client, db_session):
    staff_h, booking_id = _two_bookings(client, db_session, 30, 45, 14)  # 13:30 > 12:45
    assert client.post(f"/venue-bookings/{booking_id}/approve", headers=staff_h).status_code == 200


def test_ac5_back_to_back_without_buffers_is_still_allowed(client, db_session):
    staff_h, booking_id = _two_bookings(client, db_session, None, None, 12)
    assert client.post(f"/venue-bookings/{booking_id}/approve", headers=staff_h).status_code == 200


# --- AC6: booking responses expose the periods --------------------------------


def test_ac6_booking_responses_show_event_time_and_buffers(client, db_session):
    _, org_h, coordinator, coord_h, event_id = review_setup(client, db_session)
    event = db_session.get(Event, event_id)
    event.status = EventStatus.event_approved
    event.proposed_start = _at(10)
    event.proposed_end = _at(12)
    _, staff_h = user(client, db_session, Role.VENUE_STAFF, "staff@example.com", "Vera")
    venue = _venue(db_session, setup_minutes=30, turnaround_minutes=45)
    booking_id = _submit(client, coord_h, event_id, venue.id).json()["id"]

    for body in (
        client.get("/venue-bookings/queue", headers=staff_h).json()[0],
        client.get(f"/venue-bookings/{booking_id}", headers=staff_h).json(),
        client.get(f"/venue-bookings/events/{event_id}", headers=coord_h).json()[0],
    ):
        assert (body["setup_minutes"], body["turnaround_minutes"]) == (30, 45)
        assert body["occupied_start"].startswith("2026-11-02T09:30:00")
        assert body["occupied_end"].startswith("2026-11-02T12:45:00")
        assert body["start_time"].startswith("2026-11-02T10:00:00")


def test_ac6_unset_buffers_read_as_zero(client, db_session):
    _, org_h, coordinator, coord_h, event_id = review_setup(client, db_session)
    db_session.get(Event, event_id).status = EventStatus.event_approved
    db_session.commit()
    venue = _venue(db_session)
    body = _submit(client, coord_h, event_id, venue.id).json()
    assert (body["setup_minutes"], body["turnaround_minutes"]) == (0, 0)
    assert body["occupied_start"][:19] == body["start_time"][:19]
    assert body["occupied_end"][:19] == body["end_time"][:19]


def test_ac6_safety_check_booking_shows_buffers_and_occupied_period(client, db_session):
    from tests.test_safety_checks import _setup

    s = _setup(client, db_session)
    detail = client.get(f"/safety-checks/{s['event_id']}", headers=s["officer_h"]).json()
    vb = detail["venue_bookings"][0]
    assert (vb["setup_minutes"], vb["turnaround_minutes"]) == (0, 0)
    assert vb["occupied_start"][:19] == vb["start_time"][:19]

    from app.models.venues import Venue

    db_session.get(Venue, vb["venue"]["id"]).setup_minutes = 30
    db_session.get(Venue, vb["venue"]["id"]).turnaround_minutes = 45
    db_session.commit()
    vb = next(
        b
        for b in client.get(f"/safety-checks/{s['event_id']}", headers=s["officer_h"]).json()["venue_bookings"]
        if b["id"] == vb["id"]
    )
    assert (vb["setup_minutes"], vb["turnaround_minutes"]) == (30, 45)
    assert vb["occupied_start"] < vb["start_time"] and vb["occupied_end"] > vb["end_time"]
