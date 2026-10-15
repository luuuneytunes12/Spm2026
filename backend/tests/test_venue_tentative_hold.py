"""Tests for "Place a Tentative Hold on a Venue with an expiry".

    As Venue Staff, I want to place a tentative hold on a Venue with an
    expiry date/time, so that an Event Coordinator can finalise arrangements
    without the Venue being blocked forever.

    AC1  placing a hold needs an expiry date/time and the action the
         Coordinator must complete
    AC2  a missing or past expiry is not saved and the field is named
    AC3  an active hold is treated as occupied for availability and conflicts
    AC4  the calendar and the Event show "Tentative hold", its expiry and
         the required action
    AC5  approving a held booking makes it an approved Venue Booking
    AC6  a hold does not count as approved for Submit for Safety Check
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.roles import Role
from app.domain.event_readiness import outstanding_arrangements
from app.models.enums import BookingStatus, EventStatus, NotificationType
from app.models.events import Event, EventStatusHistory
from app.models.notifications import Notification
from app.models.venues import VenueBooking
from tests.event_review_test_helpers import user
from tests.test_submit_for_safety_check import _booking as _ready_booking
from tests.test_submit_for_safety_check import _setup as _ready_setup
from tests.test_submit_for_safety_check import _submit as _submit_for_check
from tests.test_venue_booking_decision import _setup
from tests.test_venue_search import _someone

pytestmark = pytest.mark.usefixtures("coordinator_auto_assign")

ACTION = "Confirm final headcount and pay the deposit."


def _later(hours=48):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def _hold(client, headers, booking_id, **body):
    return client.post(f"/venue-bookings/{booking_id}/hold", json=body, headers=headers)


def _place(client, s, expires_at=None, action=ACTION):
    return _hold(client, s["staff_h"], s["booking_id"], expires_at=expires_at or _later(), required_action=action)


def _status(db_session, booking_id):
    db_session.expire_all()
    return db_session.get(VenueBooking, booking_id).status


def _locs(response):
    return [tuple(e["loc"]) for e in response.json()["detail"]]


def _window_around(db_session, booking_id):
    b = db_session.get(VenueBooking, booking_id)
    return {
        "start": (b.start_time - timedelta(hours=1)).isoformat(),
        "end": (b.end_time + timedelta(hours=1)).isoformat(),
    }


# --- AC1: an expiry and a required action -----------------------------------


def test_ac1_a_hold_stores_its_expiry_and_required_action(client, db_session):
    s = _setup(client, db_session)
    expiry = datetime.now(timezone.utc) + timedelta(days=3)

    res = _place(client, s, expires_at=expiry.isoformat())

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == BookingStatus.tentative_hold
    returned = datetime.fromisoformat(body["expires_at"].replace("Z", "+00:00"))
    assert returned.replace(tzinfo=returned.tzinfo or timezone.utc) == expiry
    assert body["hold_action"] == ACTION
    db_session.expire_all()
    stored = db_session.get(VenueBooking, s["booking_id"])
    assert stored.hold_action == ACTION and stored.reviewed_by == s["staff"].id


def test_ac1_the_coordinator_is_told_the_expiry_and_the_action(client, db_session):
    s = _setup(client, db_session)
    assert _place(client, s).status_code == 200

    note = (
        db_session.query(Notification)
        .filter_by(event_id=s["event_id"], type=NotificationType.venue_hold_expiring)
        .one()
    )
    assert note.user_id == db_session.get(Event, s["event_id"]).coordinator_id
    assert ACTION in note.message and "will expire" in note.message


def test_ac1_placing_a_hold_is_in_the_events_activity_log_with_who_and_what(client, db_session):
    s = _setup(client, db_session)
    assert _place(client, s).status_code == 200

    [entry] = [
        h for h in db_session.query(EventStatusHistory).filter_by(event_id=s["event_id"])
        if (h.note or "").startswith("Tentative hold placed")
    ]
    assert entry.changed_by == s["staff"].id and entry.created_at is not None
    assert s["venue"].name in entry.note and ACTION in entry.note
    assert entry.from_status == entry.to_status  # the Event status is unchanged


def test_ac1_the_action_is_trimmed(client, db_session):
    s = _setup(client, db_session)
    assert _place(client, s, action=f"  {ACTION}  ").json()["hold_action"] == ACTION


@pytest.mark.parametrize("who", ["coord_h", "org_h"])
def test_ac1_negative_only_venue_staff_can_place_a_hold(client, db_session, who):
    s = _setup(client, db_session)
    res = _hold(client, s[who], s["booking_id"], expires_at=_later(), required_action=ACTION)
    assert res.status_code == 403
    assert _status(db_session, s["booking_id"]) == BookingStatus.pending


def test_ac1_negative_only_a_pending_request_can_be_held(client, db_session):
    s = _setup(client, db_session)
    assert client.post(f"/venue-bookings/{s['booking_id']}/approve", headers=s["staff_h"]).status_code == 200
    assert _place(client, s).status_code == 409
    assert _status(db_session, s["booking_id"]) == BookingStatus.approved


# --- AC2: missing or past expiry is refused, naming the field ---------------


def test_ac2_a_missing_expiry_is_not_saved_and_the_field_is_named(client, db_session):
    s = _setup(client, db_session)
    res = _hold(client, s["staff_h"], s["booking_id"], required_action=ACTION)
    assert res.status_code == 422
    assert ("body", "expires_at") in _locs(res)
    assert _status(db_session, s["booking_id"]) == BookingStatus.pending


@pytest.mark.parametrize("minutes_ago", [1, 0])
def test_ac2_a_past_expiry_is_not_saved_and_the_field_is_named(client, db_session, minutes_ago):
    s = _setup(client, db_session)
    past = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()
    res = _place(client, s, expires_at=past)
    assert res.status_code == 422
    assert _locs(res) == [("body", "expires_at")]
    assert "future" in res.json()["detail"][0]["msg"]
    assert _status(db_session, s["booking_id"]) == BookingStatus.pending
    assert db_session.query(Notification).filter_by(type=NotificationType.venue_hold_expiring).count() == 0


@pytest.mark.parametrize("action", [None, "", "   "])
def test_ac2_a_missing_required_action_is_not_saved_and_the_field_is_named(client, db_session, action):
    s = _setup(client, db_session)
    body = {"expires_at": _later()}
    if action is not None:
        body["required_action"] = action
    res = _hold(client, s["staff_h"], s["booking_id"], **body)
    assert res.status_code == 422
    assert ("body", "required_action") in _locs(res)
    assert _status(db_session, s["booking_id"]) == BookingStatus.pending


# --- AC3: an active hold is occupied ----------------------------------------


def _rival(db_session, s):
    """Another event's pending request for the same venue at the same time."""
    held = db_session.get(VenueBooking, s["booking_id"])
    organiser = _someone(db_session)
    event = Event(name="Rival Gala", organiser_id=organiser.id, status=EventStatus.planning_event)
    db_session.add(event)
    db_session.flush()
    rival = VenueBooking(
        event_id=event.id, venue_id=held.venue_id, requested_by=organiser.id,
        start_time=held.start_time, end_time=held.end_time,
    )
    db_session.add(rival)
    db_session.commit()
    return rival


