"""SCRUM-81 on a real PostgreSQL engine: several Leads reassigning the same
Event to the same Coordinator at once. The row lock must serialise them, so
exactly one succeeds, the rest are refused ("already has it"), and the
Activity Log gets a single reassignment line. SQLite ignores the lock."""

import pytest

from app.core.roles import Role
from app.models.events import Event, EventStatusHistory
from tests.integration.conftest import submit_event
from tests.integration.test_coordinator_concurrency_postgres import THREADS, race

pytestmark = pytest.mark.integration


def test_ac1_ac3_concurrent_reassignments_to_one_coordinator_exactly_one_wins(client, make_client, db, make_user):
    _o, org_h = make_user(Role.ORGANISER, "org@connectsphere.test", "Olivia Organiser")
    sam, _ = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")
    priya, _ = make_user(Role.COORDINATOR, "priya@connectsphere.test", "Priya Nair")
    _l, lead_h = make_user(Role.COORDINATOR_LEAD, "lead@connectsphere.test", "Lena Lead")
    event_id = submit_event(client, org_h)
    assert client.post(f"/lead/unassigned-queue/{event_id}/assign", json={"coordinator_id": sam.id}, headers=lead_h).status_code == 200

    results = race(
        make_client,
        THREADS,
        lambda c: c.post(f"/lead/assignments/{event_id}/reassign", json={"coordinator_id": priya.id}, headers=lead_h).status_code,
    )

    assert sorted(results) == [200] + [409] * (THREADS - 1)
    db.expire_all()
    assert db.get(Event, event_id).coordinator_id == priya.id
    lines = [h.note for h in db.query(EventStatusHistory).filter(EventStatusHistory.event_id == event_id)
             if h.note and h.note.startswith("Reassigned")]
    assert lines == ["Reassigned from Sam Tan to Priya Nair."]
