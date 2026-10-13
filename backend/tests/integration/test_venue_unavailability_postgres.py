"""Temporarily unavailable venues (SCRUM-93) on real PostgreSQL: the new
columns and check constraints in db/schema.sql, affected bookings identified
and flagged (never cancelled), and a period being saved while an approval is
racing for the same time -- afterwards no approved booking sits inside the
period without being flagged."""

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.enums import BookingStatus, EventStatus
from app.models.events import Event
from app.models.venues import VenueBooking, VenueUnavailability
from tests.integration.test_coordinator_concurrency_postgres import race
from tests.integration.test_venue_booking_decision_postgres import _approve
from tests.integration.test_venue_setup_turnaround_postgres import _world

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("coordinator_auto_assign")]


def _at(hour, minute=0):
    return datetime(2026, 11, 2, hour, minute, tzinfo=timezone.utc)


def _body(start=None, end=None, category="Maintenance", reason="Aircon"):
    return {
        "start_time": (start or _at(8)).isoformat(),
        "end_time": (end or _at(18)).isoformat(),
        "reason_category": category,
        "reason": reason,
    }


def _post(client, staff_h, venue_id, body=None):
    return client.post(f"/venues/{venue_id}/unavailability", json=body or _body(), headers=staff_h)


def test_ac1_ac2_period_persists_and_database_rejects_bad_rows(client, make_user, db):
    _, staff_h, venue_id, _ = _world(client, make_user, db, 0, 0, [])
    res = _post(client, staff_h, venue_id, _body(category="Equipment failure"))
    assert res.status_code == 201
    db.expire_all()
    row = db.get(VenueUnavailability, res.json()["id"])
    assert row.reason_category == "Equipment failure" and row.updated_by is not None

    bad = _post(client, staff_h, venue_id, _body(_at(9), _at(9)))
    assert bad.status_code == 422 and bad.json()["detail"][0]["loc"] == ["body", "end_time"]
    assert db.query(VenueUnavailability).count() == 1

    # the database itself refuses an unknown category and an end before the start
    for kwargs in ({"reason_category": "Party"}, {"end_time": _at(7)}):
        values = dict(venue_id=venue_id, start_time=_at(8), end_time=_at(9), created_by=row.created_by,
                      reason_category="Other")
        values.update(kwargs)
        db.add(VenueUnavailability(**values))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_ac3_ac4_ac5_calendar_review_flag_and_nothing_cancelled(client, make_user, db):
    sam_h, staff_h, venue_id, [first, second] = _world(client, make_user, db, 0, 0, [10, 13])
    assert _approve(client, staff_h, first).status_code == 200  # second stays pending

    res = _post(client, staff_h, venue_id)
    assert res.status_code == 201
    body = res.json()
    assert sorted(a["booking_id"] for a in body["affected_bookings"]) == [first, second]
    assert body["recheck"] == {"flagged": 1, "cleared": 0}

    db.expire_all()
    booking = db.get(VenueBooking, first)
    assert booking.status == BookingStatus.approved and booking.conflict_flagged_at is not None
    assert db.get(Event, booking.event_id).status == EventStatus.planning_event

    [c] = client.get(f"/venue-bookings/{second}", headers=staff_h).json()["conflicts"]
    assert c["kind"] == "unavailability" and c["reason"] == "Maintenance: Aircon"
    assert client.post(f"/venue-bookings/{second}/approve", headers=staff_h).status_code == 409

    busy = client.get(
        f"/venues/{venue_id}/availability",
        params={"start": "2026-11-02T00:00:00Z", "end": "2026-11-03T00:00:00Z"},
        headers=sam_h,
    ).json()["busy"]
    assert [b["reason_category"] for b in busy if b["kind"] == "closure"] == ["Maintenance"]


def test_ac6_ac7_edit_clears_flag_and_coordinator_is_denied(client, make_user, db):
    sam_h, staff_h, venue_id, [first] = _world(client, make_user, db, 0, 0, [10])
    assert _approve(client, staff_h, first).status_code == 200
    pid = _post(client, staff_h, venue_id).json()["id"]
    url = f"/venues/{venue_id}/unavailability/{pid}"

    assert client.put(url, json=_body(_at(14), _at(18)), headers=sam_h).status_code == 403
    assert client.delete(url, headers=sam_h).status_code == 403

    res = client.put(url, json=_body(_at(14), _at(18)), headers=staff_h)
    assert res.status_code == 200 and res.json()["recheck"] == {"flagged": 0, "cleared": 1}
    db.expire_all()
    assert db.get(VenueBooking, first).conflict_flagged_at is None
    assert client.delete(url, headers=staff_h).status_code == 204
    assert db.query(VenueUnavailability).count() == 0


def test_saving_a_period_while_an_approval_races_never_leaves_an_unflagged_booking(
    client, make_user, db, make_client
):
    _, staff_h, venue_id, [first] = _world(client, make_user, db, 0, 0, [10])
    jobs = iter(
        [
            lambda c: ("approve", _approve(c, staff_h, first)),
            lambda c: ("save", _post(c, staff_h, venue_id)),
        ]
    )
    import threading

    lock = threading.Lock()

    def call(c):
        with lock:
            job = next(jobs)
        return job(c)

    results = dict(race(make_client, 2, call))
    assert results["save"].status_code == 201
    db.expire_all()
    booking = db.get(VenueBooking, first)
    if booking.status == BookingStatus.approved:
        assert booking.conflict_flagged_at is not None  # approval won; the save flagged it
    else:
        assert booking.status == BookingStatus.pending and results["approve"].status_code == 409
