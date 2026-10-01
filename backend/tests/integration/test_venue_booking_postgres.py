"""SCRUM-39 (Submit Venue Booking Request) on real PostgreSQL.

The SQLite unit tests (tests/test_venue_booking_request.py) prove the rules;
these prove they hold on the production engine -- its enum and timestamp
handling, the one-live-request-per-event index -- and when the same request
arrives many times at once.
"""

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.roles import Role
from app.models.enums import BookingStatus, EventStatus
from app.models.events import Event
from app.models.venues import Venue, VenueBooking
from tests.integration.conftest import submit_event
from tests.integration.test_coordinator_concurrency_postgres import THREADS, race


def _setup(client, make_user, db):
    _o, org_h = make_user(Role.ORGANISER, "org@connectsphere.test", "Priya Menon")
    sam, sam_h = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")
    _v, staff_h = make_user(Role.VENUE_STAFF, "staff@connectsphere.test", "Vera Staff")
    event_id = submit_event(client, org_h)
    event = db.get(Event, event_id)
    event.status = EventStatus.approved
    event.room_layout_preference = "Theatre"
    venue = Venue(name="Marina Hall", location="10 Bayfront Ave", capacity=250)
    db.add(venue)
    db.commit()
    return sam, sam_h, staff_h, event_id, venue.id


def _post(client, headers, event_id, venue_id):
    return client.post(f"/venue-bookings/events/{event_id}", json={"venue_id": venue_id}, headers=headers)


def test_scrum39_ac1_to_ac3_a_request_reaches_the_queue_carrying_everything(client, make_user, db):
    sam, sam_h, staff_h, event_id, venue_id = _setup(client, make_user, db)

    assert client.post(f"/venue-bookings/events/{event_id}", json={}, headers=sam_h).status_code == 422  # AC1
    assert db.query(VenueBooking).count() == 0

    assert _post(client, sam_h, event_id, venue_id).status_code == 201
    [queued] = client.get("/venue-bookings/queue", headers=staff_h).json()  # AC2
    assert queued["status"] == "pending"
    assert queued["venue"]["name"] == "Marina Hall"  # AC3
    assert queued["start_time"].startswith("2026-11-02T09:00")
    assert queued["expected_attendance"] == 120
    assert queued["room_layout_preference"] == "Theatre"
    assert queued["accessibility_needs"] == "Step-free access, hearing loop"
    assert queued["requested_by"]["name"] == "Sam Tan"


def test_scrum39_a_submit_fired_many_times_at_once_creates_exactly_one_request(
    make_client, client, make_user, db
):
    _sam, sam_h, _staff, event_id, venue_id = _setup(client, make_user, db)

    results = race(make_client, THREADS, lambda c: _post(c, sam_h, event_id, venue_id))

    assert sorted(r.status_code for r in results) == [201] + [409] * (THREADS - 1)
    assert db.query(VenueBooking).count() == 1


def test_scrum39_the_database_itself_refuses_a_second_live_request_for_an_event(client, make_user, db):
    sam, _h, _s, event_id, venue_id = _setup(client, make_user, db)
    event = db.get(Event, event_id)
    row = lambda status: VenueBooking(  # noqa: E731
        event_id=event_id,
        venue_id=venue_id,
        requested_by=sam.id,
        start_time=event.proposed_start,
        end_time=event.proposed_end,
        status=status,
    )
    db.add(row(BookingStatus.rejected))
    db.add(row(BookingStatus.pending))
    db.commit()  # history plus one live request is fine

    db.add(row(BookingStatus.approved))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_scrum39_the_request_persists_across_separate_sessions(client, make_user, db):
    _sam, sam_h, staff_h, event_id, venue_id = _setup(client, make_user, db)
    booking_id = _post(client, sam_h, event_id, venue_id).json()["id"]

    assert [b["id"] for b in client.get(f"/venue-bookings/events/{event_id}", headers=sam_h).json()] == [booking_id]
    assert client.get(f"/venue-bookings/{booking_id}", headers=staff_h).json()["venue"]["id"] == venue_id


def test_scrum39_another_coordinator_cannot_book_or_read_it(client, make_user, db):
    _sam, sam_h, _staff, event_id, venue_id = _setup(client, make_user, db)
    _p, priya_h = make_user(Role.COORDINATOR, "priya@connectsphere.test", "Priya Nair")
    _post(client, sam_h, event_id, venue_id)

    assert _post(client, priya_h, event_id, venue_id).status_code == 404
    assert client.get(f"/venue-bookings/events/{event_id}", headers=priya_h).status_code == 404
