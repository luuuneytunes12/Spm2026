"""Venue search leaves out venues closed in the chosen time.

2 Nov 2026 is a Monday. Hours are the venue's Singapore clock, so a window is
given here with a +08:00 offset and reads the same as the hours.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.roles import Role
from app.models.enums import BookingStatus
from app.models.venues import VenueBooking
from test_venue_search import _at, _booking, _coordinator, _headers, _names, _venue

HOURS = "Mon-Fri 09:00-17:00"


def _window(start, end, day=2):
    return {"start": f"2026-11-{day:02d}T{start}:00+08:00", "end": f"2026-11-{day:02d}T{end}:00+08:00"}


def _search(client, headers, start, end, day=2, **filters):
    return _names(client.get("/venues", params={**_window(start, end, day), **filters}, headers=headers))


@pytest.mark.parametrize(
    "start, end",
    [
        ("08:59", "12:00"),  # starts before opening
        ("16:00", "17:01"),  # ends after closing
        ("08:00", "18:00"),  # runs past both ends
        ("18:00", "20:00"),  # fully after closing
        ("06:00", "08:00"),  # fully before opening
    ],
)
def test_ac1_a_window_partly_or_fully_outside_the_hours_leaves_the_venue_out(
    client, db_session, start, end
):
    headers = _coordinator(client, db_session)
    _venue(db_session, "Hall", operating_hours=HOURS)

    assert _search(client, headers, start, end) == []


def test_ac1_a_day_the_hours_do_not_cover_leaves_the_venue_out(client, db_session):
    headers = _coordinator(client, db_session)
    _venue(db_session, "Hall", operating_hours=HOURS)

    assert _search(client, headers, "10:00", "12:00", day=7) == []  # a Saturday


def test_ac1_the_window_is_compared_on_the_venues_clock_not_utc(client, db_session):
    headers = _coordinator(client, db_session)
    _venue(db_session, "Hall", operating_hours=HOURS)

    # 10:00-12:00 UTC is 18:00-20:00 at the venue, after closing.
    params = {"start": "2026-11-02T10:00:00Z", "end": "2026-11-02T12:00:00Z"}
    assert _names(client.get("/venues", params=params, headers=headers)) == []


def test_ac2_a_window_of_exactly_the_hours_keeps_the_venue(client, db_session):
    headers = _coordinator(client, db_session)
    _venue(db_session, "Hall", operating_hours=HOURS)

    assert _search(client, headers, "09:00", "17:00") == ["Hall"]


def test_ac2_setup_and_turnaround_do_not_push_an_exact_window_outside(client, db_session):
    headers = _coordinator(client, db_session)
    _venue(db_session, "Hall", operating_hours=HOURS, setup_minutes=30, turnaround_minutes=60)

    assert _search(client, headers, "09:00", "17:00") == ["Hall"]


def test_ac3_no_hours_recorded_keeps_the_venue_and_other_filters_still_apply(client, db_session):
    headers = _coordinator(client, db_session)
    _venue(db_session, "Big Hall", operating_hours=None, capacity=300)
    _venue(db_session, "Small Hall", operating_hours=None, capacity=10)

    assert _search(client, headers, "02:00", "03:00", min_capacity=100) == ["Big Hall"]


@pytest.mark.parametrize(
    "status", [BookingStatus.approved, BookingStatus.tentative_hold]
)
def test_ac4_an_open_venue_with_a_booking_or_hold_is_still_excluded(client, db_session, status):
    headers = _coordinator(client, db_session)
    taken = _venue(db_session, "Taken Hall", operating_hours=HOURS)
    _venue(db_session, "Free Hall", operating_hours=HOURS)
    # 02:00-04:00 UTC is 10:00-12:00 at the venue.
    _booking(db_session, taken, _at(2), _at(4))
    if status == BookingStatus.tentative_hold:
        # The database refuses a hold with no expiry, which _booking cannot set.
        booking = db_session.query(VenueBooking).filter_by(venue_id=taken.id).one()
        booking.status = status
        booking.expires_at = datetime.now(timezone.utc) + timedelta(days=1)
        db_session.commit()

    assert _search(client, headers, "09:00", "17:00") == ["Free Hall"]


def test_unreadable_hours_keep_the_venue_findable(client, db_session):
    headers = _coordinator(client, db_session)
    _venue(db_session, "Hall", operating_hours="By appointment")

    assert _search(client, headers, "10:00", "12:00") == ["Hall"]


def test_frozen_search_without_a_window_ignores_the_hours(client, db_session):
    headers = _coordinator(client, db_session)
    _venue(db_session, "Hall", operating_hours=HOURS)

    assert _names(client.get("/venues", headers=headers)) == ["Hall"]


def test_other_roles_still_cannot_search(client, db_session):
    _venue(db_session, "Hall", operating_hours=HOURS)
    organiser = _headers(client, db_session, Role.ORGANISER, "organiser@example.com")

    assert client.get("/venues", params=_window("10:00", "12:00"), headers=organiser).status_code == 403
    assert client.get("/venues", params=_window("10:00", "12:00")).status_code == 401
