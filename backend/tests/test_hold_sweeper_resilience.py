"""Unit tests for the tentative-hold sweeper when something goes wrong.

SCRUM-98  Auto-Expire Tentative Holds & Notify Coordinator

    As an Event Coordinator, I want to be warned before my tentative hold
    expires and told when it expires, so that I can act in time or plan another
    Venue.

    AC1  an active hold whose action is not complete gets a reminder before
         expiry
    AC2  when the expiry passes, the hold expires automatically

The main paths are tests/test_venue_hold_expiry.py; these are the failure
paths it leaves unexecuted.
"""

import asyncio
from datetime import timedelta

import pytest

from app.models.enums import BookingStatus
from app.models.events import Event
from app.models.notifications import Notification
from app.services.hold_sweeper import HoldSweeper
from tests.test_venue_booking_decision import _setup as _booking_setup
from tests.test_venue_hold_expiry import _hold, _reminders, _status, _sweep


def test_scrum98_ac2_one_failed_pass_does_not_stop_the_sweeper():
    passes = []

    class Flaky(HoldSweeper):
        def run_once(self, now=None):
            passes.append(now)
            if len(passes) == 1:
                raise RuntimeError("database went away")
            return 0, 0

    async def scenario():
        sweeper = asyncio.ensure_future(Flaky(lambda: None, 0).run_forever())
        while len(passes) < 2:
            await asyncio.sleep(0)
        sweeper.cancel()
        with pytest.raises(asyncio.CancelledError):
            await sweeper

    asyncio.run(asyncio.wait_for(scenario(), timeout=5))
    assert len(passes) >= 2


@pytest.mark.usefixtures("coordinator_auto_assign")
def test_scrum98_ac1_a_hold_whose_event_has_no_coordinator_reminds_nobody(client, db_session):
    s = _booking_setup(client, db_session)
    expiry = _hold(client, s, hours=48)
    db_session.get(Event, s["event_id"]).coordinator_id = None
    db_session.commit()
    before = db_session.query(Notification).count()

    _sweep(db_session, expiry - timedelta(hours=24))

    assert db_session.query(Notification).count() == before
    assert _status(db_session, s) == BookingStatus.tentative_hold
    assert _reminders(db_session, s) == []
