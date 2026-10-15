"""Tentative venue hold with an expiry and a required action, on real PostgreSQL.

The SQLite unit tests (tests/test_venue_tentative_hold.py) prove the rules;
these prove the new `hold_action` column in db/schema.sql and the timestamptz
expiry round-trip on the production engine, that an active hold occupies the
venue in Postgres queries, and that a hold placed twice at once is placed
exactly once.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.enums import BookingStatus
from app.models.venues import VenueBooking
from tests.integration.test_coordinator_concurrency_postgres import THREADS, race
from tests.integration.test_venue_booking_decision_postgres import _approve, _setup

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("coordinator_auto_assign")]

ACTION = "Confirm final headcount and pay the deposit."


def _hold(client, headers, booking_id, expires_at, action=ACTION):
    return client.post(
        f"/venue-bookings/{booking_id}/hold",
        json={"expires_at": expires_at.isoformat(), "required_action": action},
        headers=headers,
    )


def test_ac1_ac3_ac5_hold_round_trips_occupies_and_approves_on_postgres(client, make_user, db):
    sam_h, _vera, staff_h, [event_id, _], [held_id, rival_id], _venue = _setup(client, make_user, db, events=2)
    expiry = (datetime.now(timezone.utc) + timedelta(days=2)).replace(microsecond=0)

    res = _hold(client, staff_h, held_id, expiry)
    assert res.status_code == 200, res.text

    db.expire_all()
    row = db.get(VenueBooking, held_id)
    assert (row.status, row.expires_at, row.hold_action) == (BookingStatus.tentative_hold, expiry, ACTION)

    # AC3: the hold occupies the venue for another event's request.
    rival = client.get(f"/venue-bookings/{rival_id}", headers=staff_h).json()
    assert [(c["booking_id"], c["status"]) for c in rival["conflicts"]] == [(held_id, "tentative_hold")]

    # AC4: the Event's Coordinator reads the expiry and the action.
    [mine] = client.get(f"/venue-bookings/events/{event_id}", headers=sam_h).json()
    assert mine["hold_action"] == ACTION

    # AC5: approval turns it into an approved booking, the hold fields cleared.
    assert _approve(client, staff_h, held_id).status_code == 200
    db.expire_all()
    row = db.get(VenueBooking, held_id)
    assert (row.status, row.expires_at, row.hold_action) == (BookingStatus.approved, None, None)


def test_ac2_a_past_expiry_leaves_the_row_untouched_on_postgres(client, make_user, db):
    _sam_h, _vera, staff_h, _events, [booking_id], _venue = _setup(client, make_user, db)

    res = _hold(client, staff_h, booking_id, datetime.now(timezone.utc) - timedelta(minutes=5))

    assert res.status_code == 422
    db.expire_all()
    row = db.get(VenueBooking, booking_id)
    assert (row.status, row.expires_at, row.hold_action) == (BookingStatus.pending, None, None)


def test_a_hold_placed_many_times_at_once_is_placed_exactly_once(client, make_user, db, make_client):
    _sam_h, _vera, staff_h, _events, [booking_id], _venue = _setup(client, make_user, db)
    expiry = datetime.now(timezone.utc) + timedelta(days=1)

    results = race(make_client, THREADS, lambda c: _hold(c, staff_h, booking_id, expiry))

    assert sorted(r.status_code for r in results) == [200] + [409] * (THREADS - 1)
    db.expire_all()
    assert db.get(VenueBooking, booking_id).status == BookingStatus.tentative_hold
