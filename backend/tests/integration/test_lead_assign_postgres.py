"""SCRUM-80 / SCRUM-81 on a real PostgreSQL engine.

Assigning is a read-check-write on one row, so two Leads acting at once is the
case that matters: the row lock (SELECT ... FOR UPDATE) must let exactly one
win and refuse the rest, leaving a single assignment and a single log line.
SQLite ignores the lock, so this can only be proven here.
"""

import pytest

from app.core.roles import Role
from app.models.enums import EventStatus
from app.models.events import Event, EventStatusHistory
from tests.integration.conftest import submit_event
from tests.integration.test_coordinator_concurrency_postgres import THREADS, race

pytestmark = pytest.mark.integration


def test_ac5_many_leads_assigning_the_same_request_at_once_exactly_one_wins(client, make_client, db, make_user):
    _o, org_h = make_user(Role.ORGANISER, "org@connectsphere.test", "Olivia Organiser")
    coords = [make_user(Role.COORDINATOR, f"c{i}@connectsphere.test", f"Coord {i}")[0] for i in range(THREADS)]
    _l, lead_h = make_user(Role.COORDINATOR_LEAD, "lead@connectsphere.test", "Lena Lead")
    event_id = submit_event(client, org_h)

    counter = iter(range(THREADS))
    results = race(
        make_client,
        THREADS,
        lambda c: c.post(
            f"/lead/unassigned-queue/{event_id}/assign",
            json={"coordinator_id": coords[next(counter)].id},
            headers=lead_h,
        ).status_code,
    )

    assert sorted(results) == [200] + [409] * (THREADS - 1)
    db.expire_all()
    event = db.get(Event, event_id)
    assert event.status == EventStatus.under_review and event.coordinator_id in {c.id for c in coords}
    assigned_lines = [h for h in db.query(EventStatusHistory).filter(EventStatusHistory.event_id == event_id) if h.note and h.note.startswith("Assigned to")]
    assert len(assigned_lines) == 1
