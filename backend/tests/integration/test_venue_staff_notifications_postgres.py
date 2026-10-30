"""Venue Staff notifications on real PostgreSQL, with overlapping requests.

SQLite serialises every write, so these only show on Postgres: a
double-clicked booking request is made once and so told once, and a
Coordinator's edit racing a Venue Staff approval never deadlocks (a
notification row takes a key lock on its Event).
"""

from datetime import datetime, timezone

import pytest

from app.core.roles import Role
from app.models.enums import EventStatus, NotificationType
from app.models.events import Event
from app.models.notifications import Notification
from app.models.venues import Venue
from tests.integration.test_coordinator_concurrency_postgres import THREADS, race

pytestmark = pytest.mark.integration

START = datetime(2026, 11, 2, 9, tzinfo=timezone.utc)
END = datetime(2026, 11, 2, 17, tzinfo=timezone.utc)


def _world(db, make_user):
    organiser, _ = make_user(Role.ORGANISER, "org@connectsphere.test", "Priya Menon")
    coordinator, coord_h = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")
    vera, vera_h = make_user(Role.VENUE_STAFF, "vera@connectsphere.test", "Vera Staff")
    event = Event(
        name="Partner Summit",
        organiser_id=organiser.id,
        coordinator_id=coordinator.id,
        status=EventStatus.event_approved,
        proposed_start=START,
        proposed_end=END,
        expected_attendance=120,
    )
    venue = Venue(name="Marina Hall", location="10 Bayfront Ave", capacity=250)
    db.add_all([event, venue])
    db.commit()
    return event.id, venue.id, coord_h, vera, vera_h


def _told(db, user_id, type):
    db.expire_all()
    return db.query(Notification).filter_by(user_id=user_id, type=type.value).count()


def test_ac1_a_double_clicked_booking_request_is_told_once(make_client, db, make_user):
    event_id, venue_id, coord_h, vera, _ = _world(db, make_user)

    results = race(
        make_client,
        THREADS,
        lambda c: c.post(f"/venue-bookings/events/{event_id}", json={"venues": [{"venue_id": venue_id}]}, headers=coord_h),
    )

    assert [r.status_code for r in results].count(201) == 1
    assert _told(db, vera.id, NotificationType.venue_booking_requested) == 1


def test_ac4_an_edit_racing_an_approval_never_deadlocks(make_client, db, make_user):
    event_id, venue_id, coord_h, vera, vera_h = _world(db, make_user)
    res = make_client().post(
        f"/venue-bookings/events/{event_id}", json={"venues": [{"venue_id": venue_id}]}, headers=coord_h
    )
    assert res.status_code == 201, res.text
    booking_id = res.json()[0]["id"]
    calls = [
        lambda c: c.post(f"/venue-bookings/{booking_id}/approve", headers=vera_h),
        lambda c: c.patch(f"/events/assigned/{event_id}/planning", json={"expected_attendance": 150}, headers=coord_h),
    ]
    turn = iter(calls)

    results = race(make_client, 2, lambda c: next(turn)(c))

    assert all(r.status_code < 500 for r in results), [r.text for r in results]
    # Told of the change only if the approval landed first.
    assert _told(db, vera.id, NotificationType.approved_event_changed) in (0, 1)
