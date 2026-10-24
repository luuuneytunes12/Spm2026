"""Request a replacement venue for an affected booking (SCRUM-95), on real PostgreSQL.

The SQLite tests (tests/test_venue_replacement.py) prove the rules; these
prove the 'replaced' enum label and the self-referencing foreign key on the
production engine, the confirmed Event returning to planning in the same
transaction as the flag, and that two replacement requests at the same moment
create only one.
"""

import pytest

from app.core.roles import Role
from app.models.enums import BookingStatus, EventStatus
from app.models.events import Event
from app.models.notifications import Notification
from app.models.venues import Venue, VenueBooking
from tests.integration.test_coordinator_concurrency_postgres import THREADS, race
from tests.integration.test_venue_booking_decision_postgres import _approve
from tests.integration.test_venue_setup_turnaround_postgres import _at, _world

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("coordinator_auto_assign")]


def _close(client, staff_h, venue_id):
    res = client.post(
        f"/venues/{venue_id}/unavailability",
        json={"start_time": _at(9).isoformat(), "end_time": _at(13).isoformat(), "reason_category": "Maintenance"},
        headers=staff_h,
    )
    assert res.status_code == 201, res.text


def _setup(client, make_user, db):
    sam_h, staff_h, venue_id, [booking_id] = _world(client, make_user, db, 0, 0, [10])
    _so, _ = make_user(Role.SAFETY_OFFICER, "so@connectsphere.test", "Sofia")
    other = Venue(name="Bay Room", location="Level 2", capacity=250)
    db.add(other)
    db.commit()
    assert _approve(client, staff_h, booking_id).status_code == 200
    event = db.get(VenueBooking, booking_id).event
    event.status = EventStatus.safety_check_passed
    db.commit()
    return sam_h, staff_h, venue_id, booking_id, other.id, event.id


def test_ac3_ac4_confirmed_event_returns_to_planning_and_replacement_marks_original_replaced(
    client, make_user, db
):
    sam_h, staff_h, venue_id, booking_id, other_id, event_id = _setup(client, make_user, db)

    _close(client, staff_h, venue_id)
    db.expire_all()
    assert db.get(Event, event_id).status == EventStatus.safety_check_passed  # unavailable alone changes nothing

    res = client.post(f"/venue-bookings/{booking_id}/replacement", json={"venue_id": other_id}, headers=sam_h)
    assert res.status_code == 201, res.text
    new_id = res.json()["id"]
    assert res.json()["replaces"]["id"] == booking_id  # AC2

    assert _approve(client, staff_h, new_id).status_code == 200
    db.expire_all()
    assert db.get(VenueBooking, booking_id).status == BookingStatus.replaced  # AC3
    assert db.get(VenueBooking, new_id).replaces_booking_id == booking_id
    assert db.get(Event, event_id).status == EventStatus.planning_event  # AC4, not cancelled
    assert db.query(Notification).filter_by(type="event_returned_to_planning").count() == 1  # the Coordinator only


def test_two_replacement_requests_at_once_create_only_one(client, make_user, db, make_client):
    sam_h, staff_h, venue_id, booking_id, other_id, _event_id = _setup(client, make_user, db)
    third = Venue(name="Third Hall", location="Level 3", capacity=250)
    db.add(third)
    db.commit()
    _close(client, staff_h, venue_id)
    venues = [other_id, third.id]

    results = race(
        make_client,
        THREADS,
        lambda c: c.post(
            f"/venue-bookings/{booking_id}/replacement",
            json={"venue_id": venues[id(c) % 2]},
            headers=sam_h,
        ).status_code,
    )

    assert results.count(201) == 1
    assert all(code in (201, 409) for code in results)
    db.expire_all()
    assert db.query(VenueBooking).filter_by(replaces_booking_id=booking_id).count() == 1
