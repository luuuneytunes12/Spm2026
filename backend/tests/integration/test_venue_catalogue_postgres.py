"""Finding and judging Venues on real PostgreSQL:

    SCRUM-35  Search and Filter Venues
    SCRUM-36  View Venue Details
    SCRUM-37  View Venue Availability Calendar
    SCRUM-58  Check Venue Suitability for an Event
    SCRUM-104 Check Venue Suitability Per Venue Booking

The SQLite tests (tests/test_venue_search.py, test_venues.py,
test_venue_availability_calendar.py, test_venue_suitability.py) store the
venue lists -- facilities, layouts, accessibility -- as JSON. Production
stores them as Postgres text[] arrays, and the keyword search is an ILIKE
with escaping. These prove search, filters, details, the calendar and the
suitability checks read those real columns correctly, with timestamptz
windows and every request in its own session.
"""

from datetime import datetime, timedelta, timezone
"""Venue catalogue management (SCRUM-108) on real PostgreSQL: the new columns,
the venue_activity table and the case-insensitive unique name index in
db/schema.sql, plus two Venue Staff adding the same name at the same instant."""

import pytest

from app.core.roles import Role
from app.models.enums import BookingStatus, EventStatus
from app.models.events import Event
from app.models.venues import Venue, VenueBooking, VenueUnavailability
from tests.integration.conftest import assign_event, submit_event

pytestmark = pytest.mark.integration

SGT = timezone(timedelta(hours=8))


@pytest.fixture()
def venues(db):
    rows = [
        Venue(name="Main Hall", location="Block A, Level 1", capacity=300,
              facilities=["Projector", "PA System", "Stage"], supported_layouts=["Theatre", "Banquet"],
              accessibility_features=["Step-free access", "Hearing loop"], operating_hours="08:00-22:00",
              emergency_access="Two exits to the car park", known_restrictions="No open flames"),
        Venue(name="Seminar Room 3", location="Block B, Level 2", capacity=40,
              facilities=["Projector", "Whiteboard"], supported_layouts=["Classroom", "U-shape"],
              accessibility_features=["Step-free access"], operating_hours="09:00-18:00"),
        Venue(name="Rooftop Garden", location="Block A, Roof", capacity=120,
              facilities=["PA System"], supported_layouts=["Cocktail"], accessibility_features=[],
              operating_hours="10:00-20:00"),
        Venue(name="100% Lab", location="Block C", capacity=25, facilities=[], supported_layouts=[],
              accessibility_features=[], is_active=False),
    ]
    db.add_all(rows)
    db.commit()
    return {v.name: v.id for v in rows}


@pytest.fixture()
def coordinator_h(make_user):
    return make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")[1]


def _names(res):
    assert res.status_code == 200, res.text
    return [v["name"] for v in res.json()]


# --------------------------------------------------------------------------
# SCRUM-35 Search and Filter Venues
# --------------------------------------------------------------------------


def test_scrum35_ac1_keyword_matches_name_or_location_case_insensitively(client, venues, coordinator_h):
    assert _names(client.get("/venues", params={"q": "hall"}, headers=coordinator_h)) == ["Main Hall"]
    assert _names(client.get("/venues", params={"q": "BLOCK A"}, headers=coordinator_h)) == ["Main Hall", "Rooftop Garden"]
    assert _names(client.get("/venues", params={"q": "nowhere"}, headers=coordinator_h)) == []


def test_scrum35_ac1_a_typed_percent_sign_is_matched_literally_not_as_a_wildcard(client, venues, coordinator_h):
    assert _names(client.get("/venues", params={"q": "100%"}, headers=coordinator_h)) == ["100% Lab"]
    assert _names(client.get("/venues", params={"q": "%"}, headers=coordinator_h)) == ["100% Lab"]


def test_scrum35_ac2_every_selected_filter_must_hold_on_the_array_columns(client, venues, coordinator_h):
    both = client.get("/venues", params={"facilities": ["projector", "PA SYSTEM"]}, headers=coordinator_h)
    assert _names(both) == ["Main Hall"]
    combined = client.get("/venues", params={"facilities": ["Projector"], "accessibility": ["Step-free access"],
                                             "layout": "classroom"}, headers=coordinator_h)
    assert _names(combined) == ["Seminar Room 3"]
    assert _names(client.get("/venues", params={"accessibility": ["Hearing loop", "Braille"]},
                             headers=coordinator_h)) == []


