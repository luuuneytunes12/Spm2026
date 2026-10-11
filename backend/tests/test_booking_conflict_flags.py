"""Tests for "Flag Conflicting Bookings given Venue Setup & Turnaround" (SCRUM-92).

    AC1  saving a venue's setup/turnaround re-checks FUTURE approved bookings
         (a Hold status does not exist yet, SCRUM-97); those that now clash
         under the SCRUM-41 rule are flagged
    AC2  flagging never changes the booking's status; the Event's Coordinator
         is notified once per flag
    AC3  no clash, no flag; a flag that no longer applies is cleared and logged
    AC4  Venue Staff list flagged bookings with their overlapping period
    AC5  a flagged booking blocks Submit for Safety Check (and Safety approval)
    AC6  cleared when rejected/changed so it no longer overlaps, or kept by
         Venue Staff with a reason recorded in the Activity Log
         (no change/cancel endpoint exists yet: SCRUM-96)
"""

from datetime import datetime, timezone

import pytest

from app.core.roles import Role
from app.domain.event_readiness import outstanding_arrangements
from app.models.enums import BookingStatus, EventStatus
from app.models.events import Event, EventStatusHistory
from app.models.notifications import Notification
from app.models.venues import VenueBooking
from tests.event_review_test_helpers import user
from tests.test_submit_for_safety_check import _booking as _ready_booking
from tests.test_submit_for_safety_check import _setup as _ready_setup
from tests.test_submit_for_safety_check import _submit as _submit_for_check
from tests.test_venue_booking_request import _venue
from tests.test_venue_search import _someone

pytestmark = pytest.mark.usefixtures("coordinator_auto_assign")

CLASH = {"setup_minutes": 30, "turnaround_minutes": 45}


def _at(hour, minute=0, day=2, year=2030):
    return datetime(year, 11, day, hour, minute, tzinfo=timezone.utc)


def _world(client, db_session):
    staff, staff_h = user(client, db_session, Role.VENUE_STAFF, "vs@example.com", "Vera Staff")
    sam, sam_h = user(client, db_session, Role.COORDINATOR, "sam@example.com", "Sam Tan")
    kim, kim_h = user(client, db_session, Role.COORDINATOR, "kim@example.com", "Kim Lee")
    venue = _venue(db_session)
    return {
        "staff": staff, "staff_h": staff_h, "sam": sam, "sam_h": sam_h,
        "kim": kim, "kim_h": kim_h, "venue": venue,
    }


def _approved(db_session, w, start, end, coordinator="sam", status=BookingStatus.approved, venue=None, name="Gala"):
    """A booking of the venue for a new event, inserted directly."""
    organiser = _someone(db_session)
    event = Event(
        name=name, organiser_id=organiser.id, status=EventStatus.planning_event,
        coordinator_id=None if coordinator is None else w[coordinator].id,
    )
    db_session.add(event)
    db_session.flush()
    booking = VenueBooking(
        event_id=event.id, venue_id=(venue or w["venue"]).id, requested_by=organiser.id,
        start_time=start, end_time=end, status=status,
    )
    db_session.add(booking)
    db_session.commit()
    return booking


def _pair(db_session, w, **kw):
    """Two approved bookings that clash under 30/45: 10-12 and 13-15 (12:30-12:45 shared)."""
    return _approved(db_session, w, _at(10), _at(12), **kw), _approved(db_session, w, _at(13), _at(15), **kw)


def _put(client, w, body=CLASH, venue=None):
    return client.put(f"/venues/{(venue or w['venue']).id}/setup-turnaround", json=body, headers=w["staff_h"])


def _flagged(db_session, *bookings):
    db_session.expire_all()
    return [db_session.get(VenueBooking, b.id).conflict_flagged_at is not None for b in bookings]


def _notes(db_session, user_id):
    db_session.expire_all()
    return db_session.query(Notification).filter_by(user_id=user_id, type="venue_booking_conflict").all()


