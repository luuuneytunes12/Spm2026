"""Tests for "Warn before a tentative hold expires, and tell when it does".

    As an Event Coordinator, I want to be warned before my tentative hold
    expires and told when it expires, so that I can act in time or plan
    another Venue.

    AC1  an active hold whose required action is not complete gets one
         reminder, 24 hours (configurable) before expiry
    AC2  when the expiry passes the hold becomes 'Expired' automatically and
         the venue is free for that window
    AC3  on expiry the Coordinator and the Venue Staff are notified
    AC4  an expired hold is never shown as a confirmed booking and stays in
         the Event's history

The sweeper is driven through `HoldSweeper.run_once(now=...)`, so "24 hours
before" and "after expiry" are exact instants rather than real waiting.
"""

import threading
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.domain.event_readiness import outstanding_arrangements
from app.main import app
from app.models.enums import BookingStatus, EventStatus, NotificationType
from app.models.events import Event, EventStatusHistory
from app.models.notifications import Notification
from app.models.venues import VenueBooking
from app.services.hold_sweeper import HoldSweeper
from tests.test_venue_booking_decision import _setup
from tests.test_venue_search import _someone

pytestmark = pytest.mark.usefixtures("coordinator_auto_assign")

ACTION = "Confirm final headcount and pay the deposit."
EXPIRING = NotificationType.venue_hold_expiring
EXPIRED = NotificationType.venue_hold_expired


def _hold(client, s, hours=48, action=ACTION):
    """Venue Staff hold the request until `hours` from now; returns the expiry."""
    expiry = (datetime.now(timezone.utc) + timedelta(hours=hours)).replace(microsecond=0)
    res = client.post(
        f"/venue-bookings/{s['booking_id']}/hold",
        json={"expires_at": expiry.isoformat(), "required_action": action},
        headers=s["staff_h"],
    )
    assert res.status_code == 200, res.text
    return expiry


def _sweep(db_session, at):
    # The test's session, not closed after the pass (the client shares it).
    return HoldSweeper(lambda: nullcontext(db_session), 60).run_once(now=at)


def _coordinator(db_session, s):
    return db_session.get(Event, s["event_id"]).coordinator_id


def _notes(db_session, user_id, type):
    db_session.expire_all()
    return [
        n.message
        for n in db_session.query(Notification).filter_by(user_id=user_id, type=type).order_by(Notification.id)
    ]


def _reminders(db_session, s):
    return [m for m in _notes(db_session, _coordinator(db_session, s), EXPIRING) if m.startswith("Reminder")]


def _status(db_session, s):
    db_session.expire_all()
    return db_session.get(VenueBooking, s["booking_id"]).status


# --- AC1: one reminder, 24 hours (configurable) before expiry -----------------


def test_ac1_the_coordinator_is_reminded_once_24_hours_before_expiry(client, db_session):
    s = _setup(client, db_session)
    expiry = _hold(client, s, hours=48)

    assert _sweep(db_session, expiry - timedelta(hours=24, minutes=1)) == (0, 0)  # not yet
    assert _sweep(db_session, expiry - timedelta(hours=24)) == (1, 0)
    assert _sweep(db_session, expiry - timedelta(hours=2)) == (0, 0)  # once only

    [reminder] = _reminders(db_session, s)
    for part in ("Marina Hall", "expires at", f"{expiry:%d %b %Y %H:%M} UTC", f"Required action: {ACTION}"):
        assert part in reminder
    assert _status(db_session, s) == BookingStatus.tentative_hold  # still held


def test_ac1_the_lead_time_is_configurable(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "hold_reminder_hours", 2)
    s = _setup(client, db_session)
    expiry = _hold(client, s, hours=48)

    assert _sweep(db_session, expiry - timedelta(hours=24)) == (0, 0)
    assert _sweep(db_session, expiry - timedelta(hours=2)) == (1, 0)


@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_ac1_a_hold_whose_action_is_done_is_never_reminded(client, db_session, decision):
    s = _setup(client, db_session)
    expiry = _hold(client, s, hours=48)
    body = {"json": {"reason": "Fell through."}} if decision == "reject" else {}
    assert client.post(f"/venue-bookings/{s['booking_id']}/{decision}", headers=s["staff_h"], **body).status_code == 200

    assert _sweep(db_session, expiry - timedelta(hours=1)) == (0, 0)
    assert _reminders(db_session, s) == []


def test_ac1_a_hold_placed_inside_the_lead_is_not_reminded_again(client, db_session):
    s = _setup(client, db_session)
    expiry = _hold(client, s, hours=6)  # the placement notice already gives expiry and action
    assert _sweep(db_session, expiry - timedelta(hours=1)) == (0, 0)
    assert _reminders(db_session, s) == []


def test_ac1_negative_only_the_events_coordinator_is_reminded(client, db_session):
    s = _setup(client, db_session)
    expiry = _hold(client, s, hours=48)
    _sweep(db_session, expiry - timedelta(hours=12))
    assert _notes(db_session, s["staff"].id, EXPIRING) == []
    assert db_session.query(Notification).filter_by(type=EXPIRING).count() == 2  # placement + reminder


# --- AC2: expired automatically, the venue free again --------------------------


def _rival(db_session, s):
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


