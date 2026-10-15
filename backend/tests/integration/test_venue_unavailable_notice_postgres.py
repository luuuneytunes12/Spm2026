"""Be told when a booked Venue becomes unavailable (SCRUM-94), on real PostgreSQL.

The SQLite unit tests (tests/test_venue_unavailable_notice.py) prove the
rules; these prove them on the production engine -- setup/turnaround from
the database, timestamptz comparisons, the flag and the notifications in one
transaction -- and that two periods saved at the same moment tell each
Coordinator once, not twice.
"""

import pytest

from app.models.enums import BookingStatus, EventStatus
from app.models.events import Event
from app.models.notifications import Notification
from app.models.venues import VenueBooking
from tests.integration.test_coordinator_concurrency_postgres import race
from tests.integration.test_venue_booking_decision_postgres import _approve
from tests.integration.test_venue_setup_turnaround_postgres import _at, _world

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("coordinator_auto_assign")]


def _body(start, end):
    return {"start_time": start.isoformat(), "end_time": end.isoformat(), "reason_category": "Maintenance", "reason": "Aircon"}


def _messages(db, **filters):
    db.expire_all()
    return [n.message for n in db.query(Notification).filter_by(**filters).order_by(Notification.id)]


def test_ac1_to_ac4_flag_notify_untouched_and_cleared_on_postgres(client, make_user, db):
    # 10-12 occupies 09:30-12:45; 14-16 occupies 13:30-16:45.
    _sam_h, staff_h, venue_id, [approved_id, pending_id] = _world(client, make_user, db, 30, 45, [10, 14])
    assert _approve(client, staff_h, approved_id).status_code == 200
    event_ids = [db.get(VenueBooking, i).event_id for i in (approved_id, pending_id)]
    before = [(db.get(Event, e).status, db.get(Event, e).name) for e in event_ids]

    # AC1: a period between the two events, touching only their buffers.
    res = client.post(f"/venues/{venue_id}/unavailability", json=_body(_at(12, 30), _at(13, 45)), headers=staff_h)
    assert res.status_code == 201, res.text
    assert [a["booking_id"] for a in res.json()["affected_bookings"]] == [approved_id, pending_id]
    db.expire_all()
    assert db.get(VenueBooking, approved_id).conflict_flagged_at is not None
    assert [r["id"] for r in client.get("/venue-bookings/flagged", headers=staff_h).json()] == [approved_id]

    # AC2: nothing cancelled.
    assert [db.get(VenueBooking, i).status for i in (approved_id, pending_id)] == [
        BookingStatus.approved, BookingStatus.pending,
    ]
    assert [(db.get(Event, e).status, db.get(Event, e).name) for e in event_ids] == before
    assert EventStatus.event_cancelled not in {status for status, _ in before}

    # AC3: each Coordinator told, with the affected period.
    told = _messages(db, type="venue_booking_conflict") + _messages(db, type="venue_unavailability_recorded")
    assert len(told) == 2 and all("Action Required" in m for m in told)
    assert "from 02 Nov 2026 12:30 to 02 Nov 2026 12:45 UTC" in told[0]
    assert "from 02 Nov 2026 13:30 to 02 Nov 2026 13:45 UTC" in told[1]

    # AC4: moved clear of both -> both marks gone, both Coordinators told.
    pid = res.json()["id"]
    moved = client.put(f"/venues/{venue_id}/unavailability/{pid}", json=_body(_at(17), _at(18)), headers=staff_h)
    assert moved.status_code == 200 and moved.json()["affected_bookings"] == []
    db.expire_all()
    assert db.get(VenueBooking, approved_id).conflict_flagged_at is None
    assert "cleared" in _messages(db, type="venue_booking_conflict")[-1]
    assert "no longer unavailable" in _messages(db, type="venue_unavailability_recorded")[-1]


def test_two_periods_saved_at_once_tell_a_pending_requests_coordinator_once(client, make_user, db, make_client):
    _sam_h, staff_h, venue_id, [pending_id] = _world(client, make_user, db, 0, 0, [10])
    bodies = iter([_body(_at(9), _at(11)), _body(_at(11), _at(13))])

    results = race(
        make_client, 2, lambda c: c.post(f"/venues/{venue_id}/unavailability", json=next(bodies), headers=staff_h)
    )

    assert sorted(r.status_code for r in results) == [201, 201]
    assert len(_messages(db, type="venue_unavailability_recorded")) == 1
    assert db.get(VenueBooking, pending_id).status == BookingStatus.pending