def _notes_any(db_session, user_id):
    db_session.expire_all()
    return db_session.query(Notification).filter_by(user_id=user_id).all()


def _log(db_session, event_id):
    db_session.expire_all()
    return [h.note for h in db_session.query(EventStatusHistory).filter_by(event_id=event_id).order_by(EventStatusHistory.id)]


# --- AC1: future approved bookings are re-checked on save ---------------------


def test_ac1_saving_buffers_flags_future_approved_bookings_that_now_clash(client, db_session):
    w = _world(client, db_session)
    a, b = _pair(db_session, w)
    res = _put(client, w)
    assert res.status_code == 200
    assert res.json()["recheck"] == {"flagged": 2, "cleared": 0}
    assert _flagged(db_session, a, b) == [True, True]


def test_ac1_recheck_is_only_in_the_save_response(client, db_session):
    w = _world(client, db_session)
    _pair(db_session, w)
    _put(client, w)
    assert client.get(f"/venues/{w['venue'].id}", headers=w["staff_h"]).json()["recheck"] is None


def test_ac1_no_clash_means_no_flag(client, db_session):
    w = _world(client, db_session)
    a = _approved(db_session, w, _at(10), _at(12))
    b = _approved(db_session, w, _at(16), _at(18))
    assert _put(client, w).json()["recheck"] == {"flagged": 0, "cleared": 0}
    assert _flagged(db_session, a, b) == [False, False]


def test_ac1_windows_that_exactly_touch_are_not_flagged(client, db_session):
    w = _world(client, db_session)
    a = _approved(db_session, w, _at(10), _at(12))  # occupies 09:30-12:45
    b = _approved(db_session, w, _at(13, 15), _at(15))  # occupies 12:45-15:45
    assert _put(client, w).json()["recheck"]["flagged"] == 0
    assert _flagged(db_session, a, b) == [False, False]
    # one minute closer and it clashes
    c = _approved(db_session, w, _at(13, 14), _at(15), name="Closer")
    assert _put(client, w, {"setup_minutes": 30, "turnaround_minutes": 46}).json()["recheck"]["flagged"] == 3
    assert _flagged(db_session, a, b, c) == [True, True, True]


def test_ac1_past_bookings_are_ignored(client, db_session):
    w = _world(client, db_session)
    a = _approved(db_session, w, _at(10, year=2020), _at(12, year=2020))
    b = _approved(db_session, w, _at(13, year=2020), _at(15, year=2020))
    assert _put(client, w).json()["recheck"] == {"flagged": 0, "cleared": 0}
    assert _flagged(db_session, a, b) == [False, False]
    assert _notes(db_session, w["sam"].id) == []


@pytest.mark.parametrize("other", [BookingStatus.pending, BookingStatus.rejected, BookingStatus.cancelled])
def test_ac1_only_approved_bookings_are_flagged_or_clash(client, db_session, other):
    w = _world(client, db_session)
    a = _approved(db_session, w, _at(10), _at(12))
    b = _approved(db_session, w, _at(13), _at(15), status=other)
    assert _put(client, w).json()["recheck"]["flagged"] == 0
    assert _flagged(db_session, a, b) == [False, False]


def test_ac1_other_venues_are_not_rechecked(client, db_session):
    w = _world(client, db_session)
    other = _venue(db_session, "Other Hall")
    a, b = _pair(db_session, w, venue=other)
    assert _put(client, w).json()["recheck"]["flagged"] == 0
    assert _flagged(db_session, a, b) == [False, False]


def test_ac1_saving_the_same_values_again_rechecks_nothing(client, db_session):
    w = _world(client, db_session)
    _pair(db_session, w)
    _put(client, w)
    again = _put(client, w)
    assert again.status_code == 200 and again.json()["recheck"] == {"flagged": 0, "cleared": 0}