def test_ac2_after_expiry_the_hold_is_expired_and_the_venue_free(client, db_session):
    s = _setup(client, db_session)
    expiry = _hold(client, s)
    rival = _rival(db_session, s)
    held_by = lambda: [c["booking_id"] for c in client.get(f"/venue-bookings/{rival.id}", headers=s["staff_h"]).json()["conflicts"]]  # noqa: E731
    assert held_by() == [s["booking_id"]]  # occupied while the hold is active

    assert _sweep(db_session, expiry + timedelta(seconds=1)) == (0, 1)

    assert _status(db_session, s) == BookingStatus.hold_expired
    booking = db_session.get(VenueBooking, s["booking_id"])
    window = {"start": (booking.start_time - timedelta(hours=1)).isoformat(), "end": (booking.end_time + timedelta(hours=1)).isoformat()}
    busy = client.get(f"/venues/{s['venue'].id}/availability", params=window, headers=s["staff_h"]).json()["busy"]
    assert busy == []
    assert held_by() == []


def test_ac2_frozen_literal_before_expiry_nothing_changes(client, db_session):
    s = _setup(client, db_session)
    expiry = _hold(client, s)
    assert _sweep(db_session, expiry - timedelta(seconds=1))[1] == 0
    assert _status(db_session, s) == BookingStatus.tentative_hold


def test_ac2_the_sweeper_runs_by_itself_while_the_app_is_up(monkeypatch):
    """The lifespan starts the sweeper; nobody has to call an endpoint."""
    swept = threading.Event()
    monkeypatch.setattr(settings, "hold_sweep_interval_seconds", 1)
    monkeypatch.setattr(HoldSweeper, "run_once", lambda self, now=None: swept.set() or (0, 0))
    from fastapi.testclient import TestClient

    with TestClient(app):
        assert swept.wait(timeout=5)


def test_ac2_an_expired_hold_is_never_swept_twice(client, db_session):
    s = _setup(client, db_session)
    expiry = _hold(client, s)
    assert _sweep(db_session, expiry + timedelta(seconds=1)) == (0, 1)
    assert _sweep(db_session, expiry + timedelta(hours=1)) == (0, 0)
    assert len(_notes(db_session, _coordinator(db_session, s), EXPIRED)) == 1


# --- AC3: the Coordinator and the Venue Staff are told -------------------------


def test_ac3_on_expiry_the_coordinator_and_the_venue_staff_are_notified(client, db_session):
    s = _setup(client, db_session)
    expiry = _hold(client, s)
    _sweep(db_session, expiry + timedelta(minutes=1))

    [to_coordinator] = _notes(db_session, _coordinator(db_session, s), EXPIRED)
    [to_staff] = _notes(db_session, s["staff"].id, EXPIRED)
    assert "Marina Hall" in to_coordinator and "expired" in to_coordinator
    assert "Marina Hall" in to_staff and "free again" in to_staff


def test_ac3_negative_no_one_else_is_told(client, db_session):
    s = _setup(client, db_session)
    expiry = _hold(client, s)
    _sweep(db_session, expiry + timedelta(minutes=1))
    told = {n.user_id for n in db_session.query(Notification).filter_by(type=EXPIRED)}
    assert told == {_coordinator(db_session, s), s["staff"].id}


# --- AC4: never a confirmed booking, still in the history ----------------------


def test_ac4_the_event_shows_the_hold_as_expired_not_confirmed(client, db_session):
    s = _setup(client, db_session)
    expiry = _hold(client, s)
    _sweep(db_session, expiry + timedelta(minutes=1))

    [booking] = client.get(f"/venue-bookings/events/{s['event_id']}", headers=s["coord_h"]).json()
    assert booking["status"] == "hold_expired"
    assert booking["decision_notes"] == "Tentative hold expired."


def test_ac4_an_expired_hold_does_not_count_as_a_venue_for_safety_check(client, db_session):
    s = _setup(client, db_session)
    expiry = _hold(client, s)
    _sweep(db_session, expiry + timedelta(minutes=1))
    event = db_session.get(Event, s["event_id"])
    assert outstanding_arrangements(db_session, event)[0].startswith("The event has no venue")


def test_ac4_the_expiry_stays_in_the_events_history(client, db_session):
    s = _setup(client, db_session)
    expiry = _hold(client, s)
    _sweep(db_session, expiry + timedelta(minutes=1))
    db_session.expire_all()
    notes = [h.note for h in db_session.query(EventStatusHistory).filter_by(event_id=s["event_id"])]
    assert any(n and n.startswith("Tentative hold placed") for n in notes)
    assert any(n == "Tentative hold on 'Marina Hall' expired." for n in notes)
    # ...and the Coordinator reads it in the Event's activity log.
    activity = client.get(f"/events/assigned/{s['event_id']}", headers=s["coord_h"]).json()["activity"]
    assert any("Tentative hold on 'Marina Hall' expired." in (a.get("note") or "") for a in activity)
    # The booking row itself is kept, with its outcome, not deleted.
    assert db_session.get(VenueBooking, s["booking_id"]).decision_notes == "Tentative hold expired."


def test_ac4_frozen_literal_the_venue_can_be_requested_again(client, db_session):
    s = _setup(client, db_session)
    expiry = _hold(client, s)
    _sweep(db_session, expiry + timedelta(minutes=1))
    res = client.post(
        f"/venue-bookings/events/{s['event_id']}", json={"venues": [{"venue_id": s["venue"].id}]}, headers=s["coord_h"]
    )
    assert res.status_code == 201, res.text
