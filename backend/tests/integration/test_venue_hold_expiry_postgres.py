"""Tentative hold reminder and expiry, on real PostgreSQL.

The SQLite unit tests (tests/test_venue_hold_expiry.py) prove the rules;
these prove the new 'hold_expired' value of the booking_status enum and the
hold_reminder_sent_at column in db/schema.sql, and that sweeps running at
the same moment (the background sweeper and a request, or two app
processes) remind and expire each hold exactly once -- FOR UPDATE SKIP
LOCKED, which SQLite does not have.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from app.models.enums import BookingStatus
from app.models.notifications import Notification
from app.models.venues import VenueBooking
from app.services.hold_sweeper import HoldSweeper
from tests.integration.test_coordinator_concurrency_postgres import THREADS
from tests.integration.test_venue_booking_decision_postgres import _setup

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("coordinator_auto_assign")]


def _hold(client, staff_h, booking_id, hours=48):
    expiry = (datetime.now(timezone.utc) + timedelta(hours=hours)).replace(microsecond=0)
    res = client.post(
        f"/venue-bookings/{booking_id}/hold",
        json={"expires_at": expiry.isoformat(), "required_action": "Pay the deposit."},
        headers=staff_h,
    )
    assert res.status_code == 200, res.text
    return expiry


def _sweep_at_once(session_factory, at, n=THREADS):
    sweeper = HoldSweeper(session_factory, 60)
    barrier = threading.Barrier(n)

    def one(_):
        barrier.wait()
        return sweeper.run_once(now=at)

    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(one, range(n)))


def test_ac1_ac2_reminder_and_expiry_persist_on_postgres(client, make_user, db, session_factory):
    _sam_h, _vera, staff_h, _events, [booking_id], _venue = _setup(client, make_user, db)
    expiry = _hold(client, staff_h, booking_id)
    sweeper = HoldSweeper(session_factory, 60)

    assert sweeper.run_once(now=expiry - timedelta(hours=23)) == (1, 0)
    db.expire_all()
    assert db.get(VenueBooking, booking_id).hold_reminder_sent_at is not None

    assert sweeper.run_once(now=expiry + timedelta(minutes=1)) == (0, 1)
    db.expire_all()
    row = db.get(VenueBooking, booking_id)
    assert row.status == BookingStatus.hold_expired  # the new enum value round-trips
    assert db.query(VenueBooking).filter(VenueBooking.status == "hold_expired").count() == 1


def test_sweeps_at_the_same_moment_remind_and_expire_each_hold_once(client, make_user, db, session_factory):
    _sam_h, _vera, staff_h, _events, booking_ids, _venue = _setup(client, make_user, db, events=3)
    expiries = [_hold(client, staff_h, b) for b in booking_ids]
    first = min(expiries)

    reminded = _sweep_at_once(session_factory, first - timedelta(hours=1))
    assert sum(r for r, _ in reminded) == 3

    expired = _sweep_at_once(session_factory, max(expiries) + timedelta(minutes=1))
    assert sum(e for _, e in expired) == 3

    db.expire_all()
    assert {db.get(VenueBooking, b).status for b in booking_ids} == {BookingStatus.hold_expired}
    reminders = db.query(Notification).filter(Notification.message.like("Reminder:%")).count()
    expiry_notices = db.query(Notification).filter_by(type="venue_hold_expired").count()
    assert reminders == 3
    assert expiry_notices == 6  # each hold: its Coordinator and the Venue Staff who placed it
