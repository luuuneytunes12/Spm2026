"""Cancellation notifications on real PostgreSQL, with overlapping requests.

SQLite serialises every write, so this only shows on Postgres: a
double-clicked Cancel cancels once, so everyone involved is told once.
"""

from datetime import datetime, timezone

import pytest

from app.core.roles import Role
from app.models.enums import EventStatus, NotificationType
from app.models.events import Event
from app.models.notifications import Notification
from app.models.registrations import Registration
from tests.integration.test_coordinator_concurrency_postgres import THREADS, race

pytestmark = pytest.mark.integration

START = datetime(2026, 11, 2, 9, tzinfo=timezone.utc)
END = datetime(2026, 11, 2, 17, tzinfo=timezone.utc)


def test_ac1_ac5_a_double_clicked_cancel_tells_everyone_once(make_client, db, make_user):
    organiser, _ = make_user(Role.ORGANISER, "org@connectsphere.test", "Priya Menon")
    coordinator, coord_h = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")
    attendee, _ = make_user(Role.ATTENDEE, "amy@connectsphere.test", "Amy Attendee")
    event = Event(
        name="Partner Summit",
        organiser_id=organiser.id,
        coordinator_id=coordinator.id,
        status=EventStatus.safety_check_passed,
        proposed_start=START,
        proposed_end=END,
        expected_attendance=120,
    )
    db.add(event)
    db.flush()
    db.add(Registration(event_id=event.id, attendee_id=attendee.id))
    db.commit()
    event_id = event.id

    results = race(
        make_client,
        THREADS,
        lambda c: c.post(f"/events/{event_id}/cancel", json={"reason": "Budget cut"}, headers=coord_h),
    )

    assert [r.status_code for r in results].count(200) == 1
    db.expire_all()
    told = db.query(Notification).filter_by(type=NotificationType.event_cancelled.value)
    assert sorted(n.user_id for n in told) == sorted([organiser.id, coordinator.id, attendee.id])
