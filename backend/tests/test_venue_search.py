"""Tests for the "Search and Filter Venues" story (Event Coordinator).

    As an Event Coordinator, I want to search for venues by keyword and
    filter them by my event's requirements, so that I can quickly narrow
    down venues worth reviewing.

Each test is named after the acceptance criterion it covers (VS AC1-AC5);
the mapping is in docs/test-cases-venue-search.md. Edge cases -- boundaries,
invalid input, overlap rules -- are tested here rather than written as
extra criteria.

The contract under test:

    GET /venues?q=&min_capacity=&layout=&facilities=&accessibility=&start=&end=
        With no parameters it returns exactly what it returned before this
        story: every venue, alphabetically, inactive ones included.

    GET /venues/filter-options
        The distinct layouts, facilities and accessibility features recorded
        for venues. These columns are free text, so the "fixed" choices the
        filters offer are whatever values have actually been recorded.
"""

import itertools
from datetime import datetime, timezone

import pytest

from app.core.roles import Role
from app.models.enums import BookingStatus
from app.models.events import Event
from app.models.user import User
from app.models.venues import Venue, VenueBooking, VenueUnavailability

_unique = itertools.count()


def _headers(client, db_session, role, email="coord@example.com"):
    """Register a user, promote them to `role`, and return auth headers.

    Registration always assigns `attendee` (by design -- a client can never
    pick its own role), so the role is set directly here. The re-login is
    what makes the returned token reflect the new role.
    """
    password = "password123"
    res = client.post(
        "/auth/register", json={"name": "Test User", "email": email, "password": password}
    )
    assert res.status_code == 201
    user = db_session.query(User).filter(User.email == email).one()
    user.role = role.value
    db_session.commit()
    token = client.post("/auth/login", json={"email": email, "password": password}).json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


def _coordinator(client, db_session):
    return _headers(client, db_session, Role.COORDINATOR)


def _venue(db_session, name, **overrides) -> Venue:
    """There is no endpoint that creates venues yet (VENUE_MANAGE is a
    separate story), so they go in through the model."""
    venue = Venue(
        name=name,
        location=overrides.pop("location", "1 Test Street"),
        capacity=overrides.pop("capacity", 100),
        supported_layouts=overrides.pop("supported_layouts", ["Theatre"]),
        facilities=overrides.pop("facilities", ["Projector"]),
        accessibility_features=overrides.pop("accessibility_features", ["Wheelchair access"]),
        operating_hours=overrides.pop("operating_hours", None),
        **overrides,
    )
    db_session.add(venue)
    db_session.commit()
    db_session.refresh(venue)
    return venue


def _someone(db_session) -> User:
    """A user to hang bookings and blocks off. Nothing reads them back."""
    user = User(
        name="Someone",
        email=f"someone{next(_unique)}@example.com",
        password_hash="x",
        role=Role.COORDINATOR.value,
    )
    db_session.add(user)
    db_session.flush()
    return user


def _booking(db_session, venue, start, end, status=BookingStatus.approved):
    """A booking of `venue` for [start, end).

    No endpoint creates bookings yet -- Venue Booking Request and Approval
    are separate stories -- so they are inserted directly, exactly as those
    stories will write them.
    """
    user = _someone(db_session)
    event = Event(name="Another event", organiser_id=user.id)
    db_session.add(event)
    db_session.flush()
    db_session.add(
        VenueBooking(
            event_id=event.id,
            venue_id=venue.id,
            requested_by=user.id,
            start_time=start,
            end_time=end,
            status=status,
        )
    )
    db_session.commit()


def _block(db_session, venue, start, end):
    """A recorded unavailability period (maintenance, renovation, ...)."""
    user = _someone(db_session)
    db_session.add(
        VenueUnavailability(
            venue_id=venue.id, start_time=start, end_time=end, reason="Maintenance",
            created_by=user.id,
        )
    )
    db_session.commit()


def _at(hour, day=2):
    """A moment on 2 Nov 2026, in UTC."""
    return datetime(2026, 11, day, hour, tzinfo=timezone.utc)


# The window every date test searches for: 2 Nov 2026, 09:00-17:00 UTC.
WINDOW = {"start": "2026-11-02T09:00:00Z", "end": "2026-11-02T17:00:00Z"}


def _names(res):
    assert res.status_code == 200, res.text
    return [venue["name"] for venue in res.json()]


