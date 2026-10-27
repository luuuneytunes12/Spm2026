"""Tests for "Release an Event's Venue Bookings when it is cancelled or completed".

    AC1  confirmed bookings are released; the venue is free for that period,
         setup and turnaround included
    AC2  active tentative holds are released
    AC3  released bookings stay in the history, marked released
    AC4  the Activity Log records it with 'System' as the actor; the Venue
         Staff and the Event Coordinator are notified
    AC5  other Events' bookings at the same venue are unchanged
    AC6  pending requests leave the Venue Staff queue, marked released
"""

from datetime import timedelta

import pytest

from app.core.roles import Role
from app.models.enums import BookingStatus, EventStatus, NotificationType
from app.models.events import Event, EventStatusHistory
from app.models.notifications import Notification
from app.models.venues import VenueBooking
from tests.event_review_test_helpers import review_setup, user
from tests.test_venue_booking_request import _venue
from tests.test_venue_search import _at, _names

pytestmark = pytest.mark.usefixtures("coordinator_auto_assign")

RELEASED = NotificationType.venue_booking_released


def _world(client, db_session):
    """A planning event booked 10:00-12:00 at three venues -- approved, held
    and pending -- plus another event approved later the same day at the hall."""
    organiser, org_h, coordinator, coord_h, event_id = review_setup(client, db_session)
    staff, staff_h = user(client, db_session, Role.VENUE_STAFF, "staff@example.com", "Vera Staff")
    other_staff, _ = user(client, db_session, Role.VENUE_STAFF, "other@example.com", "Otto Staff")
    event = db_session.get(Event, event_id)
    event.status = EventStatus.planning_event
    hall = _venue(db_session, "Main Hall", setup_minutes=30, turnaround_minutes=45)
    room = _venue(db_session, "Breakout Room")
    annex = _venue(db_session, "Annex")
    start, end = _at(10), _at(12)

    def booking(event_id, venue, status, start=start, end=end):
        row = VenueBooking(
            event_id=event_id,
            venue_id=venue.id,
            requested_by=coordinator.id,
            reviewed_by=None if status is BookingStatus.pending else staff.id,
            start_time=start,
            end_time=end,
            status=status,
            expires_at=end + timedelta(days=1) if status is BookingStatus.tentative_hold else None,
        )
        db_session.add(row)
        return row

    approved = booking(event_id, hall, BookingStatus.approved)
    hold = booking(event_id, room, BookingStatus.tentative_hold)
    pending = booking(event_id, annex, BookingStatus.pending)
    other_event = Event(name="Other event", organiser_id=organiser.id, status=EventStatus.planning_event)
    db_session.add(other_event)
    db_session.flush()
    other = booking(other_event.id, hall, BookingStatus.approved, _at(16), _at(18))
    db_session.commit()
    return {
        "event": event, "org_h": org_h, "coordinator": coordinator, "coord_h": coord_h,
        "staff": staff, "staff_h": staff_h, "other_staff": other_staff, "organiser": organiser,
        "approved": approved, "hold": hold, "pending": pending, "other": other,
    }


def _complete(db_session, w):
    w["event"].status = EventStatus.event_completed
    db_session.commit()
    db_session.expire_all()


def _finish(client, db_session, w, how):
    if how == "cancelled":
        res = client.post(f"/events/{w['event'].id}/cancel", json={"reason": "Speaker ill."}, headers=w["coord_h"])
        assert res.status_code == 200, res.text
        db_session.expire_all()
    else:
        _complete(db_session, w)


HOW = pytest.mark.parametrize("how", ["cancelled", "completed"])


@HOW
def test_ac1_approved_booking_is_released_and_venue_free_including_buffers(client, db_session, how):
    w = _world(client, db_session)
    # 12:45 is inside the hall's 45-minute turnaround, so it reads as occupied now.
    window = {"start": "2026-11-02T13:00:00Z", "end": "2026-11-02T13:30:00Z"}
    assert "Main Hall" not in _names(client.get("/venues", params=window, headers=w["coord_h"]))

    _finish(client, db_session, w, how)

    assert w["approved"].status is BookingStatus.released
    assert "Main Hall" in _names(client.get("/venues", params=window, headers=w["coord_h"]))


@HOW
def test_ac2_tentative_hold_is_released(client, db_session, how):
    w = _world(client, db_session)
    _finish(client, db_session, w, how)
    assert w["hold"].status is BookingStatus.released
    assert w["hold"].expires_at is None


@HOW
def test_ac3_released_bookings_remain_in_history_marked_released(client, db_session, how):
    w = _world(client, db_session)
    _finish(client, db_session, w, how)
    rows = client.get(f"/venue-bookings/events/{w['event'].id}", headers=w["coord_h"]).json()
    assert sorted(r["status"] for r in rows) == ["released"] * 3
    assert db_session.query(VenueBooking).filter_by(event_id=w["event"].id).count() == 3


@HOW
def test_ac4_activity_log_shows_system_and_staff_and_coordinator_are_notified(client, db_session, how):
    w = _world(client, db_session)
    _finish(client, db_session, w, how)

    activity = client.get(f"/events/{w['event'].id}/activity", headers=w["org_h"]).json()
    released = [e for e in activity if "released" in (e["note"] or "")]
    assert len(released) == 3
    assert {e["changed_by_name"] for e in released} == {"System"}

    def told(person):
        return db_session.query(Notification).filter_by(user_id=person.id, type=RELEASED).count()

    assert told(w["coordinator"]) == 3
    assert told(w["staff"]) == 2  # the approval and the hold they decided
    # Negative: nobody outside the Coordinator and deciding Venue Staff is told.
    assert told(w["other_staff"]) == 0
    assert told(w["organiser"]) == 0


@HOW
def test_ac5_other_events_bookings_at_the_same_venue_are_unchanged(client, db_session, how):
    w = _world(client, db_session)
    _finish(client, db_session, w, how)
    assert w["other"].status is BookingStatus.approved
    assert w["other"].decision_notes is None


@HOW
def test_ac6_pending_request_leaves_the_queue_marked_released(client, db_session, how):
    w = _world(client, db_session)
    queue = lambda: [b["id"] for b in client.get("/venue-bookings/queue", headers=w["staff_h"]).json()]  # noqa: E731
    assert w["pending"].id in queue()

    _finish(client, db_session, w, how)

    assert w["pending"].status is BookingStatus.released
    assert w["pending"].id not in queue()


def test_other_status_changes_release_nothing(client, db_session):
    w = _world(client, db_session)
    w["event"].status = EventStatus.awaiting_safety_check
    db_session.commit()
    db_session.expire_all()
    assert w["approved"].status is BookingStatus.approved
    assert w["hold"].status is BookingStatus.tentative_hold
    assert w["pending"].status is BookingStatus.pending


def test_release_happens_once(client, db_session):
    w = _world(client, db_session)
    _complete(db_session, w)
    w["event"].name = "Renamed afterwards"
    db_session.commit()
    notes = db_session.query(EventStatusHistory).filter(
        EventStatusHistory.event_id == w["event"].id, EventStatusHistory.changed_by.is_(None)
    )
    assert notes.count() == 3
