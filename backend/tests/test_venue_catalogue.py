"""Tests for "Manage Venue Catalogue Details" (SCRUM-108), AC1-AC5."""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.roles import Role
from app.models.enums import BookingStatus
from app.models.events import Event, EventStatusHistory
from app.models.notifications import Notification
from app.models.venues import Venue, VenueActivity, VenueBooking
from tests.test_venue_search import _headers, _someone

GOOD = {
    "name": "Harbour Hall",
    "location": "5 Quay Road",
    "capacity": 200,
    "facilities": ["Projector", "PA system"],
    "accessibility_features": ["Wheelchair access"],
    "supported_layouts": ["Theatre", "Classroom"],
    "operating_hours": "Mon-Fri 08:00-22:00",
}


def _staff(client, db_session):
    return _headers(client, db_session, Role.VENUE_STAFF, "vs@example.com")


def _add(client, headers, **overrides):
    return client.post("/venues", json={**GOOD, **overrides}, headers=headers)


def _existing(db_session, **overrides) -> Venue:
    data = {**GOOD, "supported_layouts": ["Theatre", "Classroom"], **overrides}
    venue = Venue(
        name=data["name"],
        location=data["location"],
        capacity=data["capacity"],
        facilities=data["facilities"],
        accessibility_features=data["accessibility_features"],
        supported_layouts=data["supported_layouts"],
        operating_hours=data["operating_hours"],
    )
    db_session.add(venue)
    db_session.commit()
    return venue


def _booking(db_session, venue, *, attendance=150, layout="Theatre", status=BookingStatus.approved, days=10):
    someone = _someone(db_session)
    event = Event(
        name="Gala",
        organiser_id=someone.id,
        coordinator_id=someone.id,
        expected_attendance=attendance,
        room_layout_preference=layout,
    )
    db_session.add(event)
    db_session.flush()
    start = datetime.now(timezone.utc) + timedelta(days=days)
    booking = VenueBooking(
        event_id=event.id,
        venue_id=venue.id,
        requested_by=someone.id,
        start_time=start,
        end_time=start + timedelta(hours=2),
        status=status,
    )
    db_session.add(booking)
    db_session.commit()
    return booking


# --- AC1: add a Venue -----------------------------------------------------------


def test_ac1_venue_staff_add_venue_and_it_appears_in_catalogue(client, db_session):
    staff_h = _staff(client, db_session)
    res = _add(client, staff_h)
    assert res.status_code == 201, res.text
    body = res.json()
    for key, value in GOOD.items():
        assert body[key] == value
    listed = client.get("/venues", headers=staff_h).json()
    assert [v["name"] for v in listed] == ["Harbour Hall"]
    assert client.get(f"/venues/{body['id']}", headers=staff_h).json()["operating_hours"] == GOOD["operating_hours"]


def test_ac1_only_venue_staff_may_add_or_edit(client, db_session):
    venue = _existing(db_session)
    for role in (Role.COORDINATOR, Role.ATTENDEE, Role.ORGANISER, Role.TECH_SUPPORT):
        h = _headers(client, db_session, role, f"{role.value}@example.com")
        assert _add(client, h).status_code == 403
        assert client.put(f"/venues/{venue.id}", json=GOOD, headers=h).status_code == 403
        assert client.get("/venues/activity", headers=h).status_code == 403
    assert client.post("/venues", json=GOOD).status_code == 401
    db_session.expire_all()
    assert db_session.query(Venue).count() == 1


def test_ac1_blank_lists_are_cleaned_and_optional_lists_may_be_empty(client, db_session):
    staff_h = _staff(client, db_session)
    res = _add(
        client, staff_h, facilities=[], accessibility_features=[" ", ""], supported_layouts=[" Theatre ", "theatre", "U-shape"]
    )
    assert res.status_code == 201
    assert res.json()["supported_layouts"] == ["Theatre", "U-shape"]
    assert res.json()["accessibility_features"] == []


# --- AC2: edit ------------------------------------------------------------------