def test_ac3_an_active_hold_is_a_conflict_for_another_events_request(client, db_session):
    s = _setup(client, db_session)
    assert _place(client, s).status_code == 200
    rival = _rival(db_session, s)

    res = client.get(f"/venue-bookings/{rival.id}", headers=s["staff_h"])

    assert [(c["booking_id"], c["status"]) for c in res.json()["conflicts"]] == [
        (s["booking_id"], BookingStatus.tentative_hold)
    ]


def test_ac3_an_active_hold_is_busy_in_availability(client, db_session):
    s = _setup(client, db_session)
    assert _place(client, s).status_code == 200
    res = client.get(
        f"/venues/{s['venue'].id}/availability",
        params=_window_around(db_session, s["booking_id"]),
        headers=s["coord_h"],
    )
    assert [b["kind"] for b in res.json()["busy"]] == ["tentative_hold"]


def test_ac3_frozen_literal_an_expired_hold_no_longer_occupies(client, db_session):
    s = _setup(client, db_session)
    assert _place(client, s).status_code == 200
    held = db_session.get(VenueBooking, s["booking_id"])
    held.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()
    rival = _rival(db_session, s)

    assert client.get(f"/venue-bookings/{rival.id}", headers=s["staff_h"]).json()["conflicts"] == []
    assert _status(db_session, s["booking_id"]) == BookingStatus.cancelled


# --- AC4: shown with expiry and action ---------------------------------------