def test_scrum35_ac3_capacity_below_the_value_is_excluded_and_equal_is_kept(client, venues, coordinator_h):
    assert _names(client.get("/venues", params={"min_capacity": 120}, headers=coordinator_h)) == ["Main Hall", "Rooftop Garden"]
    assert client.get("/venues", params={"min_capacity": 0}, headers=coordinator_h).status_code == 422


def test_scrum35_ac4_each_result_carries_name_location_capacity_and_facilities(client, venues, coordinator_h):
    [row] = client.get("/venues", params={"q": "Seminar"}, headers=coordinator_h).json()

    assert row["location"] == "Block B, Level 2" and row["capacity"] == 40
    assert row["facilities"] == ["Projector", "Whiteboard"] and row["is_active"] is True


def test_scrum35_filter_options_are_drawn_from_every_venue(client, venues, coordinator_h):
    options = client.get("/venues/filter-options", headers=coordinator_h).json()

    assert {"Theatre", "Classroom", "Cocktail"} <= set(options["layouts"])
    assert {"Projector", "Whiteboard", "Stage"} <= set(options["facilities"])


def test_scrum35_scrum36_venues_are_internal_only(client, venues, make_user):
    for role in (Role.ORGANISER, Role.ATTENDEE, Role.TECH_SUPPORT, Role.SAFETY_OFFICER):
        _u, headers = make_user(role, f"{role.value}@connectsphere.test")
        assert client.get("/venues", headers=headers).status_code == 403, role
        assert client.get(f"/venues/{venues['Main Hall']}", headers=headers).status_code == 403, role


# --------------------------------------------------------------------------
# SCRUM-36 View Venue Details
# --------------------------------------------------------------------------


def test_scrum36_ac1_to_ac3_details_round_trip_from_the_array_columns(client, venues, coordinator_h, make_user):
    _v, staff_h = make_user(Role.VENUE_STAFF, "vic@connectsphere.test", "Vic Venue")

    for headers in (coordinator_h, staff_h):
        detail = client.get(f"/venues/{venues['Main Hall']}", headers=headers).json()
        assert (detail["name"], detail["location"], detail["capacity"]) == ("Main Hall", "Block A, Level 1", 300)
        assert detail["supported_layouts"] == ["Theatre", "Banquet"]
        assert detail["facilities"] == ["Projector", "PA System", "Stage"]
        assert detail["accessibility_features"] == ["Step-free access", "Hearing loop"]
        assert detail["operating_hours"] == "08:00-22:00"

    empty = client.get(f"/venues/{venues['100% Lab']}", headers=coordinator_h).json()
    assert empty["accessibility_features"] == [] and empty["is_active"] is False
    assert client.get("/venues/999999", headers=coordinator_h).status_code == 404


# --------------------------------------------------------------------------
# SCRUM-37 View Venue Availability Calendar
# --------------------------------------------------------------------------


def _calendar_world(client, make_user, db, venues):
    organiser, org_h = make_user(Role.ORGANISER, "org@connectsphere.test", "Olivia Organiser")
    sam, _ = make_user(Role.COORDINATOR, "sam2@connectsphere.test", "Sam Two")
    staff, staff_h = make_user(Role.VENUE_STAFF, "vic@connectsphere.test", "Vic Venue")
    hall = venues["Main Hall"]
    event_id = submit_event(client, org_h, name="Partner Day")
    db.get(Event, event_id).status = EventStatus.planning_event
    db.add_all([
        VenueBooking(event_id=event_id, venue_id=hall, requested_by=sam.id, status=BookingStatus.approved,
                     start_time=datetime(2026, 11, 2, 9, tzinfo=SGT), end_time=datetime(2026, 11, 2, 12, tzinfo=SGT)),
        VenueUnavailability(venue_id=hall, created_by=staff.id, reason_category="Maintenance",
                            reason="Aircon servicing",
                            start_time="2026-11-05T00:00:00Z", end_time="2026-11-06T00:00:00Z"),
    ])
    # Never on the calendar: requests not yet decided, or turned down.
    for i, status in enumerate((BookingStatus.pending, BookingStatus.rejected)):
        other = submit_event(client, org_h, name=f"Other {i}")
        db.add(VenueBooking(event_id=other, venue_id=hall, requested_by=sam.id, status=status,
                            start_time="2026-11-03T09:00:00Z", end_time="2026-11-03T12:00:00Z"))
    db.commit()
    return hall, staff_h, event_id


