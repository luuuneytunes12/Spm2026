"""Tests for the "Filter Venues by Date and Time" story (Event Coordinator).

    As an Event Coordinator, I want to filter Venues by the date and time my
    Event needs, so that I only see Venues that are free then.

Each test is named after the acceptance criterion it proves (DT AC1-AC4);
the mapping is in docs/test-cases-venue-date-filter.md.

The rule under test (app/services/venue_availability.py): a booking of
[start, end) keeps its venue busy for [start - setup, end + turnaround), and
so does the event being searched for. A venue is left out when an approved
booking, a tentative hold (a `pending` request) or a recorded unavailability
period clashes with that padded period. Consecutive events at a venue
therefore need `setup + turnaround` minutes between them.

Every date test searches the same window: 2 Nov 2026, 09:00-17:00 UTC.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.roles import Role
from app.models.enums import BookingStatus
from app.models.venues import VenueBooking
from tests.test_venue_booking_decision import (
    _approve,
    _second_request_for_the_same_venue,
    _setup,
)
from tests.test_venue_search import WINDOW, _at, _block, _booking, _coordinator, _headers, _names, _venue


def _minutes(hour, minute=0, day=2):
    """A moment on `day` Nov 2026 at hour:minute, in UTC."""
    return _at(hour, day=day) + timedelta(minutes=minute)


def _search(client, headers, **params):
    return _names(client.get("/venues", params={**WINDOW, **params}, headers=headers))


# ---------------------------------------------------------------------------
# DT AC1 -- approved bookings, tentative holds and unavailability are excluded,
# setup and turnaround time included
# ---------------------------------------------------------------------------


def test_ac1_an_approved_booking_overlapping_the_window_excludes_the_venue(client, db_session):
    headers = _coordinator(client, db_session)
    booked = _venue(db_session, "Booked Hall")
    _venue(db_session, "Free Hall")
    _booking(db_session, booked, _at(10), _at(12), status=BookingStatus.approved)

    assert _search(client, headers) == ["Free Hall"]


def test_ac1_a_tentative_hold_overlapping_the_window_excludes_the_venue(client, db_session):
    """A request still awaiting a Venue Staff decision is a tentative hold:
    the venue is spoken for until it is decided, so it is not offered as
    free to another Coordinator."""
    headers = _coordinator(client, db_session)
    held = _venue(db_session, "Held Hall")
    _venue(db_session, "Free Hall")
    _booking(db_session, held, _at(10), _at(12), status=BookingStatus.pending)

    assert _search(client, headers) == ["Free Hall"]


def test_ac1_an_unavailability_period_overlapping_the_window_excludes_the_venue(
    client, db_session
):
    headers = _coordinator(client, db_session)
    closed = _venue(db_session, "Closed Hall")
    _venue(db_session, "Free Hall")
    _block(db_session, closed, _at(12), _at(13))

    assert _search(client, headers) == ["Free Hall"]


@pytest.mark.parametrize(
    "end_minute,listed,case",
    [
        (45, False, "ends 08:45 -- 15 minutes left for 30 minutes of setup"),
        (30, True, "ends 08:30 -- exactly the 30 minutes of setup (boundary)"),
    ],
)
def test_ac1_setup_time_before_the_event_is_counted(client, db_session, end_minute, listed, case):
    """The room has to be prepared before the event starts, so a booking that
    ends too close to the window's start leaves no time to do it."""
    headers = _coordinator(client, db_session)
    venue = _venue(db_session, "Hall", setup_minutes=30)
    _booking(db_session, venue, _at(6), _minutes(8, end_minute))

    assert _search(client, headers) == (["Hall"] if listed else []), case


@pytest.mark.parametrize(
    "end_minute,listed,case",
    [
        (30, False, "ends 08:30 -- 30 minutes left for 60 minutes of reset"),
        (0, True, "ends 08:00 -- exactly the 60 minutes of reset (boundary)"),
    ],
)
def test_ac1_turnaround_time_after_an_earlier_booking_is_counted(
    client, db_session, end_minute, listed, case
):
    """After an event the room has to be reset before the next one can use it."""
    headers = _coordinator(client, db_session)
    venue = _venue(db_session, "Hall", turnaround_minutes=60)
    _booking(db_session, venue, _at(5), _minutes(8, end_minute))

    assert _search(client, headers) == (["Hall"] if listed else []), case