# ---------------------------------------------------------------------------
# No criteria -- the page before anything is typed must be unchanged
# ---------------------------------------------------------------------------


def test_no_criteria_returns_every_venue_alphabetically(client, db_session):
    """Searching is additive: with nothing entered, the list is exactly what
    it was before this story -- every venue, by name, inactive included."""
    headers = _coordinator(client, db_session)
    _venue(db_session, "Suntec Hall")
    _venue(db_session, "Changi Suite", is_active=False)
    _venue(db_session, "Marina Ballroom")

    assert _names(client.get("/venues", headers=headers)) == [
        "Changi Suite",
        "Marina Ballroom",
        "Suntec Hall",
    ]


# ---------------------------------------------------------------------------
# VS AC1 -- keyword matches name or location
# ---------------------------------------------------------------------------


def test_ac1_keyword_matches_the_name_partially_and_in_any_case(client, db_session):
    headers = _coordinator(client, db_session)
    _venue(db_session, "Marina Grand Ballroom")
    _venue(db_session, "Suntec Hall")

    assert _names(client.get("/venues?q=GRAND", headers=headers)) == ["Marina Grand Ballroom"]


def test_ac1_keyword_matches_the_location(client, db_session):
    """Location has no fixed regions -- it is a free-text address -- so the
    keyword is how a Coordinator searches by location."""
    headers = _coordinator(client, db_session)
    _venue(db_session, "Conference Hall A", location="10 Bayfront Ave, Marina Bay")
    _venue(db_session, "Suntec Hall", location="1 Raffles Boulevard")

    assert _names(client.get("/venues?q=marina", headers=headers)) == ["Conference Hall A"]


def test_ac1_keyword_with_no_match_returns_an_empty_list(client, db_session):
    headers = _coordinator(client, db_session)
    _venue(db_session, "Suntec Hall")

    assert _names(client.get("/venues?q=nowhere", headers=headers)) == []


def test_ac1_a_blank_keyword_is_no_keyword(client, db_session):
    """Spaces are not a search -- they must not filter everything out."""
    headers = _coordinator(client, db_session)
    _venue(db_session, "Suntec Hall")

    assert _names(client.get("/venues?q=%20%20%20", headers=headers)) == ["Suntec Hall"]


# ---------------------------------------------------------------------------
# VS AC2 -- layout, accessibility and facilities; every filter must hold
# ---------------------------------------------------------------------------


def test_ac2_layout_filter_matches_in_any_case(client, db_session):
    headers = _coordinator(client, db_session)
    _venue(db_session, "Theatre Hall", supported_layouts=["Theatre", "Classroom"])
    _venue(db_session, "Boardroom Suite", supported_layouts=["Boardroom"])

    assert _names(client.get("/venues?layout=theatre", headers=headers)) == ["Theatre Hall"]


def test_ac2_a_venue_must_have_every_selected_facility(client, db_session):
    """An event that needs a projector AND video conferencing is not served
    by a room with only one of them."""
    headers = _coordinator(client, db_session)
    _venue(db_session, "Both", facilities=["Projector", "Video conferencing", "Whiteboard"])
    _venue(db_session, "Projector only", facilities=["Projector"])
    _venue(db_session, "Neither", facilities=["Stage"])

    res = client.get(
        "/venues?facilities=Projector&facilities=Video%20conferencing", headers=headers
    )

    assert _names(res) == ["Both"]


def test_ac2_facility_matching_ignores_case(client, db_session):
    """These values are typed in by Venue Staff, so capitalisation is not
    something a Coordinator's filter should trip over."""
    headers = _coordinator(client, db_session)
    _venue(db_session, "Hall", facilities=["Projector"])
    # Without a second venue that must be filtered OUT, this would pass even
    # if the facility filter were ignored entirely.
    _venue(db_session, "Stage only", facilities=["Stage"])

    assert _names(client.get("/venues?facilities=projector", headers=headers)) == ["Hall"]


def test_ac2_a_venue_must_have_every_selected_accessibility_feature(client, db_session):
    headers = _coordinator(client, db_session)
    _venue(db_session, "Both", accessibility_features=["Wheelchair access", "Hearing loop"])
    _venue(db_session, "Ramp only", accessibility_features=["Wheelchair access"])
    _venue(db_session, "None recorded", accessibility_features=[])

    res = client.get(
        "/venues?accessibility=Wheelchair%20access&accessibility=Hearing%20loop", headers=headers
    )

    assert _names(res) == ["Both"]