def test_scrum37_ac1_to_ac3_confirmed_bookings_and_closures_are_on_the_calendar(client, make_user, db, venues, coordinator_h):
    hall, staff_h, event_id = _calendar_world(client, make_user, db, venues)
    window = {"start": "2026-11-01T00:00:00Z", "end": "2026-11-08T00:00:00Z"}

    seen = client.get(f"/venues/{hall}/availability", params=window, headers=coordinator_h).json()

    kinds = sorted(i["kind"] for i in seen["items"])
    assert kinds == ["confirmed_booking", "unavailability"]
    booking = next(i for i in seen["items"] if i["kind"] == "confirmed_booking")
    assert booking["start_time"].startswith("2026-11-02T01:00")  # +08:00 stored as one instant
    closure = next(i for i in seen["items"] if i["kind"] == "unavailability")
    assert closure["reason_category"] == "Maintenance"
    # A Coordinator sees that it is taken, Venue Staff also see by whom.
    assert booking["event_name"] is None
    staff_view = client.get(f"/venues/{hall}/availability", params=window, headers=staff_h).json()
    assert next(i for i in staff_view["items"] if i["kind"] == "confirmed_booking")["event_name"] == "Partner Day"


def test_scrum37_ac4_the_date_range_narrows_what_is_shown(client, make_user, db, venues, coordinator_h):
    hall, _sh, _e = _calendar_world(client, make_user, db, venues)

    only_closure = client.get(f"/venues/{hall}/availability", headers=coordinator_h,
                              params={"start": "2026-11-04T00:00:00Z", "end": "2026-11-07T00:00:00Z"}).json()
    assert [i["kind"] for i in only_closure["items"]] == ["unavailability"]
    nothing = client.get(f"/venues/{hall}/availability", headers=coordinator_h,
                         params={"start": "2026-12-01T00:00:00Z", "end": "2026-12-31T00:00:00Z"}).json()
    assert nothing["items"] == [] and nothing["busy"] == []
    backwards = client.get(f"/venues/{hall}/availability", headers=coordinator_h,
                           params={"start": "2026-11-07T00:00:00Z", "end": "2026-11-04T00:00:00Z"})
    assert backwards.status_code == 422


# --------------------------------------------------------------------------
# SCRUM-58 / SCRUM-104 Venue suitability
# --------------------------------------------------------------------------


def _assigned(client, make_user, db, **event_fields):
    _o, org_h = make_user(Role.ORGANISER, "org@connectsphere.test", "Olivia Organiser")
    coordinator, coord_h = make_user(Role.COORDINATOR, "cora@connectsphere.test", "Cora Coord")
    _l, lead_h = make_user(Role.COORDINATOR_LEAD, "lena@connectsphere.test", "Lena Lead")
    event_id = submit_event(client, org_h, **event_fields)
    assign_event(client, lead_h, event_id, coordinator.id)
    return coordinator, coord_h, event_id


def test_scrum58_ac1_ac2_a_venue_meeting_every_requirement_is_suitable(client, make_user, db, venues):
    _c, coord_h, event_id = _assigned(client, make_user, db, expected_attendance=250,
                                      room_layout_preference="theatre",
                                      accessibility_needs="Step-free access, hearing loop",
                                      venue_requirements="Projector; Stage", **IN_HOURS)

    res = client.get(f"/venues/{venues['Main Hall']}/suitability/{event_id}", headers=coord_h).json()

    assert res["suitable"] is True
    assert {c["category"] for c in res["checks"]} == {"capacity", "layout", "accessibility", "facility", "operating_hours"}
    assert all(c["met"] for c in res["checks"])


def test_scrum58_ac3_each_unmet_requirement_is_named(client, make_user, db, venues):
    _c, coord_h, event_id = _assigned(client, make_user, db, expected_attendance=250,
                                      room_layout_preference="Theatre",
                                      accessibility_needs="Hearing loop", venue_requirements="Stage", **IN_HOURS)

    res = client.get(f"/venues/{venues['Seminar Room 3']}/suitability/{event_id}", headers=coord_h).json()

    assert res["suitable"] is False
    unmet = {c["category"]: c["message"] for c in res["checks"] if not c["met"]}
    assert set(unmet) == {"capacity", "layout", "accessibility", "facility"}
    assert "Capacity 40 < attendance 250" in unmet["capacity"]