def test_ac1_only_venue_staff_can_trigger_a_recheck(client, db_session):
    w = _world(client, db_session)
    a, b = _pair(db_session, w)
    res = client.put(f"/venues/{w['venue'].id}/setup-turnaround", json=CLASH, headers=w["sam_h"])
    assert res.status_code == 403
    assert _flagged(db_session, a, b) == [False, False]


def test_ac1_a_rejected_save_flags_nothing(client, db_session):
    w = _world(client, db_session)
    a, b = _pair(db_session, w)
    assert _put(client, w, {"setup_minutes": -5, "turnaround_minutes": 45}).status_code == 422
    assert _flagged(db_session, a, b) == [False, False]


# --- AC2: flagging keeps the booking and notifies the Coordinator once --------


def test_ac2_flagging_never_changes_status_and_notifies_the_coordinator_once(client, db_session):
    w = _world(client, db_session)
    a, b = _pair(db_session, w)
    _put(client, w)
    db_session.expire_all()
    assert db_session.get(VenueBooking, a.id).status == BookingStatus.approved
    assert db_session.get(VenueBooking, b.id).status == BookingStatus.approved
    assert db_session.query(VenueBooking).count() == 2
    assert len(_notes(db_session, w["sam"].id)) == 2  # one per flagged booking
    assert {n.event_id for n in _notes(db_session, w["sam"].id)} == {a.event_id, b.event_id}

    _put(client, w)  # same values: no second notification
    _put(client, w, {"setup_minutes": 40, "turnaround_minutes": 45})  # still flagged: no second one either
    assert len(_notes(db_session, w["sam"].id)) == 2


def test_ac2_only_that_events_coordinator_is_notified(client, db_session):
    w = _world(client, db_session)
    _approved(db_session, w, _at(10), _at(12), coordinator="sam")
    _approved(db_session, w, _at(13), _at(15), coordinator="kim")
    _put(client, w)
    assert len(_notes(db_session, w["sam"].id)) == 1
    assert len(_notes(db_session, w["kim"].id)) == 1
    assert _notes(db_session, w["staff"].id) == []
    assert db_session.query(Notification).count() == 2


def test_ac2_an_event_without_a_coordinator_is_flagged_without_a_notification(client, db_session):
    w = _world(client, db_session)
    a, b = _pair(db_session, w, coordinator=None)
    assert _put(client, w).json()["recheck"]["flagged"] == 2
    assert _flagged(db_session, a, b) == [True, True]
    assert db_session.query(Notification).count() == 0


def test_ac2_flagging_is_in_the_activity_log_with_the_actor(client, db_session):
    w = _world(client, db_session)
    a, _ = _pair(db_session, w)
    _put(client, w)
    [entry] = db_session.query(EventStatusHistory).filter_by(event_id=a.event_id).all()
    assert entry.changed_by == w["staff"].id and entry.created_at is not None
    assert entry.from_status == entry.to_status == EventStatus.planning_event
    assert "flagged" in entry.note


# --- AC3: un-flagged automatically when it no longer clashes ------------------


def test_ac3_a_later_save_that_removes_the_clash_clears_the_flag_with_a_log_line(client, db_session):
    w = _world(client, db_session)
    a, b = _pair(db_session, w)
    _put(client, w)
    res = _put(client, w, {"setup_minutes": 0, "turnaround_minutes": 0})
    assert res.json()["recheck"] == {"flagged": 0, "cleared": 2}
    assert _flagged(db_session, a, b) == [False, False]
    assert client.get("/venue-bookings/flagged", headers=w["staff_h"]).json() == []
    notes = _log(db_session, a.event_id)
    assert len(notes) == 2 and "cleared automatically" in notes[1]
    assert len(_notes(db_session, w["sam"].id)) == 2  # clearing does not notify again
    db_session.expire_all()
    assert db_session.get(VenueBooking, a.id).status == BookingStatus.approved


def test_ac3_a_booking_that_never_clashed_gets_no_log_line(client, db_session):
    w = _world(client, db_session)
    a = _approved(db_session, w, _at(10), _at(12))
    _put(client, w)
    assert _log(db_session, a.event_id) == []