def test_ac2_keyword_and_every_kind_of_filter_combine(client, db_session):
    """All criteria are AND: only the venue meeting every one survives."""
    headers = _coordinator(client, db_session)
    target = _venue(
        db_session, "Marina Hall", capacity=300, supported_layouts=["Theatre"],
        facilities=["Projector", "Stage"], accessibility_features=["Hearing loop"],
    )
    _venue(db_session, "Marina Too Small", capacity=50, supported_layouts=["Theatre"],
           facilities=["Projector", "Stage"], accessibility_features=["Hearing loop"])
    _venue(db_session, "Marina Wrong Layout", capacity=300, supported_layouts=["Banquet"],
           facilities=["Projector", "Stage"], accessibility_features=["Hearing loop"])
    _venue(db_session, "Marina No Stage", capacity=300, supported_layouts=["Theatre"],
           facilities=["Projector"], accessibility_features=["Hearing loop"])
    _venue(db_session, "Suntec Hall", capacity=300, supported_layouts=["Theatre"],
           facilities=["Projector", "Stage"], accessibility_features=["Hearing loop"])
    booked = _venue(db_session, "Marina Booked", capacity=300, supported_layouts=["Theatre"],
                    facilities=["Projector", "Stage"], accessibility_features=["Hearing loop"])
    _booking(db_session, booked, _at(10), _at(12))

    res = client.get(
        "/venues",
        params={
            "q": "marina", "min_capacity": 120, "layout": "Theatre",
            "facilities": ["Projector", "Stage"], "accessibility": ["Hearing loop"],
            **WINDOW,
        },
        headers=headers,
    )

    assert _names(res) == [target.name]


# ---------------------------------------------------------------------------
# VS AC3 -- date and time: venues booked or blocked in the window are excluded
# ---------------------------------------------------------------------------


def test_ac3_an_approved_booking_overlapping_the_window_excludes_the_venue(client, db_session):
    headers = _coordinator(client, db_session)
    booked = _venue(db_session, "Booked Hall")
    _venue(db_session, "Free Hall")
    _booking(db_session, booked, _at(10), _at(12))

    assert _names(client.get("/venues", params=WINDOW, headers=headers)) == ["Free Hall"]


@pytest.mark.parametrize(
    "status", [BookingStatus.pending, BookingStatus.rejected, BookingStatus.cancelled]
)
def test_ac3_a_booking_that_is_not_approved_does_not_block(client, db_session, status):
    """Only a confirmed booking takes a venue out of the running.

    W4 p4, Booking Conflict Detection: "A confirmed booking should affect
    whether that venue is considered available." A rejected or cancelled
    booking never will be; a pending one is not yet.

    PROVISIONAL for `pending`: booking requests and approval are separate
    stories, not built yet. If that story decides a pending request should
    hold the venue, this case flips -- a one-line change in the search.
    """
    headers = _coordinator(client, db_session)
    venue = _venue(db_session, "Hall")
    _booking(db_session, venue, _at(10), _at(12), status=status)

    assert _names(client.get("/venues", params=WINDOW, headers=headers)) == ["Hall"]


def test_ac3_a_recorded_unavailability_overlapping_the_window_excludes_the_venue(
    client, db_session
):
    """A venue closed for maintenance is not free, whatever its bookings say.
    W4 p3, Venue Availability Calendar: "other recorded periods of
    unavailability should be reflected"."""
    headers = _coordinator(client, db_session)
    blocked = _venue(db_session, "Blocked Hall")
    _venue(db_session, "Free Hall")
    _block(db_session, blocked, _at(8), _at(20))

    assert _names(client.get("/venues", params=WINDOW, headers=headers)) == ["Free Hall"]


@pytest.mark.parametrize(
    "start,end,case",
    [
        (_at(7), _at(10), "starts before, ends inside"),
        (_at(16), _at(19), "starts inside, ends after"),
        (_at(11), _at(13), "entirely inside the window"),
        (_at(6), _at(22), "covers the whole window"),
    ],
)
def test_ac3_every_kind_of_overlap_excludes_the_venue(client, db_session, start, end, case):
    headers = _coordinator(client, db_session)
    venue = _venue(db_session, "Hall")
    _booking(db_session, venue, start, end)

    assert _names(client.get("/venues", params=WINDOW, headers=headers)) == [], case


