"""Flagging conflicting bookings (SCRUM-92) on real PostgreSQL: the new
conflict_flagged_at column in db/schema.sql, the flag / un-flag / keep cycle,
and a setup/turnaround save racing an approval -- afterwards no two approved
bookings overlap without both being flagged."""

import threading

import pytest

from app.models.enums import BookingStatus
from app.models.events import EventStatusHistory
from app.models.notifications import Notification
from app.models.venues import VenueBooking
from tests.integration.test_booking_conflicts_postgres import _world
from tests.integration.test_coordinator_concurrency_postgres import race
from tests.integration.test_venue_booking_decision_postgres import _approve

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("coordinator_auto_assign")]

CLASH = {"setup_minutes": 30, "turnaround_minutes": 45}


def _save(client, staff_h, venue_id, body):
    return client.put(f"/venues/{venue_id}/setup-turnaround", json=body, headers=staff_h)


def _flags(db, ids):
    db.expire_all()
    return [db.get(VenueBooking, i).conflict_flagged_at is not None for i in ids]


def test_ac1_ac2_ac3_ac4_flag_notify_list_and_clear_on_postgres(client, make_user, db):
    sam_h, staff_h, venue_id, [first, second] = _world(client, make_user, db, 0, 0, [10, 13])
    assert _approve(client, staff_h, first).status_code == 200
    assert _approve(client, staff_h, second).status_code == 200  # 0/0: no clash

    res = _save(client, staff_h, venue_id, CLASH)
    assert res.status_code == 200 and res.json()["recheck"] == {"flagged": 2, "cleared": 0}
    assert _flags(db, [first, second]) == [True, True]
    assert db.query(Notification).filter_by(type="venue_booking_conflict").count() == 2

    assert _save(client, staff_h, venue_id, CLASH).json()["recheck"] == {"flagged": 0, "cleared": 0}
    assert db.query(Notification).filter_by(type="venue_booking_conflict").count() == 2

    rows = client.get("/venue-bookings/flagged", headers=staff_h).json()
    assert [r["id"] for r in rows] == [first, second]
    assert rows[0]["conflicts"][0]["overlap_start"].startswith("2026-11-02T12:30")
    assert rows[0]["status"] == "approved"
    assert client.get("/venue-bookings/flagged", headers=sam_h).status_code == 403

    assert client.post(f"/venue-bookings/{first}/keep-conflict", json={"reason": " "}, headers=staff_h).status_code == 422
    kept = client.post(f"/venue-bookings/{first}/keep-conflict", json={"reason": "Separate rooms"}, headers=staff_h)
    assert kept.status_code == 200 and kept.json()["conflict_flagged"] is False
    assert client.post(f"/venue-bookings/{first}/keep-conflict", json={"reason": "x"}, headers=staff_h).status_code == 409
    notes = [h.note for h in db.query(EventStatusHistory).order_by(EventStatusHistory.id) if "kept" in (h.note or "")]
    assert len(notes) == 1 and "Separate rooms" in notes[0]

    assert _save(client, staff_h, venue_id, {"setup_minutes": 0, "turnaround_minutes": 0}).json()["recheck"] == {
        "flagged": 0,
        "cleared": 1,
    }
    assert _flags(db, [first, second]) == [False, False]


@pytest.mark.parametrize("attempt", range(3))
def test_a_setup_save_racing_an_approval_never_leaves_an_unflagged_clash(
    client, make_user, db, make_client, attempt
):
    _, staff_h, venue_id, [first, second] = _world(client, make_user, db, 0, 0, [10, 13])
    assert _approve(client, staff_h, first).status_code == 200

    jobs = iter(
        [
            lambda c: ("save", _save(c, staff_h, venue_id, CLASH)),
            lambda c: ("approve", _approve(c, staff_h, second)),
        ]
    )
    lock = threading.Lock()

    def call(c):
        with lock:
            job = next(jobs)
        return job(c)

    results = dict(race(make_client, 2, call))
    save, approve = results["save"], results["approve"]
    assert save.status_code == 200

    db.expire_all()
    status = db.get(VenueBooking, second).status
    if status == BookingStatus.approved:
        # approval got in first: the save then saw both and flagged both
        assert _flags(db, [first, second]) == [True, True]
    else:
        # the save won: the approval was refused as a clash, nothing flagged
        assert status == BookingStatus.pending and approve.status_code == 409
        assert _flags(db, [first, second]) == [False, False]


def test_ac1_ac6_an_active_hold_is_flagged_and_a_flagged_booking_can_be_cancelled_on_postgres(
    client, make_user, db
):
    """'hold' must exist in the native booking_status enum (db/schema.sql)."""
    _, staff_h, venue_id, [first, second] = _world(client, make_user, db, 0, 0, [10, 13])
    assert _approve(client, staff_h, first).status_code == 200
    assert _approve(client, staff_h, second).status_code == 200
    db.get(VenueBooking, second).status = BookingStatus.hold
    db.commit()

    res = _save(client, staff_h, venue_id, CLASH)
    assert res.status_code == 200 and res.json()["recheck"]["flagged"] == 1
    assert _flags(db, [first, second]) == [False, True]  # a hold blocks nobody; the hold is flagged
    db.expire_all()
    assert db.get(VenueBooking, second).status == BookingStatus.hold  # kept as a hold, not cancelled

    assert client.post(f"/venue-bookings/{first}/cancel-flagged", json={"reason": "x"}, headers=staff_h).status_code == 409
    done = client.post(f"/venue-bookings/{second}/cancel-flagged", json={"reason": "Not needed"}, headers=staff_h)
    assert done.status_code == 200 and done.json()["status"] == "cancelled" and done.json()["conflict_flagged"] is False
    assert _flags(db, [first, second]) == [False, False]
    notes = [h.note for h in db.query(EventStatusHistory).order_by(EventStatusHistory.id) if "cancelled by Venue Staff" in (h.note or "")]
    assert len(notes) == 1 and "Not needed" in notes[0]