def test_scrum58_only_the_assigned_coordinator_can_run_the_check(client, make_user, db, venues):
    _c, _ch, event_id = _assigned(client, make_user, db)
    _x, other_h = make_user(Role.COORDINATOR, "priya@connectsphere.test", "Priya Nair")

    assert client.get(f"/venues/{venues['Main Hall']}/suitability/{event_id}", headers=other_h).status_code == 404


# 10:00-16:00 at the venue, inside every fixture venue's operating hours.
IN_HOURS = {"proposed_start": "2026-11-02T02:00:00Z", "proposed_end": "2026-11-02T08:00:00Z"}


def _book(db, event_id, coordinator, venue_id, start="2026-11-02T02:00:00Z", end="2026-11-02T08:00:00Z", **needs):
    booking = VenueBooking(event_id=event_id, venue_id=venue_id, requested_by=coordinator.id,
                           status=BookingStatus.pending, start_time=start, end_time=end, **needs)
    db.add(booking)
    db.commit()
    return booking.id


def test_scrum104_ac1_ac2_each_booking_is_judged_on_its_own_needs(client, make_user, db, venues):
    coordinator, coord_h, event_id = _assigned(client, make_user, db, expected_attendance=100,
                                               accessibility_needs="Step-free access",
                                               venue_requirements="Projector")
    plenary = _book(db, event_id, coordinator, venues["Main Hall"], expected_attendance=100)
    breakout = _book(db, event_id, coordinator, venues["Seminar Room 3"], expected_attendance=40)
    garden = _book(db, event_id, coordinator, venues["Rooftop Garden"], expected_attendance=60,
                   facilities_needs="PA System")

    res = client.get(f"/venues/events/{event_id}/suitability", headers=coord_h).json()

    by_id = {v["booking_id"]: v for v in res["venues"]}
    assert by_id[plenary]["suitable"] is True and by_id[breakout]["suitable"] is True
    assert by_id[garden]["suitable"] is False
    unmet = [c for c in by_id[garden]["checks"] if not c["met"]]
    assert [c["category"] for c in unmet] == ["accessibility"]  # its own facility need IS met
    assert res["combined_capacity"]["available_capacity"] == 300 + 40 + 120


def test_operating_hours_ac1_ac2_ac3_are_judged_on_the_venues_clock(client, make_user, db, venues):
    coordinator, coord_h, event_id = _assigned(client, make_user, db, expected_attendance=30,
                                               accessibility_needs="Step-free access",
                                               venue_requirements="Projector", **IN_HOURS)
    # 11:00-13:00 UTC is 19:00-21:00 at the venue: open till 22:00, closed from
    # 18:00, and both the other way round if the times were read as UTC.
    open_late = _book(db, event_id, coordinator, venues["Main Hall"],
                      start="2026-11-02T11:00:00Z", end="2026-11-02T13:00:00Z")
    closed = _book(db, event_id, coordinator, venues["Seminar Room 3"],
                   start="2026-11-02T11:00:00Z", end="2026-11-02T13:00:00Z")

    res = client.get(f"/venues/events/{event_id}/suitability", headers=coord_h).json()

    by_id = {v["booking_id"]: v for v in res["venues"]}
    assert by_id[open_late]["suitable"] is True
    assert by_id[closed]["suitable"] is False
    assert [c["message"] for c in by_id[closed]["checks"] if not c["met"]] == ["Outside operating hours"]


def test_scrum104_ac2_a_failing_booking_shows_the_capacity_shortfall(client, make_user, db, venues):
    coordinator, coord_h, event_id = _assigned(client, make_user, db, expected_attendance=100)
    breakout = _book(db, event_id, coordinator, venues["Seminar Room 3"], expected_attendance=41)

    item = client.get(f"/venues/bookings/{breakout}/suitability", headers=coord_h).json()

    capacity = next(c for c in item["checks"] if c["category"] == "capacity")
    assert item["suitable"] is False and "Capacity 40 < attendance 41" in capacity["message"]