# --- AC4: Venue Staff list flagged bookings with the overlap ------------------


def test_ac4_venue_staff_list_flagged_bookings_with_their_overlap_soonest_first(client, db_session):
    w = _world(client, db_session)
    a, b = _pair(db_session, w)
    _approved(db_session, w, _at(18), _at(19), name="Fine")
    _put(client, w)
    rows = client.get("/venue-bookings/flagged", headers=w["staff_h"]).json()
    assert [r["id"] for r in rows] == [a.id, b.id]
    assert all(r["conflict_flagged"] is True and r["status"] == "approved" for r in rows)
    [c] = rows[0]["conflicts"]
    assert c["booking_id"] == b.id
    assert c["overlap_start"].startswith("2030-11-02T12:30") and c["overlap_end"].startswith("2030-11-02T12:45")
    assert rows[1]["conflicts"][0]["booking_id"] == a.id
    single = client.get(f"/venue-bookings/{a.id}", headers=w["staff_h"]).json()
    assert single["conflict_flagged"] is True and len(single["conflicts"]) == 1


@pytest.mark.parametrize("role", [Role.COORDINATOR, Role.ORGANISER, Role.SAFETY_OFFICER])
def test_ac4_other_roles_cannot_list_flagged_bookings(client, db_session, role):
    w = _world(client, db_session)
    _pair(db_session, w)
    _put(client, w)
    _, headers = user(client, db_session, role, "x@example.com", "X")
    assert client.get("/venue-bookings/flagged", headers=headers).status_code == 403
    assert client.get("/venue-bookings/flagged").status_code == 401


def test_ac4_the_coordinator_sees_the_flag_but_never_another_events_name(client, db_session):
    w = _world(client, db_session)
    a, _ = _pair(db_session, w)
    _put(client, w)
    mine = client.get(f"/venue-bookings/events/{a.event_id}", headers=w["sam_h"]).json()
    assert [(m["conflict_flagged"], m["conflicts"]) for m in mine] == [(True, [])]


def test_ac4_an_unflagged_booking_reads_as_not_flagged(client, db_session):
    w = _world(client, db_session)
    a = _approved(db_session, w, _at(10), _at(12))
    assert client.get(f"/venue-bookings/{a.id}", headers=w["staff_h"]).json()["conflict_flagged"] is False


# --- AC5: a flagged booking is not "approved" for Submit / Safety approval ----


def test_ac5_a_flagged_booking_is_outstanding_and_blocks_submit_for_safety_check(client, db_session):
    s = _ready_setup(client, db_session)
    booking = _ready_booking(db_session, s, name="Hall A")
    event = db_session.get(Event, s["event_id"])
    assert outstanding_arrangements(db_session, event) == []

    booking.conflict_flagged_at = datetime.now(timezone.utc)
    db_session.commit()
    assert outstanding_arrangements(db_session, event) == [
        "Venue booking 'Hall A' has an unresolved conflict with another booking"
    ]
    res = _submit_for_check(client, s)
    assert res.status_code == 409
    assert "Venue booking 'Hall A' has an unresolved conflict with another booking" in str(res.json())
    db_session.expire_all()
    assert db_session.get(Event, s["event_id"]).status != EventStatus.awaiting_safety_check


def test_ac5_unflagged_booking_still_passes_frozen_literal(client, db_session):
    s = _ready_setup(client, db_session)
    _ready_booking(db_session, s)
    assert _submit_for_check(client, s).status_code == 200


def test_ac5_a_conflict_after_submitting_blocks_the_safety_officers_approval(client, db_session):
    s = _ready_setup(client, db_session)
    booking = _ready_booking(db_session, s, name="Hall A")
    assert _submit_for_check(client, s).status_code == 200
    booking.conflict_flagged_at = datetime.now(timezone.utc)
    db_session.commit()
    _, officer_h = user(client, db_session, Role.SAFETY_OFFICER, "so@example.com", "Sam Safety")
    res = client.post(f"/safety-checks/{s['event_id']}/approve", headers=officer_h)
    assert res.status_code == 409
    assert "Venue booking 'Hall A' has an unresolved conflict with another booking" in res.json()["detail"]


