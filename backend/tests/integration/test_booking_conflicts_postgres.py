"""Booking conflicts (SCRUM-41) on real PostgreSQL: the flag shown to Venue
Staff, the availability calendar, and two overlapping requests approved at
the same moment -- exactly one wins and the loser is told who holds the venue."""

import pytest

from app.models.enums import BookingStatus
from app.models.venues import VenueBooking
from tests.integration.test_coordinator_concurrency_postgres import THREADS, race
from tests.integration.test_venue_booking_decision_postgres import _approve
from tests.integration.test_venue_setup_turnaround_postgres import _world

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("coordinator_auto_assign")]


def test_ac1_ac2_ac5_overlap_is_flagged_and_calendar_shows_it_busy(client, make_user, db):
    sam_h, staff_h, venue_id, [first, second] = _world(client, make_user, db, 30, 45, [10, 13])
    flagged = client.get(f"/venue-bookings/{second}", headers=staff_h).json()
    assert flagged["conflicts"] == []  # first is still pending: not a conflict
    assert _approve(client, staff_h, first).status_code == 200
    [c] = client.get(f"/venue-bookings/{second}", headers=staff_h).json()["conflicts"]
    assert c["booking_id"] == first
    assert c["overlap_start"].startswith("2026-11-02T12:30")
    assert c["overlap_end"].startswith("2026-11-02T12:45")

    # the Coordinator never sees it
    mine = client.get(f"/venue-bookings/events/{flagged['event']['id']}", headers=sam_h).json()
    assert all(b["conflicts"] == [] for b in mine)

    cal = client.get(
        f"/venues/{venue_id}/availability",
        params={"start": "2026-11-02T00:00:00Z", "end": "2026-11-03T00:00:00Z"},
        headers=sam_h,
    ).json()
    [busy] = cal["busy"]
    assert busy["start"].startswith("2026-11-02T09:30") and busy["end"].startswith("2026-11-02T12:45")
    assert busy["event_name"] is None


def test_ac3_exact_touch_is_not_a_conflict(client, make_user, db):
    # 10-12 occupies 09:30-12:45; 14:45 setup start == 12:45 end exactly.
    _, staff_h, _venue_id, [first, second] = _world(client, make_user, db, 30, 45, [10, 15])
    assert _approve(client, staff_h, first).status_code == 200
    assert client.get(f"/venue-bookings/{second}", headers=staff_h).json()["conflicts"] == []
    assert _approve(client, staff_h, second).status_code == 200


def test_two_overlapping_requests_approved_at_once_exactly_one_wins(client, make_user, db, make_client):
    _, staff_h, _venue_id, ids = _world(client, make_user, db, 0, 0, [10, 11])
    todo = iter(ids * (THREADS // 2))
    results = race(make_client, THREADS, lambda c: _approve(c, staff_h, next(todo)))
    codes = sorted(r.status_code for r in results)
    assert codes.count(200) == 1 and codes.count(409) == THREADS - 1, codes
    loser_msgs = [r.json()["detail"] for r in results if r.status_code == 409]
    assert any("already booked" in m for m in loser_msgs)
    db.expire_all()
    approved = [b for b in db.query(VenueBooking).all() if b.status == BookingStatus.approved]
    assert len(approved) == 1
