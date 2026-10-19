"""Tests for "Request Replacement Venue for Affected Booking" (SCRUM-95).

    AC1  'Find replacement' on a flagged booking: the replacement request is
         made for that booking's own date/time and needs (frontend prefill)
    AC2  Venue Staff open the request and see which booking it replaces
    AC3  approved replacement: original is 'replaced', kept in history; the
         Event's other bookings are unchanged
    AC4  a confirmed Event returns to 'Planning Event' when a replacement for
         one of its bookings is approved; the Coordinator is told
    AC5  once Approved + Reserved the Event can be submitted again;
         registration stays blocked until it passes the Safety Check again
"""

import pytest

from app.core.roles import Role
from app.models.enums import BookingStatus, EventStatus
from app.models.events import Event, EventStatusHistory
from app.models.notifications import Notification
from app.models.venues import VenueBooking
from tests.event_review_test_helpers import user
from tests.test_booking_conflict_flags import _approved, _at, _flagged, _world
from tests.test_submit_for_safety_check import _booking as _ready_booking
from tests.test_submit_for_safety_check import _setup as _ready_setup
from tests.test_submit_for_safety_check import _submit as _submit_for_check
from tests.test_venue_booking_request import _venue

pytestmark = pytest.mark.usefixtures("coordinator_auto_assign")


def _close(client, w, start=_at(9), end=_at(13)):
    res = client.post(
        f"/venues/{w['venue'].id}/unavailability",
        json={"start_time": start.isoformat(), "end_time": end.isoformat(), "reason_category": "Maintenance"},
        headers=w["staff_h"],
    )
    assert res.status_code == 201, res.text


def _replace(client, w, booking, venue, headers=None, **extra):
    return client.post(
        f"/venue-bookings/{booking.id}/replacement",
        json={"venue_id": venue.id, **extra},
        headers=headers or w["sam_h"],
    )


def _flagged_world(client, db_session):
    w = _world(client, db_session)
    original = _approved(db_session, w, _at(10), _at(12))
    other = _venue(db_session, "Other Hall")
    _close(client, w)
    assert _flagged(db_session, original) == [True]
    return w, original, other


def _notes(db_session, user_id, type):
    db_session.expire_all()
    return [n.message for n in db_session.query(Notification).filter_by(user_id=user_id, type=type)]


# --- AC1/AC2 ---------------------------------------------------------------


def test_ac1_ac2_replacement_uses_the_originals_time_and_shows_what_it_replaces(client, db_session):
    w, original, other = _flagged_world(client, db_session)

    res = _replace(client, w, original, other, expected_attendance=40)

    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "pending"
    assert body["venue"]["id"] == other.id
    assert body["start_time"].startswith("2030-11-02T10:00") and body["end_time"].startswith("2030-11-02T12:00")
    assert body["replaces"]["id"] == original.id
    queue = client.get("/venue-bookings/queue", headers=w["staff_h"]).json()
    assert [q["replaces"]["id"] for q in queue] == [original.id]
    assert queue[0]["replaces"]["venue"]["name"] == "Marina Hall"
    one = client.get(f"/venue-bookings/{body['id']}", headers=w["staff_h"]).json()
    assert one["replaces"]["id"] == original.id


def test_ac2_ordinary_request_replaces_nothing(client, db_session):
    w = _world(client, db_session)
    booking = _approved(db_session, w, _at(10), _at(12), status=BookingStatus.pending)
    assert client.get(f"/venue-bookings/{booking.id}", headers=w["staff_h"]).json()["replaces"] is None


def test_ac1_only_a_flagged_booking_can_be_replaced(client, db_session):
    w = _world(client, db_session)
    booking = _approved(db_session, w, _at(10), _at(12))
    other = _venue(db_session, "Other Hall")
    assert _replace(client, w, booking, other).status_code == 409
    assert db_session.query(VenueBooking).count() == 1