# --- AC6: resolved by keeping it with a reason, or by it no longer overlapping -


def _keep(client, w, booking, **body):
    return client.post(f"/venue-bookings/{booking.id}/keep-conflict", json=body, headers=w["staff_h"])


def test_ac6_keeping_a_flagged_booking_with_a_reason_clears_it_and_logs_actor_time_reason(client, db_session):
    w = _world(client, db_session)
    a, b = _pair(db_session, w)
    _put(client, w)
    res = _keep(client, w, a, reason="  Different rooms in the hall  ")
    assert res.status_code == 200
    assert res.json()["conflict_flagged"] is False and res.json()["status"] == "approved"
    assert _flagged(db_session, a, b) == [False, True]
    [flag, kept] = db_session.query(EventStatusHistory).filter_by(event_id=a.event_id).order_by(EventStatusHistory.id).all()
    assert kept.changed_by == w["staff"].id and kept.created_at is not None
    assert "Different rooms in the hall" in kept.note and "kept" in kept.note
    assert [r["id"] for r in client.get("/venue-bookings/flagged", headers=w["staff_h"]).json()] == [b.id]


@pytest.mark.parametrize("body", [{"reason": ""}, {"reason": "   "}, {}, {"reason": None}])
def test_ac6_a_blank_or_missing_reason_is_refused_and_nothing_changes(client, db_session, body):
    w = _world(client, db_session)
    a, b = _pair(db_session, w)
    _put(client, w)
    before = len(_log(db_session, a.event_id))
    assert _keep(client, w, a, **body).status_code == 422
    assert _flagged(db_session, a, b) == [True, True]
    assert len(_log(db_session, a.event_id)) == before


def test_ac6_keeping_twice_is_refused_and_state_is_unchanged(client, db_session):
    w = _world(client, db_session)
    a, _ = _pair(db_session, w)
    _put(client, w)
    assert _keep(client, w, a, reason="ok").status_code == 200
    log = _log(db_session, a.event_id)
    assert _keep(client, w, a, reason="again").status_code == 409
    assert _log(db_session, a.event_id) == log


def test_ac6_keep_conflict_guards(client, db_session):
    w = _world(client, db_session)
    a, _ = _pair(db_session, w)
    assert _keep(client, w, a, reason="x").status_code == 409  # not flagged
    assert client.post("/venue-bookings/99999/keep-conflict", json={"reason": "x"}, headers=w["staff_h"]).status_code == 404
    _put(client, w)
    for headers in (w["sam_h"], w["kim_h"]):
        res = client.post(f"/venue-bookings/{a.id}/keep-conflict", json={"reason": "x"}, headers=headers)
        assert res.status_code == 403
    assert client.post(f"/venue-bookings/{a.id}/keep-conflict", json={"reason": "x"}).status_code == 401
    assert _flagged(db_session, a)[0] is True


def test_ac6_rejecting_a_flagged_booking_clears_its_flag_and_the_other_ones(client, db_session):
    w = _world(client, db_session)
    a, b = _pair(db_session, w)
    _put(client, w)
    # A Safety Officer's re-review request is the only way an approved booking is decided again today.
    db_session.get(VenueBooking, a.id).safety_recheck_reason = "Look again"
    db_session.commit()
    res = client.post(f"/venue-bookings/{a.id}/reject", json={"reason": "Clashes"}, headers=w["staff_h"])
    assert res.status_code == 200 and res.json()["conflict_flagged"] is False
    assert _flagged(db_session, a, b) == [False, False]  # b no longer overlaps an approved booking
    assert client.get("/venue-bookings/flagged", headers=w["staff_h"]).json() == []