def test_ac2_edit_shows_updated_details_everywhere(client, db_session):
    venue = _existing(db_session)
    staff_h = _staff(client, db_session)
    coord_h = _headers(client, db_session, Role.COORDINATOR, "coord@example.com")
    edited = {
        **GOOD,
        "name": "Harbour Hall East",
        "location": "7 Quay Road",
        "capacity": 300,
        "facilities": ["Stage"],
        "accessibility_features": ["Hearing loop"],
        "supported_layouts": ["Banquet"],
        "operating_hours": "Daily 09:00-18:00",
    }
    res = client.put(f"/venues/{venue.id}", json=edited, headers=staff_h)
    assert res.status_code == 200, res.text
    for h in (staff_h, coord_h):
        detail = client.get(f"/venues/{venue.id}", headers=h).json()
        for key, value in edited.items():
            assert detail[key] == value
        assert [v["name"] for v in client.get("/venues", headers=h).json()] == ["Harbour Hall East"]


def test_ac2_keeping_own_name_is_not_a_duplicate(client, db_session):
    venue = _existing(db_session)
    staff_h = _staff(client, db_session)
    res = client.put(f"/venues/{venue.id}", json={**GOOD, "capacity": 250}, headers=staff_h)
    assert res.status_code == 200


def test_ac2_unknown_venue_is_404(client, db_session):
    assert client.put("/venues/9999", json=GOOD, headers=_staff(client, db_session)).status_code == 404


# --- AC3: refusals leave the Venue unchanged ------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": ""},
        {"name": "   "},
        {"location": ""},
        {"operating_hours": " "},
        {"supported_layouts": []},
        {"supported_layouts": [" "]},
        {"capacity": 0},
        {"capacity": -5},
        {"capacity": 10.5},
        {"capacity": "100"},
    ],
)
def test_ac3_invalid_save_is_refused_and_venue_unchanged(client, db_session, overrides):
    venue = _existing(db_session)
    staff_h = _staff(client, db_session)
    assert _add(client, staff_h, **overrides).status_code == 422
    res = client.put(f"/venues/{venue.id}", json={**GOOD, **overrides}, headers=staff_h)
    assert res.status_code == 422
    assert res.json()["detail"]  # a reason
    db_session.expire_all()
    assert db_session.query(Venue).count() == 1
    kept = db_session.get(Venue, venue.id)
    assert (kept.name, kept.capacity, kept.location) == (GOOD["name"], GOOD["capacity"], GOOD["location"])
    assert db_session.query(VenueActivity).count() == 0


def test_ac3_missing_field_is_refused(client, db_session):
    staff_h = _staff(client, db_session)
    body = {k: v for k, v in GOOD.items() if k != "capacity"}
    res = client.post("/venues", json=body, headers=staff_h)
    assert res.status_code == 422
    assert "capacity" in str(res.json()["detail"])


def test_ac3_duplicate_name_is_refused_ignoring_case(client, db_session):
    _existing(db_session, name="Marina Hall")
    other = _existing(db_session, name="Other Hall")
    staff_h = _staff(client, db_session)
    res = _add(client, staff_h, name="  marina HALL ")
    assert res.status_code == 409
    assert "already exists" in res.json()["detail"]
    res = client.put(f"/venues/{other.id}", json={**GOOD, "name": "MARINA HALL", "capacity": 999}, headers=staff_h)
    assert res.status_code == 409
    db_session.expire_all()
    assert (db_session.get(Venue, other.id).name, db_session.get(Venue, other.id).capacity) == ("Other Hall", 200)
    assert db_session.query(Venue).count() == 2
    assert db_session.query(VenueActivity).count() == 0


# --- AC4: bookings kept and flagged ---------------------------------------------