@pytest.mark.parametrize(
    "start_minute,listed,case",
    [
        (29, False, "starts 18:29 -- one minute short of turnaround + setup"),
        (30, True, "starts 18:30 -- exactly turnaround + setup after 17:00 (boundary)"),
    ],
)
def test_ac1_a_later_booking_needs_turnaround_and_setup_after_the_window(
    client, db_session, start_minute, listed, case
):
    """The searched event needs resetting after it (60) and the next one
    needs setting up before it (30): 90 minutes after 17:00."""
    headers = _coordinator(client, db_session)
    venue = _venue(db_session, "Hall", setup_minutes=30, turnaround_minutes=60)
    _booking(db_session, venue, _minutes(18, start_minute), _at(21))

    assert _search(client, headers) == (["Hall"] if listed else []), case


@pytest.mark.parametrize(
    "start,end,listed,case",
    [
        (_at(6), _minutes(8, 45), False, "maintenance until 08:45 -- setup starts 08:30"),
        (_at(6), _minutes(8, 30), True, "maintenance until 08:30 -- setup can start on time"),
        (_minutes(17, 30), _at(20), False, "maintenance from 17:30 -- reset runs to 18:00"),
        (_at(18), _at(20), True, "maintenance from 18:00 -- reset is done by then"),
    ],
)
def test_ac1_setup_and_turnaround_count_against_unavailability_too(
    client, db_session, start, end, listed, case
):
    """A closed room cannot be set up or reset either."""
    headers = _coordinator(client, db_session)
    venue = _venue(db_session, "Hall", setup_minutes=30, turnaround_minutes=60)
    _block(db_session, venue, start, end)

    assert _search(client, headers) == (["Hall"] if listed else []), case


@pytest.mark.parametrize(
    "status", [BookingStatus.approved, BookingStatus.pending], ids=["approved", "tentative hold"]
)
def test_ac1_a_booking_that_only_clashes_because_of_setup_and_turnaround_excludes_the_venue(
    client, db_session, status
):
    """Published times that do not touch the window at all -- 07:00-08:00 --
    still clash once the venue's 60 minutes of turnaround and 30 of setup
    are counted."""
    headers = _coordinator(client, db_session)
    venue = _venue(db_session, "Hall", setup_minutes=30, turnaround_minutes=60)
    _booking(db_session, venue, _at(7), _at(8), status=status)

    assert _search(client, headers) == []


def test_ac1_each_venue_is_padded_by_its_own_setup_and_turnaround(client, db_session):
    """The same booking times leave one venue out and not the other, because
    only one of them needs time to reset."""
    headers = _coordinator(client, db_session)
    slow = _venue(db_session, "Slow Hall", turnaround_minutes=120)
    quick = _venue(db_session, "Quick Hall")
    _booking(db_session, slow, _at(6), _at(8))
    _booking(db_session, quick, _at(6), _at(8))

    assert _search(client, headers) == ["Quick Hall"]


def test_ac1_a_window_given_in_singapore_time_is_compared_correctly(client, db_session):
    """17:00-01:00 Singapore time is 09:00-17:00 UTC, so a booking at
    10:00-12:00 UTC lies inside it."""
    headers = _coordinator(client, db_session)
    venue = _venue(db_session, "Hall")
    _booking(db_session, venue, _at(10), _at(12))

    res = client.get(
        "/venues",
        params={"start": "2026-11-02T17:00:00+08:00", "end": "2026-11-03T01:00:00+08:00"},
        headers=headers,
    )
    assert _names(res) == []


# ---------------------------------------------------------------------------
# DT AC2 -- rejected, cancelled and expired bookings do not exclude a venue
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    [BookingStatus.rejected, BookingStatus.cancelled, BookingStatus.hold_expired],
    ids=["rejected", "cancelled", "hold expired"],
)
def test_ac2_a_venue_whose_only_overlapping_booking_holds_nothing_is_still_shown(
    client, db_session, status
):
    headers = _coordinator(client, db_session)
    venue = _venue(db_session, "Hall", setup_minutes=30, turnaround_minutes=60)
    _booking(db_session, venue, _at(10), _at(12), status=status)

    assert _search(client, headers) == ["Hall"]