def test_ac6_a_kept_booking_is_not_reflagged_by_saving_the_same_values(client, db_session):
    w = _world(client, db_session)
    a, b = _pair(db_session, w)
    _put(client, w)
    _keep(client, w, a, reason="fine")
    _put(client, w)
    assert _flagged(db_session, a, b) == [False, True]
    assert len(_notes(db_session, w["sam"].id)) == 2


def test_ac1_an_active_hold_that_now_clashes_is_flagged_and_stays_a_hold(client, db_session):
    w = _world(client, db_session)
    hold = _approved(db_session, w, _at(10), _at(12), status=BookingStatus.hold, name="Held")
    approved = _approved(db_session, w, _at(13), _at(15))  # 12:30-12:45 shared under 30/45
    _put(client, w)
    # The hold is checked against approved bookings; a hold blocks nobody, so the approved one stays clear.
    assert _flagged(db_session, hold, approved) == [True, False]
    assert db_session.get(VenueBooking, hold.id).status == BookingStatus.hold  # not cancelled or changed
    assert len(_notes(db_session, w["sam"].id)) == 1  # the hold's Coordinator is told


def test_ac1_a_hold_that_does_not_clash_is_not_flagged(client, db_session):
    w = _world(client, db_session)
    hold = _approved(db_session, w, _at(10), _at(12), status=BookingStatus.hold)
    far = _approved(db_session, w, _at(18), _at(20))
    _put(client, w)
    assert _flagged(db_session, hold, far) == [False, False]


def test_ac1_a_past_hold_is_not_rechecked(client, db_session):
    w = _world(client, db_session)
    past = _approved(db_session, w, _at(10, year=2020), _at(12, year=2020), status=BookingStatus.hold)
    _approved(db_session, w, _at(13, year=2020), _at(15, year=2020))
    _put(client, w)
    assert _flagged(db_session, past) == [False]


def _cancel(client, w, booking, **body):
    body = body or {"reason": "Venue needs the slot"}
    return client.post(f"/venue-bookings/{booking.id}/cancel-flagged", json=body, headers=w["staff_h"])


def test_ac6_venue_staff_cancel_a_flagged_booking_flag_cleared_logged_and_coordinator_told(client, db_session):
    w = _world(client, db_session)
    a, b = _pair(db_session, w)
    _put(client, w)
    res = _cancel(client, w, a, reason="  Double booked by mistake  ")
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled" and res.json()["conflict_flagged"] is False
    assert _flagged(db_session, a, b) == [False, False]  # b only clashed with a
    db_session.expire_all()
    assert db_session.get(Event, a.event_id).status == EventStatus.planning_event  # the Event is not cancelled
    notes = _log(db_session, a.event_id)
    assert any("cancelled by Venue Staff" in n and "Double booked by mistake" in n for n in notes)
    told = [n.message for n in _notes_any(db_session, w["sam"].id)]
    assert any("cancelled your booking" in m and "Double booked by mistake" in m for m in told)
    assert client.get("/venue-bookings/flagged", headers=w["staff_h"]).json() == []


def test_ac6_cancel_needs_a_reason_and_changes_nothing_without_one(client, db_session):
    w = _world(client, db_session)
    a, b = _pair(db_session, w)
    _put(client, w)
    for body in ({"reason": ""}, {"reason": "   "}, {}):
        assert client.post(f"/venue-bookings/{a.id}/cancel-flagged", json=body, headers=w["staff_h"]).status_code == 422
    assert _flagged(db_session, a, b) == [True, True]
    assert db_session.get(VenueBooking, a.id).status == BookingStatus.approved