def test_negative_replacement_of_someone_elses_booking_is_404_and_staff_are_denied(client, db_session):
    w, original, other = _flagged_world(client, db_session)
    assert _replace(client, w, original, other, headers=w["kim_h"]).status_code == 404
    assert _replace(client, w, original, other, headers=w["staff_h"]).status_code == 403
    assert db_session.query(VenueBooking).count() == 1


def test_negative_second_replacement_and_same_venue_are_refused(client, db_session):
    w, original, other = _flagged_world(client, db_session)
    assert _replace(client, w, original, w["venue"]).status_code == 409
    assert _replace(client, w, original, other).status_code == 201
    third = _venue(db_session, "Third Hall")
    assert _replace(client, w, original, third).status_code == 409
    assert db_session.query(VenueBooking).count() == 2


def test_negative_unknown_venue_is_422(client, db_session):
    w, original, _ = _flagged_world(client, db_session)
    res = client.post(f"/venue-bookings/{original.id}/replacement", json={"venue_id": 99999}, headers=w["sam_h"])
    assert res.status_code == 422


# --- AC3 -------------------------------------------------------------------


def test_ac3_approving_the_replacement_marks_the_original_replaced_and_keeps_history(client, db_session):
    w, original, other = _flagged_world(client, db_session)
    event_id = original.event_id
    sibling_venue = _venue(db_session, "Sibling Hall")
    sibling = VenueBooking(
        event_id=event_id, venue_id=sibling_venue.id, requested_by=w["sam"].id,
        start_time=_at(10), end_time=_at(12), status=BookingStatus.approved,
    )
    db_session.add(sibling)
    db_session.commit()
    new = _replace(client, w, original, other).json()

    res = client.post(f"/venue-bookings/{new['id']}/approve", headers=w["staff_h"])

    assert res.status_code == 200, res.text
    db_session.expire_all()
    assert db_session.get(VenueBooking, original.id).status == BookingStatus.replaced
    assert db_session.get(VenueBooking, original.id).conflict_flagged_at is None
    assert db_session.get(VenueBooking, new["id"]).status == BookingStatus.approved
    assert db_session.get(VenueBooking, sibling.id).status == BookingStatus.approved
    listed = client.get(f"/venue-bookings/events/{event_id}", headers=w["sam_h"]).json()
    by_id = {b["id"]: b for b in listed}
    assert by_id[original.id]["status"] == "replaced"
    assert by_id[new["id"]]["replaces"]["id"] == original.id
    notes = [h.note for h in db_session.query(EventStatusHistory).filter_by(event_id=event_id)]
    assert any("replaced by 'Other Hall'" in n for n in notes)


def test_ac3_rejecting_the_replacement_leaves_the_original_alone(client, db_session):
    w, original, other = _flagged_world(client, db_session)
    new = _replace(client, w, original, other).json()
    res = client.post(f"/venue-bookings/{new['id']}/reject", json={"reason": "No"}, headers=w["staff_h"])
    assert res.status_code == 200
    db_session.expire_all()
    assert db_session.get(VenueBooking, original.id).status == BookingStatus.approved
    assert _replace(client, w, original, _venue(db_session, "Third Hall")).status_code == 201


def test_ac3_a_replaced_booking_does_not_block_readiness(client, db_session):
    s = _ready_setup(client, db_session)
    _ready_booking(db_session, s, "Hall A")
    _ready_booking(db_session, s, "Old Hall", BookingStatus.replaced)
    db_session.get(Event, s["event_id"]).status = EventStatus.planning_event
    db_session.commit()
    assert _submit_for_check(client, s).status_code == 200


# --- AC4 -------------------------------------------------------------------


def _confirmed(db_session, original):
    event = db_session.get(Event, original.event_id)
    event.status = EventStatus.safety_check_passed
    event.registration_enabled = True
    db_session.commit()
    return event


def _officer(client, db_session):
    return user(client, db_session, Role.SAFETY_OFFICER, "so@example.com", "Sofia Safety")[0]


def _confirmed_flagged_world(client, db_session):
    w = _world(client, db_session)
    original = _approved(db_session, w, _at(10), _at(12))
    other = _venue(db_session, "Other Hall")
    _confirmed(db_session, original)
    _close(client, w)
    assert _flagged(db_session, original) == [True]
    return w, original, other


