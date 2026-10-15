"""Tests for "Be told when a booked Venue becomes unavailable" (SCRUM-94).

    As an Event Coordinator, I want to be told when a Venue I booked becomes
    unavailable, so that I can make other arrangements without my Event
    being cancelled.

    AC1  a period overlapping a booking's occupied window (setup and
         turnaround included) flags it as needing action; Venue Staff see it
    AC2  the Event is not cancelled; its status and details stay unchanged
    AC3  the Coordinator is notified with the Event, Venue, affected period
         and reason, and told alternative arrangements are required
    AC4  editing or ending the period so it no longer overlaps removes the
         mark and notifies the Coordinator

Approved bookings and active holds carry the conflict flag; a pending
request is shown to Venue Staff as a conflict in review and its Coordinator
is told directly.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.enums import BookingStatus, EventStatus
from app.models.events import Event
from app.models.notifications import Notification
from app.models.venues import VenueBooking
from tests.test_booking_conflict_flags import _approved, _flagged, _world

pytestmark = pytest.mark.usefixtures("coordinator_auto_assign")

UNAVAILABLE = "venue_unavailability_recorded"
CONFLICT = "venue_booking_conflict"


def _at(hour, minute=0, day=2, year=2030):
    return datetime(year, 11, day, hour, minute, tzinfo=timezone.utc)


def _buffers(db_session, w, setup=30, turnaround=45):
    w["venue"].setup_minutes, w["venue"].turnaround_minutes = setup, turnaround
    db_session.commit()


def _body(start, end, category="Maintenance", reason="Aircon repair"):
    return {"start_time": start.isoformat(), "end_time": end.isoformat(), "reason_category": category, "reason": reason}


def _post(client, w, start, end, **kw):
    res = client.post(f"/venues/{w['venue'].id}/unavailability", json=_body(start, end, **kw), headers=w["staff_h"])
    assert res.status_code == 201, res.text
    return res.json()


def _put(client, w, pid, start, end, **kw):
    res = client.put(
        f"/venues/{w['venue'].id}/unavailability/{pid}", json=_body(start, end, **kw), headers=w["staff_h"]
    )
    assert res.status_code == 200, res.text
    return res.json()


def _notes(db_session, user_id, type=None):
    db_session.expire_all()
    q = db_session.query(Notification).filter_by(user_id=user_id)
    if type:
        q = q.filter_by(type=type)
    return [n.message for n in q.order_by(Notification.id)]


def _staff_conflicts(client, w, booking):
    """The unavailability conflicts Venue Staff see on a booking in review."""
    conflicts = client.get(f"/venue-bookings/{booking.id}", headers=w["staff_h"]).json()["conflicts"]
    return [c for c in conflicts if c["kind"] == "unavailability"]


# --- AC1: flagged, setup and turnaround included -------------------------------


def test_ac1_a_period_inside_only_the_turnaround_flags_an_approved_booking(client, db_session):
    w = _world(client, db_session)
    _buffers(db_session, w)  # 10:00-12:00 occupies 09:30-12:45
    booking = _approved(db_session, w, _at(10), _at(12))

    body = _post(client, w, _at(12, 30), _at(14))

    assert _flagged(db_session, booking) == [True]
    assert [a["booking_id"] for a in body["affected_bookings"]] == [booking.id]
    assert [r["id"] for r in client.get("/venue-bookings/flagged", headers=w["staff_h"]).json()] == [booking.id]


def test_ac1_a_period_inside_only_the_setup_flags_an_active_hold(client, db_session):
    w = _world(client, db_session)
    _buffers(db_session, w)
    hold = _approved(db_session, w, _at(10), _at(12), status=BookingStatus.tentative_hold)
    _post(client, w, _at(9), _at(9, 45))
    assert _flagged(db_session, hold) == [True]


def test_ac1_a_pending_request_in_the_turnaround_is_shown_to_venue_staff(client, db_session):
    w = _world(client, db_session)
    _buffers(db_session, w)
    pending = _approved(db_session, w, _at(10), _at(12), status=BookingStatus.pending)

    body = _post(client, w, _at(12, 30), _at(14))

    assert [a["booking_id"] for a in body["affected_bookings"]] == [pending.id]
    [conflict] = _staff_conflicts(client, w, pending)
    assert conflict["kind"] == "unavailability"
    assert (conflict["overlap_start"], conflict["overlap_end"]) == ("2030-11-02T12:30:00Z", "2030-11-02T12:45:00Z")


def test_ac1_frozen_literal_without_buffers_the_same_period_flags_nothing(client, db_session):
    w = _world(client, db_session)
    booking = _approved(db_session, w, _at(10), _at(12))
    pending = _approved(db_session, w, _at(10), _at(12), status=BookingStatus.pending, name="Talk")
    assert _post(client, w, _at(12, 30), _at(14))["affected_bookings"] == []
    assert _flagged(db_session, booking) == [False]
    assert _staff_conflicts(client, w, pending) == []


def test_ac1_a_period_that_only_touches_the_turnaround_flags_nothing(client, db_session):
    w = _world(client, db_session)
    _buffers(db_session, w)
    booking = _approved(db_session, w, _at(10), _at(12))
    _post(client, w, _at(12, 45), _at(14))
    assert _flagged(db_session, booking) == [False]


def test_ac1_approval_is_refused_when_the_turnaround_reaches_into_a_period(client, db_session):
    w = _world(client, db_session)
    _buffers(db_session, w)
    pending = _approved(db_session, w, _at(10), _at(12), status=BookingStatus.pending)
    _post(client, w, _at(12, 30), _at(14))
    res = client.post(f"/venue-bookings/{pending.id}/approve", headers=w["staff_h"])
    assert res.status_code == 409 and "unavailable" in res.json()["detail"]


def test_ac1_frozen_literal_approval_passes_once_clear_of_the_turnaround(client, db_session):
    w = _world(client, db_session)
    _buffers(db_session, w)
    pending = _approved(db_session, w, _at(10), _at(12), status=BookingStatus.pending)
    _post(client, w, _at(12, 45), _at(14))
    assert client.post(f"/venue-bookings/{pending.id}/approve", headers=w["staff_h"]).status_code == 200


def test_ac1_negative_a_coordinator_cannot_see_the_flagged_list(client, db_session):
    w = _world(client, db_session)
    booking = _approved(db_session, w, _at(10), _at(12))
    _post(client, w, _at(11), _at(14))
    assert client.get("/venue-bookings/flagged", headers=w["sam_h"]).status_code == 403
    [mine] = client.get(f"/venue-bookings/events/{booking.event_id}", headers=w["sam_h"]).json()
    assert mine["conflicts"] == []  # no other event's details reach a Coordinator


# --- AC2: nothing is cancelled --------------------------------------------------


@pytest.mark.parametrize("status", [BookingStatus.approved, BookingStatus.tentative_hold, BookingStatus.pending])
def test_ac2_the_event_and_the_booking_are_unchanged(client, db_session, status):
    w = _world(client, db_session)
    booking = _approved(db_session, w, _at(10), _at(12), status=status)
    event = db_session.get(Event, booking.event_id)
    before = (event.status, event.name, event.proposed_start, event.proposed_end, event.coordinator_id)

    _post(client, w, _at(8), _at(18))

    db_session.expire_all()
    event = db_session.get(Event, booking.event_id)
    assert (event.status, event.name, event.proposed_start, event.proposed_end, event.coordinator_id) == before
    assert event.status == EventStatus.planning_event
    stored = db_session.get(VenueBooking, booking.id)
    assert (stored.status, stored.start_time, stored.end_time) == (status, booking.start_time, booking.end_time)


# --- AC3: the Coordinator is told what, where, when and why ---------------------


@pytest.mark.parametrize(
    ("status", "type", "what"),
    [
        (BookingStatus.approved, CONFLICT, "booking"),
        (BookingStatus.tentative_hold, CONFLICT, "booking"),
        (BookingStatus.pending, UNAVAILABLE, "request"),
    ],
)
def test_ac3_the_notification_names_event_venue_period_reason_and_action(client, db_session, status, type, what):
    w = _world(client, db_session)
    _buffers(db_session, w)
    _approved(db_session, w, _at(10), _at(12), status=status, name="Alumni Gala")

    _post(client, w, _at(12, 30), _at(14), category="Safety concern", reason="Ceiling leak")

    [message] = _notes(db_session, w["sam"].id, type)
    for part in (
        "Marina Hall",
        "'Alumni Gala'",
        "02 Nov 2030 12:30 to 02 Nov 2030 14:00",  # the unavailable period
        "Safety concern: Ceiling leak",  # the reason
        f"your {what} for 'Alumni Gala' from 02 Nov 2030 12:30 to 02 Nov 2030 12:45 UTC",  # affected period
        "Venue Unavailable - Action Required",
        "alternative arrangements are required",
        "has not been cancelled",
    ):
        assert part in message


def test_ac3_negative_only_that_events_coordinator_is_told_once(client, db_session):
    w = _world(client, db_session)
    _approved(db_session, w, _at(10), _at(12), coordinator="sam")
    _approved(db_session, w, _at(15), _at(16), coordinator="kim", name="Later")
    _post(client, w, _at(11), _at(13))
    _post(client, w, _at(11, 30), _at(12, 30))  # a second period over the same booking
    assert len(_notes(db_session, w["sam"].id)) == 1
    assert _notes(db_session, w["kim"].id) == []
    assert _notes(db_session, w["staff"].id) == []


# --- AC4: no longer overlapping -> mark removed, Coordinator told ---------------


def test_ac4_editing_the_period_away_removes_the_flag_and_tells_the_coordinator(client, db_session):
    w = _world(client, db_session)
    _buffers(db_session, w)
    booking = _approved(db_session, w, _at(10), _at(12))
    pid = _post(client, w, _at(12, 30), _at(14))["id"]

    assert _put(client, w, pid, _at(13), _at(14))["recheck"]["cleared"] == 1

    assert _flagged(db_session, booking) == [False]
    assert "cleared" in _notes(db_session, w["sam"].id)[-1]


def test_ac4_editing_the_period_away_tells_a_pending_requests_coordinator(client, db_session):
    w = _world(client, db_session)
    _buffers(db_session, w)
    _approved(db_session, w, _at(10), _at(12), status=BookingStatus.pending, name="Talk")
    pid = _post(client, w, _at(12, 30), _at(14))["id"]

    _put(client, w, pid, _at(13), _at(14))

    first, last = _notes(db_session, w["sam"].id, UNAVAILABLE)
    assert "Action Required" in first
    assert "no longer unavailable" in last and "'Talk'" in last and "no further action" in last


def test_ac4_ending_a_period_early_clears_every_affected_booking(client, db_session):
    w = _world(client, db_session)
    approved = _approved(db_session, w, _at(10), _at(12))
    _approved(db_session, w, _at(14), _at(15), status=BookingStatus.pending, coordinator="kim", name="Talk")
    now = datetime.now(timezone.utc)
    pid = _post(client, w, now - timedelta(hours=1), _at(20))["id"]

    res = client.post(f"/venues/{w['venue'].id}/unavailability/{pid}/end", headers=w["staff_h"])

    assert res.status_code == 200
    assert _flagged(db_session, approved) == [False]
    assert "cleared" in _notes(db_session, w["sam"].id)[-1]
    assert "no longer unavailable" in _notes(db_session, w["kim"].id)[-1]


def test_ac4_deleting_the_period_tells_a_pending_requests_coordinator(client, db_session):
    w = _world(client, db_session)
    _approved(db_session, w, _at(10), _at(12), status=BookingStatus.pending)
    pid = _post(client, w, _at(11), _at(13))["id"]
    assert client.delete(f"/venues/{w['venue'].id}/unavailability/{pid}", headers=w["staff_h"]).status_code == 204
    assert "no longer unavailable" in _notes(db_session, w["sam"].id, UNAVAILABLE)[-1]


def test_ac4_frozen_literal_an_edit_that_still_overlaps_tells_no_one_again(client, db_session):
    w = _world(client, db_session)
    booking = _approved(db_session, w, _at(10), _at(12))
    _approved(db_session, w, _at(10), _at(12), status=BookingStatus.pending, name="Talk")
    pid = _post(client, w, _at(11), _at(13))["id"]
    _put(client, w, pid, _at(11), _at(14), reason="Longer repair")
    assert _flagged(db_session, booking) == [True]
    assert len(_notes(db_session, w["sam"].id)) == 2  # one per booking, from the first save only


def test_ac4_still_inside_another_period_keeps_the_mark(client, db_session):
    w = _world(client, db_session)
    booking = _approved(db_session, w, _at(10), _at(12))
    _approved(db_session, w, _at(10), _at(12), status=BookingStatus.pending, name="Talk")
    first = _post(client, w, _at(11), _at(13))["id"]
    _post(client, w, _at(9), _at(10, 30))
    _put(client, w, first, _at(15), _at(16))
    assert _flagged(db_session, booking) == [True]
    assert not any("no longer" in m or "cleared" in m for m in _notes(db_session, w["sam"].id))


def test_ac1_an_edit_that_newly_covers_a_pending_request_tells_its_coordinator(client, db_session):
    w = _world(client, db_session)
    _approved(db_session, w, _at(10), _at(12), status=BookingStatus.pending)
    pid = _post(client, w, _at(14), _at(16))["id"]
    assert _notes(db_session, w["sam"].id) == []
    _put(client, w, pid, _at(11), _at(16))
    [message] = _notes(db_session, w["sam"].id, UNAVAILABLE)
    assert "Action Required" in message