def test_ac2_one_live_booking_still_excludes_a_venue_that_also_has_dead_ones(client, db_session):
    """"Only" in AC2 matters: a rejected booking does not cancel out an
    approved one at the same time."""
    headers = _coordinator(client, db_session)
    venue = _venue(db_session, "Hall")
    _booking(db_session, venue, _at(10), _at(12), status=BookingStatus.rejected)
    _booking(db_session, venue, _at(10), _at(12), status=BookingStatus.hold_expired)
    _booking(db_session, venue, _at(13), _at(14), status=BookingStatus.approved)

    assert _search(client, headers) == []


def test_ac2_an_expired_hold_frees_the_venue_for_a_new_request(client, db_session):
    """Hold Expired is history, like Rejected: the event may ask for a venue
    again (sql/013 only allows one LIVE request per event)."""
    s = _setup(client, db_session)
    booking = db_session.get(VenueBooking, s["booking_id"])
    booking.status = BookingStatus.hold_expired
    db_session.commit()

    again = client.post(
        f"/venue-bookings/events/{s['event_id']}",
        json={"venue_id": s["venue"].id},
        headers=s["coord_h"],
    )
    assert again.status_code == 201, again.text
    assert again.json()["status"] == BookingStatus.pending


# ---------------------------------------------------------------------------
# DT AC3 -- an end earlier than the start is refused, naming the field
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "params,case",
    [
        ({"start": "2026-11-02T17:00:00Z", "end": "2026-11-02T09:00:00Z"}, "end before start"),
        ({"start": "2026-11-02T09:00:00Z", "end": "2026-11-02T09:00:00Z"}, "end equals start"),
    ],
)
def test_ac3_an_end_earlier_than_the_start_is_refused_and_the_end_is_flagged(
    client, db_session, params, case
):
    """Refused rather than ignored -- ignoring it would show venues as free
    for a time nobody asked about -- and the 422 names `end`, which is what
    the page uses to flag the field."""
    headers = _coordinator(client, db_session)
    _venue(db_session, "Hall")

    res = client.get("/venues", params=params, headers=headers)
    assert res.status_code == 422, case
    assert res.json()["detail"] == [
        {"loc": ["query", "end"], "msg": "The end must be after the start."}
    ]


# ---------------------------------------------------------------------------
# DT AC4 -- combined with other filters, only venues meeting all are shown
# ---------------------------------------------------------------------------


def test_ac4_the_date_filter_combines_with_every_other_filter(client, db_session):
    """One venue meets everything; each of the others fails exactly one
    criterion, so each criterion is proven to be applied alongside the rest."""
    headers = _coordinator(client, db_session)
    wanted = dict(
        location="Marina Bay",
        capacity=200,
        supported_layouts=["Theatre"],
        facilities=["Projector", "Stage"],
        accessibility_features=["Hearing loop"],
        setup_minutes=30,
        turnaround_minutes=30,
    )
    _venue(db_session, "Marina Match", **wanted)
    held = _venue(db_session, "Marina Held", **wanted)
    padded = _venue(db_session, "Marina Too Close", **wanted)
    _venue(db_session, "Marina Too Small", **{**wanted, "capacity": 50})
    _venue(db_session, "Marina Banquet Only", **{**wanted, "supported_layouts": ["Banquet"]})
    _venue(db_session, "Marina No Stage", **{**wanted, "facilities": ["Projector"]})
    _venue(db_session, "Marina No Loop", **{**wanted, "accessibility_features": []})
    _venue(db_session, "Jurong Match", **{**wanted, "location": "Jurong East"})
    _booking(db_session, held, _at(12), _at(13), status=BookingStatus.pending)
    _booking(db_session, padded, _at(6), _minutes(8, 45))  # inside setup + turnaround

    names = _search(
        client,
        headers,
        q="marina",
        min_capacity=150,
        layout="theatre",
        facilities=["Projector", "Stage"],
        accessibility=["Hearing loop"],
    )
    assert names == ["Marina Match"]


