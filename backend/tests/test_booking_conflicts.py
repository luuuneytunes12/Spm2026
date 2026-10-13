"""Tests for "Identify Booking Conflicts" (SCRUM-41), AC1-AC5.

A pending request is flagged to Venue Staff with every APPROVED booking of the
same venue whose occupied period (event +/- setup/turnaround) strictly
overlaps; the availability calendar lists those periods as busy.
"""

from datetime import datetime, timezone

import pytest

from app.core.roles import Role
from app.models.enums import BookingStatus
from app.models.events import Event
from app.models.venues import VenueBooking, VenueUnavailability
from tests.test_venue_booking_decision import _approve, _setup
from tests.test_venue_search import _headers

pytestmark = pytest.mark.usefixtures("coordinator_auto_assign")

# The request under review (from _setup) is 2026-11-02 09:00-17:00 UTC.


def _at(hour, minute=0, day=2):
    return datetime(2026, 11, day, hour, minute, tzinfo=timezone.utc)


def _other(db_session, s, start, end, status=BookingStatus.approved, name="Alumni Gala"):
    """Another event's booking of the same venue, inserted directly."""
    organiser = db_session.get(Event, s["event_id"]).organiser_id
    event = Event(name=name, organiser_id=organiser)
    db_session.add(event)
    db_session.flush()
    booking = VenueBooking(
        event_id=event.id,
        venue_id=s["venue"].id,
        requested_by=organiser,
        start_time=start,
        end_time=end,
        status=status,
    )
    db_session.add(booking)
    db_session.commit()
    return booking


def _buffers(db_session, s, setup, turnaround):
    s["venue"].setup_minutes, s["venue"].turnaround_minutes = setup, turnaround
    db_session.commit()


def _review(client, s):
    return client.get(f"/venue-bookings/{s['booking_id']}", headers=s["staff_h"])


def _conflicts(client, s):
    return _review(client, s).json()["conflicts"]


# --- AC1: overlap with an approved booking is flagged during review ----------


def test_ac1_overlap_with_an_approved_booking_is_flagged_on_get_and_queue(client, db_session):
    s = _setup(client, db_session)
    other = _other(db_session, s, _at(15), _at(20))
    [c] = _conflicts(client, s)
    assert c["booking_id"] == other.id and c["event_id"] == other.event_id
    assert c["event_name"] == "Alumni Gala"
    [queued] = client.get("/venue-bookings/queue", headers=s["staff_h"]).json()
    assert [x["booking_id"] for x in queued["conflicts"]] == [other.id]


def test_ac1_buffers_widen_the_overlap(client, db_session):
    s = _setup(client, db_session)
    _other(db_session, s, _at(17, 30), _at(20))  # starts 30 min after the request ends
    assert _conflicts(client, s) == []
    _buffers(db_session, s, 60, 0)  # its setup starts 16:30, inside the request
    [c] = _conflicts(client, s)
    assert c["occupied_start"].startswith("2026-11-02T16:30")
    assert c["event_start"].startswith("2026-11-02T17:30")


def test_ac1_no_overlap_means_no_conflicts(client, db_session):
    s = _setup(client, db_session)
    _other(db_session, s, _at(10, day=9), _at(12, day=9))  # a week later
    other_venue_booking = _other(db_session, s, _at(10), _at(12))
    other_venue_booking.venue_id = _second_venue(db_session).id
    db_session.commit()
    assert _conflicts(client, s) == []


def _second_venue(db_session):
    from tests.test_venue_booking_request import _venue

    return _venue(db_session, "Elsewhere Hall")


def test_ac1_approve_409_names_the_conflict_and_changes_nothing(client, db_session):
    s = _setup(client, db_session)
    _other(db_session, s, _at(15), _at(20))
    res = _approve(client, s["staff_h"], s["booking_id"])
    assert res.status_code == 409
    detail = res.json()["detail"]
    assert "already booked" in detail and "Alumni Gala" in detail
    assert "2026-11-02 15:00 to 2026-11-02 17:00" in detail
    db_session.expire_all()
    assert db_session.get(VenueBooking, s["booking_id"]).status == BookingStatus.pending


# --- AC2: availability calendar shows the occupied period as busy ------------


def _availability(client, headers, venue_id, start, end):
    return client.get(
        f"/venues/{venue_id}/availability",
        params={"start": start.isoformat(), "end": end.isoformat()},
        headers=headers,
    )