@pytest.mark.parametrize(
    "start,end,case",
    [
        (_at(6), _at(8), "ends before the window"),
        (_at(18), _at(20), "starts after the window"),
        (_at(9, day=1), _at(17, day=1), "same hours, the day before"),
    ],
)
def test_ac3_a_booking_outside_the_window_does_not_block(client, db_session, start, end, case):
    headers = _coordinator(client, db_session)
    venue = _venue(db_session, "Hall")
    _booking(db_session, venue, start, end)

    assert _names(client.get("/venues", params=WINDOW, headers=headers)) == ["Hall"], case


@pytest.mark.parametrize(
    "start,end,case",
    [
        (_at(6), _at(9), "ends exactly when the window starts"),
        (_at(17), _at(20), "starts exactly when the window ends"),
    ],
)
def test_ac3_back_to_back_is_not_an_overlap(client, db_session, start, end, case):
    """Boundary: a morning session ending at 09:00 leaves the room free for
    one starting at 09:00. Setup and turnaround time are a separate feature
    and are not part of this rule."""
    headers = _coordinator(client, db_session)
    venue = _venue(db_session, "Hall")
    _booking(db_session, venue, start, end)

    assert _names(client.get("/venues", params=WINDOW, headers=headers)) == ["Hall"], case


def test_ac3_a_booking_of_another_venue_changes_nothing(client, db_session):
    headers = _coordinator(client, db_session)
    other = _venue(db_session, "Other Hall")
    _venue(db_session, "Our Hall")
    _booking(db_session, other, _at(10), _at(12))

    assert _names(client.get("/venues", params=WINDOW, headers=headers)) == ["Our Hall"]


@pytest.mark.parametrize(
    "params,case",
    [
        ({"start": "2026-11-02T17:00:00Z", "end": "2026-11-02T09:00:00Z"}, "end before start"),
        ({"start": "2026-11-02T09:00:00Z", "end": "2026-11-02T09:00:00Z"}, "end equals start"),
        ({"start": "2026-11-02T09:00:00Z"}, "start without an end"),
        ({"end": "2026-11-02T17:00:00Z"}, "end without a start"),
        ({"start": "not-a-date", "end": "2026-11-02T17:00:00Z"}, "unreadable date"),
    ],
)
def test_ac3_an_invalid_time_window_is_rejected(client, db_session, params, case):
    """A half-given or back-to-front window is a mistake, not a search. It is
    rejected rather than silently ignored, which would show venues as free
    for a period nobody actually asked about."""
    headers = _coordinator(client, db_session)
    _venue(db_session, "Hall")

    assert client.get("/venues", params=params, headers=headers).status_code == 422, case


# ---------------------------------------------------------------------------
# VS AC3 -- expected attendance: venues below that capacity are excluded
# ---------------------------------------------------------------------------


def test_ac3_venues_below_the_expected_attendance_are_excluded(client, db_session):
    headers = _coordinator(client, db_session)
    _venue(db_session, "Small", capacity=80)
    _venue(db_session, "Large", capacity=600)

    assert _names(client.get("/venues?min_capacity=120", headers=headers)) == ["Large"]


def test_ac3_a_venue_exactly_at_the_expected_attendance_is_included(client, db_session):
    """Boundary: 120 people fit in a room that holds 120."""
    headers = _coordinator(client, db_session)
    _venue(db_session, "Exact", capacity=120)
    _venue(db_session, "One short", capacity=119)

    assert _names(client.get("/venues?min_capacity=120", headers=headers)) == ["Exact"]


@pytest.mark.parametrize("value", ["0", "-5", "lots"])
def test_ac3_an_attendance_that_is_not_a_positive_number_is_rejected(client, db_session, value):
    headers = _coordinator(client, db_session)
    _venue(db_session, "Hall")

    assert client.get(f"/venues?min_capacity={value}", headers=headers).status_code == 422


# ---------------------------------------------------------------------------
# VS AC4 -- each result shows name, location, capacity and facilities
# ---------------------------------------------------------------------------