def test_ac4_without_a_date_the_same_filters_ignore_bookings(client, db_session):
    """Bookings only matter when a date and time are asked for."""
    headers = _coordinator(client, db_session)
    venue = _venue(db_session, "Hall", capacity=200)
    _booking(db_session, venue, _at(10), _at(12), status=BookingStatus.pending)

    res = client.get("/venues", params={"min_capacity": 150}, headers=headers)
    assert _names(res) == ["Hall"]


# ---------------------------------------------------------------------------
# What a Coordinator can see about a venue's setup and turnaround
# ---------------------------------------------------------------------------


def test_venue_details_show_setup_and_turnaround_time(client, db_session):
    headers = _coordinator(client, db_session)
    venue = _venue(db_session, "Hall", setup_minutes=45, turnaround_minutes=90)
    _venue(db_session, "Plain Hall")

    detail = client.get(f"/venues/{venue.id}", headers=headers).json()
    assert (detail["setup_minutes"], detail["turnaround_minutes"]) == (45, 90)
    plain = client.get("/venues", headers=headers).json()[1]
    assert client.get(f"/venues/{plain['id']}", headers=headers).json()["setup_minutes"] == 0


# ---------------------------------------------------------------------------
# Who may search by date
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", [Role.ORGANISER, Role.ATTENDEE, Role.TECH_SUPPORT])
def test_roles_outside_venue_planning_cannot_search_by_date(client, db_session, role):
    """Bookings and holds are internal: who has which venue when is not for
    Organisers, Attendees or Technical Support to browse."""
    headers = _headers(client, db_session, role, email=f"{role.value}@example.com")
    _venue(db_session, "Hall")

    assert client.get("/venues", params=WINDOW, headers=headers).status_code == 403


def test_venue_staff_can_search_by_date(client, db_session):
    headers = _headers(client, db_session, Role.VENUE_STAFF, email="staff@example.com")
    _venue(db_session, "Hall")

    assert _search(client, headers) == ["Hall"]


def test_an_anonymous_caller_cannot_search_by_date(client, db_session):
    assert client.get("/venues", params=WINDOW).status_code == 401


# ---------------------------------------------------------------------------
# Booking approval applies the same rule, so search and approval agree
# ---------------------------------------------------------------------------


def test_approval_refuses_a_booking_inside_the_venues_turnaround(client, db_session):
    """The venue search would not offer this slot, so Venue Staff cannot
    confirm it either: the first event ends 17:00 and the venue needs an
    hour to reset."""
    s = _setup(client, db_session)  # 2 Nov, 09:00-17:00
    s["venue"].turnaround_minutes = 60
    db_session.commit()
    second = _second_request_for_the_same_venue(
        client,
        db_session,
        s,
        proposed_start=datetime(2026, 11, 2, 17, 30, tzinfo=timezone.utc),
        proposed_end=datetime(2026, 11, 2, 20, 0, tzinfo=timezone.utc),
    )
    assert _approve(client, s["staff_h"], s["booking_id"]).status_code == 200

    res = _approve(client, s["staff_h"], second)
    assert res.status_code == 409
    assert "already booked" in res.json()["detail"]
    assert db_session.get(VenueBooking, second).status == BookingStatus.pending


def test_approval_allows_a_booking_exactly_one_turnaround_later(client, db_session):
    s = _setup(client, db_session)
    s["venue"].turnaround_minutes = 60
    db_session.commit()
    second = _second_request_for_the_same_venue(
        client,
        db_session,
        s,
        proposed_start=datetime(2026, 11, 2, 18, 0, tzinfo=timezone.utc),
        proposed_end=datetime(2026, 11, 2, 20, 0, tzinfo=timezone.utc),
    )
    assert _approve(client, s["staff_h"], s["booking_id"]).status_code == 200
    assert _approve(client, s["staff_h"], second).status_code == 200


def test_approval_is_not_blocked_by_another_tentative_hold_on_the_same_slot(client, db_session):
    """Two Coordinators may hold the same slot while their requests wait.
    Approving either must stay possible, or both would be stuck; once one is
    confirmed, the other is refused."""
    s = _setup(client, db_session)
    second = _second_request_for_the_same_venue(client, db_session, s)

    assert _approve(client, s["staff_h"], second).status_code == 200
    assert _approve(client, s["staff_h"], s["booking_id"]).status_code == 409