def test_ac2_an_approved_booking_makes_its_occupied_period_busy(client, db_session):
    s = _setup(client, db_session)
    _buffers(db_session, s, 30, 45)
    other = _other(db_session, s, _at(10, day=3), _at(12, day=3))
    res = _availability(client, s["staff_h"], s["venue"].id, _at(0, day=3), _at(23, day=3))
    assert res.status_code == 200
    body = res.json()
    assert body["venue_id"] == s["venue"].id
    [busy] = body["busy"]
    assert busy["kind"] == "booking"
    assert busy["start"].startswith("2026-11-03T09:30") and busy["end"].startswith("2026-11-03T12:45")
    assert busy["event_start"].startswith("2026-11-03T10:00") and busy["event_end"].startswith("2026-11-03T12:00")
    assert busy["event_name"] == "Alumni Gala"
    # the buffer alone (12:30) is busy even though the event has ended
    edge = _availability(client, s["staff_h"], s["venue"].id, _at(12, 30, day=3), _at(13, day=3))
    assert len(edge.json()["busy"]) == 1
    assert other.id  # silence unused


def test_ac2_closures_are_busy_and_a_range_outside_is_free(client, db_session):
    s = _setup(client, db_session)
    db_session.add(
        VenueUnavailability(
            venue_id=s["venue"].id, start_time=_at(8, day=4), end_time=_at(9, day=4),
            reason="Maintenance", created_by=s["staff"].id,
        )
    )
    db_session.commit()
    res = _availability(client, s["staff_h"], s["venue"].id, _at(0, day=4), _at(23, day=4)).json()
    [closure] = res["busy"]
    assert closure["kind"] == "closure" and closure["event_name"] is None
    assert _availability(client, s["staff_h"], s["venue"].id, _at(10, day=4), _at(11, day=4)).json()["busy"] == []


def test_ac2_venue_search_agrees_with_the_calendar(client, db_session):
    s = _setup(client, db_session)
    _buffers(db_session, s, 30, 45)
    _other(db_session, s, _at(10, day=3), _at(12, day=3))
    window = (_at(12, 15, day=3), _at(12, 25, day=3))  # inside the turnaround
    assert _availability(client, s["staff_h"], s["venue"].id, *window).json()["busy"]
    found = client.get(
        "/venues", params={"start": window[0].isoformat(), "end": window[1].isoformat()}, headers=s["staff_h"]
    ).json()
    assert s["venue"].id not in [v["id"] for v in found]


# --- AC3: touching occupied periods do not conflict ---------------------------


def test_ac3_a_request_starting_exactly_when_an_approved_one_ends_is_not_a_conflict(client, db_session):
    s = _setup(client, db_session)
    _other(db_session, s, _at(5), _at(9))  # ends exactly as the request starts
    assert _conflicts(client, s) == []
    assert _approve(client, s["staff_h"], s["booking_id"]).status_code == 200


def test_ac3_touching_occupied_periods_with_buffers_are_not_a_conflict(client, db_session):
    s = _setup(client, db_session)
    _buffers(db_session, s, 30, 45)
    # request occupies 08:30-17:45; this one's occupied period ends 08:30 sharp
    _other(db_session, s, _at(5, 45), _at(7, 45))
    assert _conflicts(client, s) == []
    # and one minute later it does overlap
    _other(db_session, s, _at(5, 46), _at(7, 46), name="Late One")
    [c] = _conflicts(client, s)
    assert c["event_name"] == "Late One"
    assert c["overlap_start"].startswith("2026-11-02T08:30") and c["overlap_end"].startswith("2026-11-02T08:31")


def test_ac3_availability_treats_touching_as_free(client, db_session):
    s = _setup(client, db_session)
    _other(db_session, s, _at(10, day=3), _at(12, day=3))
    assert _availability(client, s["staff_h"], s["venue"].id, _at(12, day=3), _at(13, day=3)).json()["busy"] == []


# --- AC4: only approved bookings count ----------------------------------------


@pytest.mark.parametrize("status", [BookingStatus.pending, BookingStatus.rejected, BookingStatus.cancelled])
def test_ac4_non_approved_bookings_are_never_conflicts(client, db_session, status):
    s = _setup(client, db_session)
    other = _other(db_session, s, _at(10), _at(12), status=status)
    assert _conflicts(client, s) == []
    free = _availability(client, s["staff_h"], s["venue"].id, _at(0), _at(23))
    assert free.json()["busy"] == []
    assert other.status == status


def test_ac4_a_decided_request_is_not_flagged_and_does_not_conflict_with_itself(client, db_session):
    s = _setup(client, db_session)
    assert _approve(client, s["staff_h"], s["booking_id"]).status_code == 200
    assert _conflicts(client, s) == []  # approved: nothing to review, not its own conflict


def test_ac4_rejecting_the_clashing_booking_clears_the_flag(client, db_session):
    s = _setup(client, db_session)
    other = _other(db_session, s, _at(10), _at(12), status=BookingStatus.pending)
    assert client.post(
        f"/venue-bookings/{other.id}/reject", json={"reason": "No"}, headers=s["staff_h"]
    ).status_code == 200
    assert _conflicts(client, s) == []


# --- AC5: what it conflicts with, and the overlapping time --------------------


