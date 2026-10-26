"""Venue Bookings released when an Event is cancelled or completed, on real
PostgreSQL: the new 'released' enum value, the System (null) actor, and six
simultaneous cancels releasing each booking exactly once."""

from datetime import datetime, timezone

import pytest

from app.core.roles import Role
from app.models.enums import BookingStatus, EventStatus, NotificationType
from app.models.events import Event, EventStatusHistory
from app.models.notifications import Notification
from app.models.venues import Venue, VenueBooking
from tests.integration.test_coordinator_concurrency_postgres import THREADS, race

pytestmark = pytest.mark.integration

START = datetime(2026, 11, 2, 9, tzinfo=timezone.utc)
END = datetime(2026, 11, 2, 17, tzinfo=timezone.utc)


def _world(db, make_user):
    organiser, _ = make_user(Role.ORGANISER, "org@connectsphere.test", "Priya Menon")
    coordinator, coord_h = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")
    staff, _ = make_user(Role.VENUE_STAFF, "venue@connectsphere.test", "Vera Staff")
    hall = Venue(name="Main Hall", location="A", capacity=250)
    event = Event(
        name="Conference", organiser_id=organiser.id, coordinator_id=coordinator.id,
        status=EventStatus.planning_event, proposed_start=START, proposed_end=END,
    )
    other = Event(name="Other", organiser_id=organiser.id, status=EventStatus.planning_event)
    db.add_all([hall, event, other])
    db.flush()

    def booking(event_id, status, start=START, end=END):
        return VenueBooking(
            event_id=event_id, venue_id=hall.id, requested_by=coordinator.id,
            reviewed_by=staff.id, start_time=start, end_time=end, status=status,
        )

    mine = booking(event.id, BookingStatus.approved)
    theirs = booking(other.id, BookingStatus.approved, END, END.replace(hour=20))
    db.add_all([mine, theirs])
    db.commit()
    return event, mine, theirs, coord_h, staff


def test_completing_an_event_releases_its_booking_with_a_system_entry(db, make_user):
    event, mine, theirs, _, staff = _world(db, make_user)

    event.status = EventStatus.event_completed
    db.commit()
    db.expire_all()

    assert mine.status is BookingStatus.released
    assert theirs.status is BookingStatus.approved
    system = db.query(EventStatusHistory).filter_by(event_id=event.id, changed_by=None).one()
    assert "released" in system.note
    assert db.query(Notification).filter_by(
        user_id=staff.id, type=NotificationType.venue_booking_released
    ).count() == 1


def test_simultaneous_cancels_release_each_booking_once(db, make_user, make_client):
    event, mine, _, coord_h, _ = _world(db, make_user)
    event_id = event.id

    responses = race(
        make_client,
        THREADS,
        lambda c: c.post(f"/events/{event_id}/cancel", json={"reason": "Not proceeding."}, headers=coord_h),
    )

    assert sorted(r.status_code for r in responses) == [200] + [409] * (THREADS - 1)
    db.expire_all()
    assert mine.status is BookingStatus.released
    assert db.query(EventStatusHistory).filter_by(event_id=event_id, changed_by=None).count() == 1
