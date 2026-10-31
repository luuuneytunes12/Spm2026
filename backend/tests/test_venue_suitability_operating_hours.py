"""Operating hours in the venue suitability check.

2 Nov 2026 is a Monday. Hours are the venue's Singapore clock, so 01:00 UTC is
09:00 at the venue.
"""

from datetime import datetime, timezone

import pytest

from app.domain.venue_operating_hours import (
    VENUE_TIMEZONE,
    OperatingHours,
    UnreadableOperatingHours,
    outside_operating_hours,
)
from app.core.roles import Role
from app.models.enums import BookingStatus
from app.models.events import Event
from app.models.user import User
from app.models.venues import VenueBooking
from test_process_event_change_request import _assigned, _change_request
from test_venue_search import _coordinator, _headers, _venue
from test_venue_suitability import _assigned_event


def _sgt(hour, day=2, minute=0):
    """A moment on the venue's clock, as the UTC value that gets stored."""
    return datetime(2026, 11, day, hour, minute, tzinfo=VENUE_TIMEZONE).astimezone(timezone.utc)


def _setup(client, db_session, hours, start=None, end=None, **event):
    headers = _coordinator(client, db_session)
    coordinator = db_session.query(User).filter(User.email == "coord@example.com").one()
    venue = _venue(db_session, "Hours Hall", operating_hours=hours)
    event = _assigned_event(
        db_session,
        coordinator,
        accessibility_needs=None,
        venue_requirements=None,
        proposed_start=start,
        proposed_end=end,
        **event,
    )
    return headers, coordinator, venue, event


def _hours_check(result):
    return next(c for c in result["checks"] if c["category"] == "operating_hours")


def _book(db_session, event, venue, coordinator, start, end):
    booking = VenueBooking(
        event_id=event.id,
        venue_id=venue.id,
        requested_by=coordinator.id,
        start_time=start,
        end_time=end,
        status=BookingStatus.pending,
    )
    db_session.add(booking)
    db_session.commit()
    return booking


@pytest.mark.parametrize(
    "start, end",
    [
        (_sgt(10), _sgt(12)),
        # Boundaries are inside: starting at opening, ending at closing.
        (_sgt(9), _sgt(17)),
    ],
)
def test_ac1_event_fully_inside_hours_counts_as_met(client, db_session, start, end):
    headers, _, venue, event = _setup(client, db_session, "Mon-Fri 09:00-17:00", start, end)

    res = client.get(f"/venues/{venue.id}/suitability/{event.id}", headers=headers)

    assert res.status_code == 200, res.text
    assert res.json()["suitable"] is True
    assert _hours_check(res.json())["met"] is True


@pytest.mark.parametrize(
    "start, end",
    [
        (_sgt(18), _sgt(20)),  # fully outside
        (_sgt(8), _sgt(10)),  # starts before opening
        (_sgt(16), _sgt(18)),  # ends after closing
        (_sgt(10, day=7), _sgt(12, day=7)),  # a Saturday, right time wrong day
        (_sgt(9), _sgt(17, day=3)),  # runs through the closed night
    ],
)
def test_ac2_event_partly_or_fully_outside_is_not_suitable(client, db_session, start, end):
    headers, _, venue, event = _setup(client, db_session, "Mon-Fri 09:00-17:00", start, end)

    result = client.get(f"/venues/{venue.id}/suitability/{event.id}", headers=headers).json()

    assert result["suitable"] is False
    check = _hours_check(result)
    assert check["met"] is False
    assert check["message"] == "Outside operating hours"
    assert check["available"] == "Mon-Fri 09:00-17:00"


def test_ac2_times_are_compared_on_the_venues_clock_not_utc(client, db_session):
    # 09:00-10:00 UTC is 17:00-18:00 at the venue: inside if read as UTC.
    start = datetime(2026, 11, 2, 9, tzinfo=timezone.utc)
    end = datetime(2026, 11, 2, 10, tzinfo=timezone.utc)
    headers, _, venue, event = _setup(client, db_session, "Mon-Fri 09:00-17:00", start, end)

    result = client.get(f"/venues/{venue.id}/suitability/{event.id}", headers=headers).json()

    assert _hours_check(result)["message"] == "Outside operating hours"


def test_ac3_only_the_booking_outside_hours_is_marked_not_suitable(client, db_session):
    headers, coordinator, open_late, event = _setup(
        client, db_session, "Mon-Fri 09:00-22:00", _sgt(10), _sgt(12)
    )
    closes_early = _venue(db_session, "Early Hall", operating_hours="Mon-Fri 09:00-17:00")
    inside = _book(db_session, event, open_late, coordinator, _sgt(18), _sgt(20))
    outside = _book(db_session, event, closes_early, coordinator, _sgt(18), _sgt(20))

    whole = client.get(f"/venues/events/{event.id}/suitability", headers=headers).json()
    alone = client.get(f"/venues/bookings/{outside.id}/suitability", headers=headers).json()
    other = client.get(f"/venues/bookings/{inside.id}/suitability", headers=headers).json()

    assert {v["venue_name"]: v["suitable"] for v in whole["venues"]} == {
        "Hours Hall": True,
        "Early Hall": False,
    }
    assert alone["suitable"] is False
    assert _hours_check(alone)["message"] == "Outside operating hours"
    assert other["suitable"] is True