def test_ac5_conflict_shape_and_overlap_are_exact(client, db_session):
    s = _setup(client, db_session)
    _buffers(db_session, s, 15, 30)  # request occupies 08:45-17:30
    other = _other(db_session, s, _at(16), _at(20))  # occupies 15:45-20:30
    [c] = _conflicts(client, s)
    assert set(c) == {
        "booking_id", "event_id", "event_name", "event_start", "event_end",
        "occupied_start", "occupied_end", "overlap_start", "overlap_end",
        "kind", "reason",
    }
    assert c["kind"] == "booking" and c["reason"] is None
    assert c["booking_id"] == other.id
    assert (c["occupied_start"][:16], c["occupied_end"][:16]) == ("2026-11-02T15:45", "2026-11-02T20:30")
    assert (c["overlap_start"][:16], c["overlap_end"][:16]) == ("2026-11-02T15:45", "2026-11-02T17:30")


def test_ac5_several_conflicts_are_all_listed_in_start_order(client, db_session):
    s = _setup(client, db_session)
    late = _other(db_session, s, _at(14), _at(16), name="Late")
    early = _other(db_session, s, _at(8), _at(10), name="Early")
    assert [c["booking_id"] for c in _conflicts(client, s)] == [early.id, late.id]


# --- Visibility: nobody but Venue Staff learns other events' names ------------


def test_conflicts_never_reach_the_coordinator_or_leak_event_names(client, db_session):
    s = _setup(client, db_session)
    _other(db_session, s, _at(10), _at(12), name="Secret Gala")
    mine = client.get(f"/venue-bookings/events/{s['event_id']}", headers=s["coord_h"])
    assert mine.status_code == 200
    assert all(b["conflicts"] == [] for b in mine.json())
    assert "Secret Gala" not in mine.text
    coord_view = _availability(client, s["coord_h"], s["venue"].id, _at(0), _at(23))
    assert coord_view.status_code == 200 and len(coord_view.json()["busy"]) == 1
    assert coord_view.json()["busy"][0]["event_name"] is None
    assert "Secret Gala" not in coord_view.text


def test_conflicts_are_only_for_the_staff_queue_and_get_not_other_roles(client, db_session):
    s = _setup(client, db_session)
    _other(db_session, s, _at(10), _at(12))
    assert client.get(f"/venue-bookings/{s['booking_id']}", headers=s["coord_h"]).status_code == 403
    assert client.get("/venue-bookings/queue", headers=s["coord_h"]).status_code == 403


# --- Availability endpoint: access and validation -----------------------------


def test_availability_access_denied_and_unknown_venue(client, db_session):
    s = _setup(client, db_session)
    url = f"/venues/{s['venue'].id}/availability"
    params = {"start": _at(0).isoformat(), "end": _at(5).isoformat()}
    assert client.get(url, params=params).status_code == 401
    org = s["org_h"]
    assert client.get(url, params=params, headers=org).status_code == 403
    attendee = _headers(client, db_session, Role.ATTENDEE, "att@example.com")
    assert client.get(url, params=params, headers=attendee).status_code == 403
    assert _availability(client, s["staff_h"], 99999, _at(0), _at(5)).status_code == 404


@pytest.mark.parametrize(
    "params",
    [
        {"start": "2026-11-02T10:00:00Z"},
        {"end": "2026-11-02T10:00:00Z"},
        {"start": "2026-11-02T10:00:00Z", "end": "2026-11-02T10:00:00Z"},
        {"start": "2026-11-02T11:00:00Z", "end": "2026-11-02T10:00:00Z"},
        {},
    ],
)
def test_availability_rejects_half_or_inverted_ranges(client, db_session, params):
    s = _setup(client, db_session)
    res = client.get(f"/venues/{s['venue'].id}/availability", params=params, headers=s["staff_h"])
    assert res.status_code == 422


# --- Frozen literals: behaviour this story must not change --------------------


def test_frozen_a_booking_with_no_clash_has_empty_conflicts_and_existing_fields(client, db_session):
    s = _setup(client, db_session)
    body = _review(client, s).json()
    assert body["conflicts"] == []
    assert body["status"] == "pending"
    assert (body["setup_minutes"], body["turnaround_minutes"]) == (0, 0)
    assert body["occupied_start"].startswith("2026-11-02T09:00")
    assert body["occupied_end"].startswith("2026-11-02T17:00")


def test_frozen_venue_search_still_excludes_only_approved_overlaps(client, db_session):
    s = _setup(client, db_session)
    _other(db_session, s, _at(10, day=5), _at(12, day=5), status=BookingStatus.pending)
    params = {"start": _at(10, day=5).isoformat(), "end": _at(12, day=5).isoformat()}
    ids = [v["id"] for v in client.get("/venues", params=params, headers=s["staff_h"]).json()]
    assert s["venue"].id in ids