def test_scrum104_ac3_rechecking_one_booking_uses_its_new_values_and_leaves_the_rest(client, make_user, db, venues):
    coordinator, coord_h, event_id = _assigned(client, make_user, db, expected_attendance=100,
                                               accessibility_needs="Step-free access",
                                               venue_requirements="Projector")
    plenary = _book(db, event_id, coordinator, venues["Main Hall"], expected_attendance=100)
    breakout = _book(db, event_id, coordinator, venues["Seminar Room 3"], expected_attendance=60)
    before = client.get(f"/venues/events/{event_id}/suitability", headers=coord_h).json()
    assert {v["booking_id"]: v["suitable"] for v in before["venues"]} == {plenary: True, breakout: False}

    db.get(VenueBooking, breakout).expected_attendance = 35
    db.commit()

    assert client.get(f"/venues/bookings/{breakout}/suitability", headers=coord_h).json()["suitable"] is True
    after = client.get(f"/venues/events/{event_id}/suitability", headers=coord_h).json()
    assert {v["booking_id"]: v["suitable"] for v in after["venues"]} == {plenary: True, breakout: True}


def test_scrum104_cancelled_and_rejected_bookings_are_not_judged(client, make_user, db, venues):
    coordinator, coord_h, event_id = _assigned(client, make_user, db, expected_attendance=10)
    live = _book(db, event_id, coordinator, venues["Main Hall"])
    gone = _book(db, event_id, coordinator, venues["Seminar Room 3"])
    db.get(VenueBooking, gone).status = BookingStatus.cancelled
    db.commit()

    res = client.get(f"/venues/events/{event_id}/suitability", headers=coord_h).json()

    assert [v["booking_id"] for v in res["venues"]] == [live]
from app.models.venues import Venue, VenueActivity
from tests.integration.test_coordinator_concurrency_postgres import THREADS, race

pytestmark = pytest.mark.integration

GOOD = {
    "name": "Harbour Hall",
    "location": "5 Quay Road",
    "capacity": 200,
    "facilities": ["Projector"],
    "accessibility_features": [],
    "supported_layouts": ["Theatre"],
    "operating_hours": "Mon-Fri 08:00-22:00",
}


def test_ac1_ac5_add_persists_arrays_and_logs_actor(client, make_user, db):
    _s, staff_h = make_user(Role.VENUE_STAFF, "staff@connectsphere.test", "Vera")
    res = client.post("/venues", json=GOOD, headers=staff_h)
    assert res.status_code == 201, res.text
    db.expire_all()
    venue = db.query(Venue).one()
    assert venue.supported_layouts == ["Theatre"] and venue.facilities == ["Projector"]
    log = client.get("/venues/activity", headers=staff_h).json()
    assert [(r["changed_by"], "added" in r["note"]) for r in log] == [("Vera", True)]


def test_ac3_same_name_added_at_once_saves_exactly_one(make_client, client, make_user, db):
    _s, staff_h = make_user(Role.VENUE_STAFF, "staff@connectsphere.test", "Vera")
    results = race(make_client, THREADS, lambda c: c.post("/venues", json=GOOD, headers=staff_h))
    codes = sorted(r.status_code for r in results)
    assert codes == [201] + [409] * (THREADS - 1), codes
    db.expire_all()
    assert db.query(Venue).count() == 1
    assert db.query(VenueActivity).count() == 1


def test_ac3_database_refuses_a_name_differing_only_by_case(client, make_user, db):
    _s, staff_h = make_user(Role.VENUE_STAFF, "staff@connectsphere.test", "Vera")
    assert client.post("/venues", json=GOOD, headers=staff_h).status_code == 201
    res = client.post("/venues", json={**GOOD, "name": "harbour hall"}, headers=staff_h)
    assert res.status_code == 409
    db.expire_all()
    assert db.query(Venue).count() == 1


def test_search_leaves_out_venues_closed_in_the_window(client, venues, coordinator_h):
    # 09:00-18:00 at the venue: Seminar Room 3's exact hours, before Rooftop
    # Garden opens, and 100% Lab has none recorded.
    window = {"start": "2026-11-02T01:00:00Z", "end": "2026-11-02T10:00:00Z"}

    res = client.get("/venues", params=window, headers=coordinator_h).json()

    assert [v["name"] for v in res] == ["100% Lab", "Main Hall", "Seminar Room 3"]