def test_ac4_capacity_reduction_keeps_and_flags_bookings(client, db_session):
    venue = _existing(db_session, capacity=200)
    too_big = _booking(db_session, venue, attendance=150)
    fits = _booking(db_session, venue, attendance=40)
    staff_h = _staff(client, db_session)
    res = client.put(f"/venues/{venue.id}", json={**GOOD, "capacity": 100}, headers=staff_h)
    assert res.status_code == 200
    assert [f["booking_id"] for f in res.json()["flagged_bookings"]] == [too_big.id]
    db_session.expire_all()
    assert db_session.get(VenueBooking, too_big.id).status == BookingStatus.approved  # kept
    assert db_session.get(VenueBooking, too_big.id).review_flagged_at is not None
    assert "capacity reduced from 200 to 100" in db_session.get(VenueBooking, too_big.id).review_reason
    assert db_session.get(VenueBooking, fits.id).review_flagged_at is None
    assert db_session.query(VenueBooking).count() == 2
    assert db_session.query(Notification).count() == 1
    notes = [h.note for h in db_session.query(EventStatusHistory).all()]
    assert any("flagged for review" in n for n in notes)
    assert client.get(f"/venue-bookings/{too_big.id}", headers=staff_h).json()["review_flagged"] is True


def test_ac4_removing_a_layout_flags_bookings_using_it(client, db_session):
    venue = _existing(db_session)
    theatre = _booking(db_session, venue, layout="Theatre")
    classroom = _booking(db_session, venue, layout="Classroom", status=BookingStatus.pending)
    staff_h = _staff(client, db_session)
    res = client.put(f"/venues/{venue.id}", json={**GOOD, "supported_layouts": ["Classroom"]}, headers=staff_h)
    assert res.status_code == 200
    assert [f["booking_id"] for f in res.json()["flagged_bookings"]] == [theatre.id]
    assert "'Theatre' is no longer supported" in res.json()["flagged_bookings"][0]["reason"]
    db_session.expire_all()
    assert db_session.get(VenueBooking, theatre.id).status == BookingStatus.approved
    assert db_session.get(VenueBooking, classroom.id).review_flagged_at is None


def test_ac4_raising_capacity_or_adding_layout_flags_nothing(client, db_session):
    venue = _existing(db_session)
    booking = _booking(db_session, venue, attendance=190)
    staff_h = _staff(client, db_session)
    res = client.put(
        f"/venues/{venue.id}",
        json={**GOOD, "capacity": 500, "supported_layouts": ["Theatre", "Classroom", "Banquet"]},
        headers=staff_h,
    )
    assert res.status_code == 200 and res.json()["flagged_bookings"] == []
    db_session.expire_all()
    assert db_session.get(VenueBooking, booking.id).review_flagged_at is None


def test_ac4_past_and_cancelled_bookings_are_not_flagged(client, db_session):
    venue = _existing(db_session)
    past = _booking(db_session, venue, days=-5)
    cancelled = _booking(db_session, venue, status=BookingStatus.cancelled)
    staff_h = _staff(client, db_session)
    res = client.put(f"/venues/{venue.id}", json={**GOOD, "capacity": 10}, headers=staff_h)
    assert res.json()["flagged_bookings"] == []
    db_session.expire_all()
    assert db_session.get(VenueBooking, past.id).review_flagged_at is None
    assert db_session.get(VenueBooking, cancelled.id).review_flagged_at is None


# --- AC5: Activity Log ----------------------------------------------------------


def test_ac5_add_and_edit_are_logged_with_actor_and_time(client, db_session):
    staff_h = _staff(client, db_session)
    venue_id = _add(client, staff_h).json()["id"]
    client.put(f"/venues/{venue_id}", json={**GOOD, "capacity": 250}, headers=staff_h)
    log = client.get("/venues/activity", headers=staff_h).json()
    assert len(log) == 2
    edit, added = log
    assert "added" in added["note"]
    assert "capacity: 200 -> 250" in edit["note"]
    for row in log:
        assert row["changed_by"] == "Test User"
        assert row["venue_name"] == "Harbour Hall"
        assert row["created_at"]


def test_ac5_saving_without_changes_logs_nothing(client, db_session):
    venue = _existing(db_session)
    staff_h = _staff(client, db_session)
    assert client.put(f"/venues/{venue.id}", json=GOOD, headers=staff_h).status_code == 200
    assert client.get("/venues/activity", headers=staff_h).json() == []