def test_ac4_the_calendar_shows_the_hold_its_expiry_and_action_to_venue_staff(client, db_session):
    s = _setup(client, db_session)
    expires = _place(client, s).json()["expires_at"]
    res = client.get(
        f"/venues/{s['venue'].id}/availability",
        params=_window_around(db_session, s["booking_id"]),
        headers=s["staff_h"],
    )
    [item] = res.json()["items"]
    assert (item["kind"], item["expires_at"], item["hold_action"]) == ("tentative_hold", expires, ACTION)
    assert res.json()["busy"][0]["hold_action"] == ACTION


def test_ac4_a_coordinator_sees_the_calendar_hold_but_not_another_events_action(client, db_session):
    s = _setup(client, db_session)
    assert _place(client, s).status_code == 200
    [item] = client.get(
        f"/venues/{s['venue'].id}/availability",
        params=_window_around(db_session, s["booking_id"]),
        headers=s["coord_h"],
    ).json()["items"]
    assert item["kind"] == "tentative_hold" and item["expires_at"] is not None
    assert item["hold_action"] is None and item["event_name"] is None


def test_ac4_the_events_coordinator_sees_the_hold_expiry_and_action(client, db_session):
    s = _setup(client, db_session)
    expires = _place(client, s).json()["expires_at"]
    [mine] = client.get(f"/venue-bookings/events/{s['event_id']}", headers=s["coord_h"]).json()
    assert (mine["status"], mine["expires_at"], mine["hold_action"]) == (
        BookingStatus.tentative_hold, expires, ACTION,
    )


def test_ac4_a_held_request_stays_in_the_staff_queue_with_its_action(client, db_session):
    s = _setup(client, db_session)
    assert _place(client, s).status_code == 200
    [row] = client.get("/venue-bookings/queue", headers=s["staff_h"]).json()
    assert (row["id"], row["hold_action"]) == (s["booking_id"], ACTION)


# --- AC5: approve turns the hold into an approved booking --------------------


def test_ac5_approving_a_hold_makes_it_an_approved_booking(client, db_session):
    s = _setup(client, db_session)
    assert _place(client, s).status_code == 200

    res = client.post(f"/venue-bookings/{s['booking_id']}/approve", headers=s["staff_h"])

    assert res.status_code == 200
    body = res.json()
    assert (body["status"], body["expires_at"], body["hold_action"]) == (BookingStatus.approved, None, None)
    assert client.get("/venue-bookings/queue", headers=s["staff_h"]).json() == []


def test_ac5_frozen_literal_rejecting_a_hold_releases_it(client, db_session):
    s = _setup(client, db_session)
    assert _place(client, s).status_code == 200
    res = client.post(
        f"/venue-bookings/{s['booking_id']}/reject", json={"reason": "Fell through."}, headers=s["staff_h"]
    )
    assert (res.json()["status"], res.json()["hold_action"]) == (BookingStatus.rejected, None)


# --- AC6: a hold is not an approved booking for Safety Check -----------------


def test_ac6_a_hold_is_outstanding_and_blocks_submit_for_safety_check(client, db_session):
    s = _ready_setup(client, db_session)
    booking = _ready_booking(db_session, s, name="Hall A", status=BookingStatus.pending)
    _, staff_h = user(client, db_session, Role.VENUE_STAFF, "vs@example.com", "Vera Staff")
    assert _hold(client, staff_h, booking.id, expires_at=_later(), required_action=ACTION).status_code == 200

    event = db_session.get(Event, s["event_id"])
    assert outstanding_arrangements(db_session, event) == [
        "Venue booking 'Hall A' is not approved (status: tentative_hold)"
    ]
    res = _submit_for_check(client, s)
    assert res.status_code == 409
    db_session.expire_all()
    assert db_session.get(Event, s["event_id"]).status != EventStatus.awaiting_safety_check


def test_ac6_frozen_literal_once_approved_the_held_booking_passes(client, db_session):
    s = _ready_setup(client, db_session)
    booking = _ready_booking(db_session, s, name="Hall A", status=BookingStatus.pending)
    _, staff_h = user(client, db_session, Role.VENUE_STAFF, "vs@example.com", "Vera Staff")
    assert _hold(client, staff_h, booking.id, expires_at=_later(), required_action=ACTION).status_code == 200
    assert client.post(f"/venue-bookings/{booking.id}/approve", headers=staff_h).status_code == 200
    assert _submit_for_check(client, s).status_code == 200