def _approve_replacement(client, w, original, other):
    new = _replace(client, w, original, other)
    assert new.status_code == 201, new.text
    res = client.post(f"/venue-bookings/{new.json()['id']}/approve", headers=w["staff_h"])
    assert res.status_code == 200, res.text
    return original.event_id


def test_ac4_approved_replacement_returns_a_confirmed_event_to_planning_and_tells_the_coordinator(
    client, db_session
):
    w, original, other = _confirmed_flagged_world(client, db_session)
    officer = _officer(client, db_session)
    event_id = _approve_replacement(client, w, original, other)

    db_session.expire_all()
    event = db_session.get(Event, event_id)
    assert event.status == EventStatus.planning_event  # not cancelled
    assert len(_notes(db_session, w["sam"].id, "event_returned_to_planning")) == 1
    assert _notes(db_session, event.organiser_id, "event_returned_to_planning") == []
    assert _notes(db_session, officer.id, "event_returned_to_planning") == []
    log = db_session.query(EventStatusHistory).filter_by(event_id=event_id).all()
    assert any(
        h.from_status == EventStatus.safety_check_passed and h.to_status == EventStatus.planning_event
        for h in log
    )


def test_ac4_negative_the_event_stays_confirmed_until_the_replacement_is_approved(client, db_session):
    w, original, other = _confirmed_flagged_world(client, db_session)  # booking now unavailable
    db_session.expire_all()
    assert db_session.get(Event, original.event_id).status == EventStatus.safety_check_passed
    new = _replace(client, w, original, other)  # requesting is allowed on a confirmed Event
    assert new.status_code == 201, new.text
    assert client.post(f"/venue-bookings/{new.json()['id']}/reject", json={"reason": "No"}, headers=w["staff_h"]).status_code == 200
    db_session.expire_all()
    assert db_session.get(Event, original.event_id).status == EventStatus.safety_check_passed
    assert _notes(db_session, w["sam"].id, "event_returned_to_planning") == []


def test_ac4_negative_an_event_in_planning_is_not_notified_when_a_replacement_is_approved(client, db_session):
    w, original, other = _flagged_world(client, db_session)
    event_id = _approve_replacement(client, w, original, other)
    db_session.expire_all()
    assert db_session.get(Event, event_id).status == EventStatus.planning_event
    assert _notes(db_session, w["sam"].id, "event_returned_to_planning") == []


# --- AC5 -------------------------------------------------------------------


def test_ac5_resubmit_after_replacement_and_registration_blocked_meanwhile(client, db_session):
    w, original, other = _confirmed_flagged_world(client, db_session)
    _, att_h = user(client, db_session, Role.ATTENDEE, "att@example.com", "Ann Attendee")
    event_id = _approve_replacement(client, w, original, other)
    s = {"sam_h": w["sam_h"], "event_id": event_id}

    db_session.expire_all()
    assert db_session.get(Event, event_id).status == EventStatus.planning_event
    assert client.post(f"/events/{event_id}/register", headers=att_h).status_code in (403, 404, 409)
    assert _submit_for_check(client, s).status_code == 200  # replaced original is ignored, new one Approved
    db_session.expire_all()
    assert db_session.get(Event, event_id).status == EventStatus.awaiting_safety_check
    assert client.post(f"/events/{event_id}/register", headers=att_h).status_code in (403, 404, 409)


def test_ac5_negative_cannot_resubmit_while_the_replacement_is_still_pending(client, db_session):
    w, original, other = _confirmed_flagged_world(client, db_session)
    assert _replace(client, w, original, other).status_code == 201
    db_session.expire_all()
    event = db_session.get(Event, original.event_id)
    event.status = EventStatus.planning_event
    db_session.commit()
    s = {"sam_h": w["sam_h"], "event_id": original.event_id}
    assert _submit_for_check(client, s).status_code != 200  # a Pending booking is not Approved