def test_ac4_each_result_carries_name_location_capacity_and_facilities(client, db_session):
    headers = _coordinator(client, db_session)
    _venue(
        db_session, "Marina Grand Ballroom", location="10 Bayfront Ave, Level 3", capacity=600,
        facilities=["Stage", "Built-in PA system"],
    )

    row = client.get("/venues", headers=headers).json()[0]

    assert row["name"] == "Marina Grand Ballroom"
    assert row["location"] == "10 Bayfront Ave, Level 3"
    assert row["capacity"] == 600
    assert row["facilities"] == ["Stage", "Built-in PA system"]


def test_ac4_an_inactive_venue_matching_the_filters_is_still_listed_and_flagged(
    client, db_session
):
    """Consistent with the plain list: a Coordinator is better told a venue
    is inactive than left wondering where it went."""
    headers = _coordinator(client, db_session)
    _venue(db_session, "Changi Suite", capacity=300, is_active=False)
    # Proves the filter actually ran: this one is too small and must go,
    # while the inactive venue that fits must stay.
    _venue(db_session, "Tiny Room", capacity=20)

    rows = client.get("/venues?min_capacity=100", headers=headers).json()

    assert [(r["name"], r["is_active"]) for r in rows] == [("Changi Suite", False)]


# ---------------------------------------------------------------------------
# Filter options -- where the "fixed" choices come from
# ---------------------------------------------------------------------------


def test_filter_options_list_every_recorded_value_once_sorted(client, db_session):
    headers = _coordinator(client, db_session)
    _venue(db_session, "A", supported_layouts=["Theatre", "Banquet"],
           facilities=["Stage", "Projector"], accessibility_features=["Hearing loop"])
    _venue(db_session, "B", supported_layouts=["Boardroom", "Theatre"],
           facilities=["Projector", "Whiteboard"],
           accessibility_features=["Wheelchair access", "Hearing loop"])

    res = client.get("/venues/filter-options", headers=headers)

    assert res.status_code == 200, res.text
    assert res.json() == {
        "layouts": ["Banquet", "Boardroom", "Theatre"],
        "facilities": ["Projector", "Stage", "Whiteboard"],
        "accessibility_features": ["Hearing loop", "Wheelchair access"],
    }


def test_filter_options_treat_different_capitalisation_as_one_value(client, db_session):
    """Matching ignores case, so listing "Projector" and "projector" as two
    options would offer two choices that return identical results."""
    headers = _coordinator(client, db_session)
    _venue(db_session, "A", facilities=["Projector"])
    _venue(db_session, "B", facilities=["projector"])

    facilities = client.get("/venues/filter-options", headers=headers).json()["facilities"]

    assert len(facilities) == 1
    assert facilities[0].lower() == "projector"


def test_filter_options_include_values_only_an_inactive_venue_has(client, db_session):
    """Inactive venues appear in results, so their values must be choosable."""
    headers = _coordinator(client, db_session)
    _venue(db_session, "Changi Suite", facilities=["Conference phone"], is_active=False)

    facilities = client.get("/venues/filter-options", headers=headers).json()["facilities"]

    assert facilities == ["Conference phone"]


def test_filter_options_are_empty_lists_when_there_are_no_venues(client, db_session):
    headers = _coordinator(client, db_session)

    assert client.get("/venues/filter-options", headers=headers).json() == {
        "layouts": [],
        "facilities": [],
        "accessibility_features": [],
    }


# ---------------------------------------------------------------------------
# Who may search -- unchanged from View Venue Details
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", [Role.ORGANISER, Role.ATTENDEE, Role.TECH_SUPPORT])
def test_roles_outside_venue_planning_cannot_read_filter_options(client, db_session, role):
    """Same gate as the venue list: internal venue planners only. Attendees
    hold VENUE_READ, which is exactly why the gate is on role."""
    headers = _headers(client, db_session, role, email=f"{role.value}@example.com")

    assert client.get("/venues/filter-options", headers=headers).status_code == 403


def test_venue_staff_can_read_filter_options(client, db_session):
    headers = _headers(client, db_session, Role.VENUE_STAFF, email="staff@example.com")

    assert client.get("/venues/filter-options", headers=headers).status_code == 200


@pytest.mark.parametrize("path", ["/venues?q=marina", "/venues/filter-options"])
def test_an_anonymous_caller_is_unauthenticated(client, db_session, path):
    assert client.get(path).status_code == 401
