"""Coordinator notifications on real PostgreSQL, with overlapping requests.

SQLite serialises every write, so these only show on Postgres: a double
clicked Venue decision is made once and so told once, and a Change Request
racing a cancellation never deadlocks (a notification row takes a key lock on
its Event, which a cancellation holds).
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


def _event(db, make_user, status):
    organiser, org_h = make_user(Role.ORGANISER, "org@connectsphere.test", "Priya Menon")
    coordinator, coord_h = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")
    event = Event(
        name="Partner Summit",
        organiser_id=organiser.id,
        coordinator_id=coordinator.id,
        status=status,
        proposed_start=START,
        proposed_end=END,
        expected_attendance=120,
    )
    db.add(event)
    db.commit()
    return event.id, coordinator, coord_h, org_h


def _told(db, user_id, type):
    db.expire_all()
    return db.query(Notification).filter_by(user_id=user_id, type=type.value).count()


def test_ac4_a_double_clicked_approval_tells_the_coordinator_once(make_client, db, make_user):
    event_id, coordinator, coord_h, _ = _event(db, make_user, EventStatus.event_approved)
    _, staff_h = make_user(Role.VENUE_STAFF, "staff@connectsphere.test", "Vera Staff")
    venue = Venue(name="Marina Hall", location="10 Bayfront Ave", capacity=250)
    db.add(venue)
    db.commit()
    res = make_client().post(
        f"/venue-bookings/events/{event_id}", json={"venues": [{"venue_id": venue.id}]}, headers=coord_h
    )
    assert res.status_code == 201, res.text
    booking_id = res.json()[0]["id"]

    results = race(make_client, THREADS, lambda c: c.post(f"/venue-bookings/{booking_id}/approve", headers=staff_h))

    assert [r.status_code for r in results].count(200) == 1
    assert _told(db, coordinator.id, NotificationType.venue_booking_decided) == 1


def test_ac6_a_change_request_racing_a_cancellation_never_deadlocks(make_client, db, make_user):
    event_id, coordinator, coord_h, org_h = _event(db, make_user, EventStatus.planning_event)
    calls = {
        0: lambda c: c.post(f"/events/{event_id}/cancel", json={"reason": "Budget cut"}, headers=coord_h),
        1: lambda c: c.post(
            f"/events/{event_id}/change-requests",
            json={"description": "Bigger room", "proposed_changes": {"expected_attendance": 150}},
            headers=org_h,
        ),
    }
    turn = iter(range(2))

    results = race(make_client, 2, lambda c: calls[next(turn)](c))

    assert all(r.status_code < 500 for r in results), [r.text for r in results]
    # Told once if the request got in before the cancel, never if it did not.
    assert _told(db, coordinator.id, NotificationType.change_request_submitted) == sum(
        1 for r in results if r.status_code == 201
    )