def test_ac3_a_booking_uses_its_own_time_not_the_events(client, db_session):
    # The Event's time is inside the hours; this booking's is not.
    headers, coordinator, venue, event = _setup(
        client, db_session, "Mon-Fri 09:00-17:00", _sgt(10), _sgt(12)
    )
    booking = _book(db_session, event, venue, coordinator, _sgt(18), _sgt(20))

    alone = client.get(f"/venues/bookings/{booking.id}/suitability", headers=headers).json()

    assert alone["suitable"] is False


@pytest.mark.parametrize("hours", [None, "", "  \n "])
def test_ac4_no_hours_recorded_is_treated_as_open(client, db_session, hours):
    headers, _, venue, event = _setup(client, db_session, hours, _sgt(3), _sgt(4))

    result = client.get(f"/venues/{venue.id}/suitability/{event.id}", headers=headers).json()

    assert result["suitable"] is True
    assert "operating_hours" not in {c["category"] for c in result["checks"]}


def test_ac4_other_checks_still_apply_without_hours(client, db_session):
    headers, _, venue, event = _setup(
        client, db_session, None, _sgt(3), _sgt(4), expected_attendance=500
    )

    result = client.get(f"/venues/{venue.id}/suitability/{event.id}", headers=headers).json()

    assert result["suitable"] is False
    assert [c["category"] for c in result["checks"] if not c["met"]] == ["capacity"]


def test_hours_that_cannot_be_read_are_not_claimed_as_met(client, db_session):
    headers, _, venue, event = _setup(client, db_session, "By appointment", _sgt(10), _sgt(12))

    result = client.get(f"/venues/{venue.id}/suitability/{event.id}", headers=headers).json()

    assert result["suitable"] is False
    assert _hours_check(result)["message"].startswith("Cannot read")
    assert _hours_check(result)["available"] == "By appointment"


def test_missing_event_time_is_not_claimed_as_met(client, db_session):
    headers, _, venue, event = _setup(client, db_session, "Mon-Fri 09:00-17:00")

    result = client.get(f"/venues/{venue.id}/suitability/{event.id}", headers=headers).json()

    assert result["suitable"] is False
    assert _hours_check(result)["requirement"] == "Event time is not recorded"


def test_other_roles_cannot_check(client, db_session):
    _, _, venue, event = _setup(client, db_session, "Mon-Fri 09:00-17:00", _sgt(10), _sgt(12))
    url = f"/venues/{venue.id}/suitability/{event.id}"

    organiser = _headers(client, db_session, Role.ORGANISER, "organiser@example.com")
    assert client.get(url, headers=organiser).status_code == 403
    assert client.get(url).status_code == 401


@pytest.mark.parametrize(
    "text, start, end, outside",
    [
        ("Daily 09:00-18:00", _sgt(10), _sgt(11), False),
        ("09:00-18:00", _sgt(10, day=7), _sgt(11, day=7), False),
        ("Mon-Fri: 09:00 - 18:00", _sgt(10), _sgt(11), False),
        ("Mon, Wed 09:00-18:00", _sgt(10, day=3), _sgt(11, day=3), True),
        ("Monday-Friday 09:00–18:00", _sgt(10), _sgt(11), False),
        ("Fri-Mon 09:00-18:00", _sgt(10), _sgt(11), False),
        ("Mon-Fri 08:00-23:00\nSat-Sun 09:00-23:00", _sgt(8, day=7), _sgt(10, day=7), True),
        ("Tue-Sun 11:00-23:00\nClosed Mondays", _sgt(12), _sgt(13), True),
        ("Tue-Sun 11:00-23:00\nClosed Mondays", _sgt(12, day=3), _sgt(13, day=3), False),
        # Overnight: Monday's hours run into Tuesday morning.
        ("Mon-Sun 17:00-01:00", _sgt(23), _sgt(0, day=3, minute=30), False),
        ("Mon 17:00-01:00", _sgt(0, day=3), _sgt(1, day=3), False),
        ("Mon 17:00-01:00", _sgt(1, day=3), _sgt(2, day=3), True),
        # Open round the clock, across days.
        ("Daily 00:00-24:00", _sgt(9), _sgt(17, day=4), False),
        # Back-to-back entries join up.
        ("Mon 09:00-12:00\nMon 12:00-17:00", _sgt(10), _sgt(14), False),
        ("Mon 09:00-12:00\nMon 13:00-17:00", _sgt(10), _sgt(14), True),
    ],
)
def test_reading_recorded_hours(text, start, end, outside):
    assert outside_operating_hours(text, start, end) is outside


@pytest.mark.parametrize(
    "text",
    [
        "By appointment",
        "Mon-Fri",
        "Funday 09:00-17:00",
        "Mon 25:00-26:00",
        "Mon 09:75-17:00",
        "Closed Sundays",
    ],
)
def test_text_that_is_not_hours_is_refused_by_the_parser(text):
    with pytest.raises(UnreadableOperatingHours):
        OperatingHours.parse(text)


def test_change_request_impact_reports_outside_operating_hours(client, db_session):
    """A proposed new time gets the same check as the suitability pages."""
    organiser, organiser_headers, _, _, event_id = _assigned(client, db_session)
    venue = _venue(db_session, "Hours Hall", operating_hours="Mon-Fri 09:00-17:00")
    _book(db_session, db_session.get(Event, event_id), venue, organiser, _sgt(10), _sgt(12))

    request = _change_request(
        client,
        event_id,
        organiser_headers,
        {"proposed_start": _sgt(18).isoformat(), "proposed_end": _sgt(20).isoformat()},
    )

    impact = request["venue_bookings_to_reconsider"][0]
    assert impact["suitable"] is False
    assert "Outside operating hours" in impact["unmet_requirements"]