def test_ac6_cancel_guards(client, db_session):
    w = _world(client, db_session)
    a, _ = _pair(db_session, w)
    assert _cancel(client, w, a).status_code == 409  # not flagged: nothing to resolve
    assert client.post("/venue-bookings/99999/cancel-flagged", json={"reason": "x"}, headers=w["staff_h"]).status_code == 404
    _put(client, w)
    for headers in (w["sam_h"], w["kim_h"]):
        assert client.post(f"/venue-bookings/{a.id}/cancel-flagged", json={"reason": "x"}, headers=headers).status_code == 403
    assert client.post(f"/venue-bookings/{a.id}/cancel-flagged", json={"reason": "x"}).status_code == 401
    assert db_session.get(VenueBooking, a.id).status == BookingStatus.approved
    assert _cancel(client, w, a).status_code == 200
    assert _cancel(client, w, a).status_code == 409  # twice is a no-op


def test_ac6_a_flagged_booking_that_is_cancelled_is_cleared_and_logged(client, db_session):
    from app.services.booking_conflict_flags import booking_changed

    w = _world(client, db_session)
    a, b = _pair(db_session, w)
    _put(client, w)
    assert _flagged(db_session, a, b) == [True, True]
    a = db_session.get(VenueBooking, a.id)
    a.status = BookingStatus.cancelled
    assert booking_changed(db_session, a, w["staff"]) is True
    db_session.commit()
    assert _flagged(db_session, a, b) == [False, False]  # b no longer overlaps an approved booking
    assert any("cancelled" in n and "cleared" in n for n in _log(db_session, a.event_id))


def test_ac6_a_booking_changed_so_it_no_longer_overlaps_is_cleared(client, db_session):
    from app.services.booking_conflict_flags import booking_changed

    w = _world(client, db_session)
    a, b = _pair(db_session, w)
    _put(client, w)
    b = db_session.get(VenueBooking, b.id)
    b.start_time, b.end_time = _at(16), _at(18)  # moved clear of the buffers
    assert booking_changed(db_session, b, w["staff"]) is True
    db_session.commit()
    assert _flagged(db_session, a, b) == [False, False]
    assert any("cleared automatically" in n for n in _log(db_session, b.event_id))


def test_ac6_booking_changed_leaves_a_still_clashing_flag_and_an_unflagged_booking_alone(client, db_session):
    from app.services.booking_conflict_flags import booking_changed

    w = _world(client, db_session)
    a, b = _pair(db_session, w)
    assert booking_changed(db_session, db_session.get(VenueBooking, a.id), w["staff"]) is False  # never flagged
    _put(client, w)
    assert booking_changed(db_session, db_session.get(VenueBooking, a.id), w["staff"]) is False  # still clashes
    assert _flagged(db_session, a, b) == [True, True]


def test_ac6_a_save_also_clears_the_flag_of_a_booking_cancelled_since(client, db_session):
    w = _world(client, db_session)
    a, b = _pair(db_session, w)
    _put(client, w)
    db_session.get(VenueBooking, a.id).status = BookingStatus.cancelled
    db_session.commit()
    _put(client, w, {"setup_minutes": 30, "turnaround_minutes": 50})
    assert _flagged(db_session, a)[0] is False


# --- frozen literals: behaviour the story could affect ------------------------


def test_frozen_approve_still_refuses_a_clash_and_pending_conflicts_still_show(client, db_session):
    w = _world(client, db_session)
    a = _approved(db_session, w, _at(10), _at(12))
    _put(client, w)
    organiser = _someone(db_session)
    event = Event(name="New", organiser_id=organiser.id, status=EventStatus.planning_event)
    db_session.add(event)
    db_session.flush()
    pending = VenueBooking(
        event_id=event.id, venue_id=w["venue"].id, requested_by=organiser.id,
        start_time=_at(13), end_time=_at(15), status=BookingStatus.pending,
    )
    db_session.add(pending)
    db_session.commit()
    row = client.get(f"/venue-bookings/{pending.id}", headers=w["staff_h"]).json()
    assert [c["booking_id"] for c in row["conflicts"]] == [a.id] and row["conflict_flagged"] is False
    res = client.post(f"/venue-bookings/{pending.id}/approve", headers=w["staff_h"])
    assert res.status_code == 409 and "already booked" in res.json()["detail"]
