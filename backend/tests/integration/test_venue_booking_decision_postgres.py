"""Approve or Reject Venue Booking Request, on real PostgreSQL.

The SQLite unit tests (tests/test_venue_booking_decision.py) prove the rules;
these prove they hold on the production engine -- the new column in
db/schema.sql, its enum and timestamp handling -- and when decisions arrive
at the same moment: a request is decided once, and a venue is never
confirmed for two overlapping events.
"""

from app.core.roles import Role
from app.models.enums import BookingStatus, EventStatus
from app.models.events import Event
from app.models.venues import Venue, VenueBooking
from tests.integration.conftest import submit_event
from tests.integration.test_coordinator_concurrency_postgres import THREADS, race
import pytest

# These tests start from an event that already has a Coordinator; assignment is
# now the Lead's job, so submit alone no longer provides one (see tests/conftest.py).
pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("coordinator_auto_assign")]


def _setup(client, make_user, db, events=1):
    """`events` approved events, each with a pending request for the same
    venue and time. Returns (coordinator headers, staff user, staff headers,
    event ids, booking ids, venue id)."""
    _o, org_h = make_user(Role.ORGANISER, "org@connectsphere.test", "Priya Menon")
    _sam, sam_h = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")
    vera, staff_h = make_user(Role.VENUE_STAFF, "staff@connectsphere.test", "Vera Staff")
    venue = Venue(name="Marina Hall", location="10 Bayfront Ave", capacity=250)
    db.add(venue)
    db.commit()
    event_ids, booking_ids = [], []
    for _ in range(events):
        event_id = submit_event(client, org_h)
        db.get(Event, event_id).status = EventStatus.event_approved
        db.commit()
        event_ids.append(event_id)
        booking_ids.append(_submit(client, sam_h, event_id, venue.id).json()["id"])
    return sam_h, vera, staff_h, event_ids, booking_ids, venue.id


def _submit(client, headers, event_id, venue_id):
    res = client.post(f"/venue-bookings/events/{event_id}", json={"venue_id": venue_id}, headers=headers)
    assert res.status_code == 201, res.text
    return res


def _approve(client, headers, booking_id):
    return client.post(f"/venue-bookings/{booking_id}/approve", headers=headers)


def _reject(client, headers, booking_id, **body):
    return client.post(f"/venue-bookings/{booking_id}/reject", json=body, headers=headers)


def test_ac1_to_ac5_reject_resubmit_and_approve_persist_and_reach_the_coordinator(client, make_user, db):
    sam_h, vera, staff_h, [event_id], [first], venue_id = _setup(client, make_user, db)
    queue = lambda: [b["id"] for b in client.get("/venue-bookings/queue", headers=staff_h).json()]  # noqa: E731
    assert queue() == [first]  # AC1

    rejected = _reject(client, staff_h, first, reason="Closed for repairs.", suggested_alternative="Try Hall B.")
    assert rejected.status_code == 200  # AC2
    assert queue() == []

    [seen] = client.get(f"/venue-bookings/events/{event_id}", headers=sam_h).json()
    assert seen["status"] == "rejected"  # AC4
    assert seen["decision_notes"] == "Closed for repairs."  # AC3
    assert seen["suggested_alternative"] == "Try Hall B."
    assert seen["reviewed_by"]["name"] == "Vera Staff"
    assert seen["reviewed_at"] is not None

    second = _submit(client, sam_h, event_id, venue_id).json()["id"]  # AC5
    assert queue() == [second]
    assert _approve(client, staff_h, second).status_code == 200  # AC2

    listed = client.get(f"/venue-bookings/events/{event_id}", headers=sam_h).json()
    assert [(b["id"], b["status"]) for b in listed] == [(second, "approved"), (first, "rejected")]
    row = db.get(VenueBooking, second)
    assert row.reviewed_by == vera.id
    assert row.reviewed_at.tzinfo is not None  # timestamptz, not a naive time


def test_an_approve_fired_many_times_at_once_decides_the_request_exactly_once(
    make_client, client, make_user, db
):
    _sam, _vera, staff_h, _events, [booking_id], _venue = _setup(client, make_user, db)

    results = race(make_client, THREADS, lambda c: _approve(c, staff_h, booking_id))

    assert sorted(r.status_code for r in results) == [200] + [409] * (THREADS - 1)
    assert db.get(VenueBooking, booking_id).status == BookingStatus.approved


def test_an_approve_and_a_reject_at_the_same_moment_leave_one_consistent_decision(
    make_client, client, make_user, db
):
    _sam, _vera, staff_h, _events, [booking_id], _venue = _setup(client, make_user, db)
    calls = [
        lambda c: _approve(c, staff_h, booking_id),
        lambda c: _reject(c, staff_h, booking_id, reason="Closed for repairs."),
    ] * (THREADS // 2)
    pending = iter(calls)

    results = race(make_client, len(calls), lambda c: next(pending)(c))

    assert sorted(r.status_code for r in results) == [200] + [409] * (len(calls) - 1)
    [winner] = [r.json() for r in results if r.status_code == 200]
    row = db.get(VenueBooking, booking_id)
    assert row.status == winner["status"]
    # The reason belongs to a rejection only: a losing reject must not leave
    # its notes on an approved request.
    assert row.decision_notes == ("Closed for repairs." if row.status == BookingStatus.rejected else None)


def test_two_requests_for_the_same_venue_and_time_approved_at_once_confirm_only_one(
    make_client, client, make_user, db
):
    _sam, _vera, staff_h, _events, booking_ids, venue_id = _setup(client, make_user, db, events=THREADS)
    todo = iter(booking_ids)

    results = race(make_client, THREADS, lambda c: _approve(c, staff_h, next(todo)))

    assert sorted(r.status_code for r in results) == [200] + [409] * (THREADS - 1)
    confirmed = db.query(VenueBooking).filter(
        VenueBooking.venue_id == venue_id, VenueBooking.status == BookingStatus.approved
    )
    assert confirmed.count() == 1  # never double-booked
    assert db.query(VenueBooking).filter(VenueBooking.status == BookingStatus.pending).count() == THREADS - 1
