"""SCRUM-96 (Change or Cancel One Venue Booking) on real PostgreSQL.

The SQLite tests (tests/test_venue_booking_change_cancel.py) prove the rules;
these prove they hold on the production engine, where two requests really do
arrive at the same moment: a double-clicked Cancel, a second tab, Venue Staff
approving a booking at the instant the Coordinator changes it.

What must never happen: a booking cancelled twice (two log lines, two sets of
notices), a booking that reads approved with nobody having approved it, or
one that reads pending with an approval still attached.
"""

from concurrent.futures import ThreadPoolExecutor
import threading
from datetime import datetime, timezone

import pytest

from app.core.roles import Role
from app.models.enums import BookingStatus, EventStatus, NotificationType
from app.models.events import Event, EventStatusHistory
from app.models.notifications import Notification
from app.models.venues import Venue, VenueBooking
from tests.integration.test_coordinator_concurrency_postgres import THREADS, race

pytestmark = pytest.mark.integration

START = datetime(2026, 11, 2, 9, tzinfo=timezone.utc)
END = datetime(2026, 11, 2, 17, tzinfo=timezone.utc)


def _setup(make_user, db, bookings=("Marina Hall",), status=BookingStatus.pending):
    _o, _oh = make_user(Role.ORGANISER, "org@connectsphere.test", "Priya Menon")
    sam, sam_h = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")
    vera, vera_h = make_user(Role.VENUE_STAFF, "vera@connectsphere.test", "Vera Staff")
    victor, _vh = make_user(Role.VENUE_STAFF, "victor@connectsphere.test", "Victor Staff")
    event = Event(
        name="Regional Partner Conference",
        organiser_id=_o.id,
        coordinator_id=sam.id,
        status=EventStatus.planning_event,
        proposed_start=START,
        proposed_end=END,
        expected_attendance=120,
    )
    db.add(event)
    spare = Venue(name="Spare Hall", location="Building C", capacity=300)
    db.add(spare)
    made = []
    for name in bookings:
        venue = Venue(name=name, location="10 Bayfront Ave", capacity=250)
        db.add(venue)
        db.flush()
        booking = VenueBooking(
            event_id=event.id, venue_id=venue.id, requested_by=sam.id,
            start_time=START, end_time=END, status=status,
        )
        if status is BookingStatus.approved:
            booking.reviewed_by, booking.reviewed_at = vera.id, datetime.now(timezone.utc)
        db.add(booking)
        made.append(booking)
    db.commit()
    return sam_h, vera_h, event, made, spare, (vera, victor)


def _told(db, user, kind):
    return db.query(Notification).filter_by(user_id=user.id, type=kind).count()


def _race_two(make_client, first, second):
    """Run two different calls released at the same instant."""
    barrier = threading.Barrier(2)
    clients = [make_client(), make_client()]

    def run(call, client):
        barrier.wait()
        return call(client)

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(run, first, clients[0])
        b = pool.submit(run, second, clients[1])
        return a.result(), b.result()


def test_scrum96_cancelling_one_booking_many_times_at_once_cancels_it_once(
    make_client, client, make_user, db
):
    sam_h, _vh, event, [booking], _spare, staff = _setup(make_user, db, status=BookingStatus.approved)
    # Plain numbers, read here: the threads must not touch this test's own
    # session, which belongs to one thread.
    booking_id, event_id = booking.id, event.id

    results = race(
        make_client, THREADS, lambda c: c.post(f"/venue-bookings/{booking_id}/cancel", json={}, headers=sam_h)
    )

    assert sorted(r.status_code for r in results) == [200] + [409] * (THREADS - 1)
    db.expire_all()
    assert db.get(VenueBooking, booking_id).status is BookingStatus.cancelled
    assert db.query(EventStatusHistory).filter_by(event_id=event_id).count() == 1
    for member in staff:
        assert _told(db, member, NotificationType.venue_booking_cancelled) == 1


def test_scrum96_cancelling_all_many_times_at_once_cancels_each_booking_once(
    make_client, client, make_user, db
):
    sam_h, _vh, event, bookings, _spare, staff = _setup(
        make_user, db, bookings=("Marina Hall", "Garden Hall", "Sky Room"), status=BookingStatus.approved
    )
    ids = [b["id"] for b in client.get(f"/venue-bookings/events/{event.id}/cancellable", headers=sam_h).json()]
    assert len(ids) == 3

    results = race(
        make_client, THREADS,
        lambda c: c.post(f"/venue-bookings/events/{event.id}/cancel-all", json={"booking_ids": ids}, headers=sam_h),
    )

    assert sorted(r.status_code for r in results) == [200] + [409] * (THREADS - 1)
    db.expire_all()
    assert {b.status for b in db.query(VenueBooking).filter_by(event_id=event.id)} == {BookingStatus.cancelled}
    assert db.query(EventStatusHistory).filter_by(event_id=event.id).count() == 3
    for member in staff:
        assert _told(db, member, NotificationType.venue_booking_cancelled) == 3


def test_scrum96_a_change_racing_an_approval_never_leaves_a_half_decided_booking(
    make_client, client, make_user, db
):
    """Venue Staff approve while the Coordinator moves the booking. Either
    order is fine -- approved at the new venue, or pending at the new venue --
    but never approved with nobody having approved it, or pending with an
    approval still attached."""
    sam_h, vera_h, event, [booking], spare, _staff = _setup(make_user, db)
    booking_id, spare_id = booking.id, spare.id  # plain numbers: see above

    approve, change = _race_two(
        make_client,
        lambda c: c.post(f"/venue-bookings/{booking_id}/approve", headers=vera_h),
        lambda c: c.patch(f"/venue-bookings/{booking_id}", json={"venue_id": spare_id}, headers=sam_h),
    )

    assert approve.status_code in (200, 409) and change.status_code == 200
    db.expire_all()
    row = db.get(VenueBooking, booking_id)
    assert row.venue_id == spare_id  # the change always lands
    if row.status is BookingStatus.approved:
        assert row.reviewed_by is not None
    else:
        assert row.status is BookingStatus.pending
        assert row.reviewed_by is None and row.reviewed_at is None
