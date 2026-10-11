"""Venue setup & turnaround (SCRUM-78) on real PostgreSQL: the new columns and
check constraints in db/schema.sql, search and approval with buffers, and two
approvals racing for a venue whose buffers make them clash."""

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.roles import Role
from app.models.enums import BookingStatus, EventStatus
from app.models.events import Event
from app.models.venues import Venue, VenueBooking
from tests.integration.conftest import submit_event
from tests.integration.test_coordinator_concurrency_postgres import THREADS, race
from tests.integration.test_venue_booking_decision_postgres import _approve, _submit

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("coordinator_auto_assign")]


def _at(hour, minute=0):
    return datetime(2026, 11, 2, hour, minute, tzinfo=timezone.utc)


def _world(client, make_user, db, setup, turnaround, starts):
    """One venue; an event per start hour (2h long), each with a pending request."""
    _o, org_h = make_user(Role.ORGANISER, "org@connectsphere.test", "Priya")
    _s, sam_h = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam")
    _v, staff_h = make_user(Role.VENUE_STAFF, "staff@connectsphere.test", "Vera")
    venue = Venue(name="Marina Hall", location="10 Bayfront", capacity=250)
    db.add(venue)
    db.commit()
    ids = []
    for hour in starts:
        event_id = submit_event(client, org_h)
        event = db.get(Event, event_id)
        event.status = EventStatus.event_approved
        event.proposed_start, event.proposed_end = _at(hour), _at(hour + 2)
        db.commit()
        ids.append(_submit(client, sam_h, event_id, venue.id).json()["id"])
    put = client.put(
        f"/venues/{venue.id}/setup-turnaround",
        json={"setup_minutes": setup, "turnaround_minutes": turnaround},
        headers=staff_h,
    )
    assert put.status_code == 200, put.text
    return sam_h, staff_h, venue.id, ids


def test_ac1_ac5_ac6_buffers_persist_gate_approval_and_show_in_responses(client, make_user, db):
    sam_h, staff_h, venue_id, [first, second] = _world(client, make_user, db, 30, 45, [10, 13])

    db.expire_all()
    venue = db.get(Venue, venue_id)
    assert (venue.setup_minutes, venue.turnaround_minutes) == (30, 45)
    assert venue.setup_turnaround_updated_at is not None

    assert _approve(client, staff_h, first).status_code == 200
    clash = _approve(client, staff_h, second)  # 12:30 setup start < 12:45
    assert clash.status_code == 409
    db.expire_all()
    assert db.get(VenueBooking, second).status == BookingStatus.pending

    [seen] = [b for b in client.get("/venue-bookings/queue", headers=staff_h).json()]
    assert (seen["setup_minutes"], seen["turnaround_minutes"]) == (30, 45)
    assert seen["occupied_start"].startswith("2026-11-02T12:30")
    assert seen["occupied_end"].startswith("2026-11-02T15:45")

    coord = {"start": "2026-11-02T13:00:00Z", "end": "2026-11-02T14:00:00Z"}
    assert [v["name"] for v in client.get("/venues", params=coord, headers=staff_h).json()] == []
    later = {"start": "2026-11-02T13:30:00Z", "end": "2026-11-02T14:00:00Z"}
    assert [v["name"] for v in client.get("/venues", params=later, headers=staff_h).json()] == ["Marina Hall"]


def test_ac2_database_refuses_negative_minutes(db):
    venue = Venue(name="Bad Hall", location="x", capacity=10, setup_minutes=-1)
    db.add(venue)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_ac5_two_clashing_approvals_at_once_confirm_only_one(client, make_user, db, make_client):
    _, staff_h, _venue_id, ids = _world(client, make_user, db, 30, 45, [10, 13])
    todo = iter(ids * (THREADS // 2))
    results = race(make_client, THREADS, lambda c: _approve(c, staff_h, next(todo)))
    codes = sorted(r.status_code for r in results)
    assert codes.count(200) == 1, codes
    db.expire_all()
    approved = [b for b in db.query(VenueBooking).all() if b.status == BookingStatus.approved]
    assert len(approved) == 1
