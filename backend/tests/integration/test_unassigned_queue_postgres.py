"""The Lead's Unassigned Queue on a real PostgreSQL engine.

The criteria are proven fast on SQLite in tests/test_unassigned_queue.py.
These repeat the two that lean on the database -- oldest-first ordering by a
real timestamp column, and a submit that leaves no Coordinator behind -- on
the engine production uses. The `coordinator_auto_assign` fixture is NOT
used: here, submit must leave the request unassigned.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.roles import Role
from app.models.events import Event
from tests.integration.conftest import submit_event

pytestmark = pytest.mark.integration


def test_queue_ac1_submit_leaves_no_coordinator_even_with_one_available(client, db, make_user):
    _o, org_h = make_user(Role.ORGANISER, "org@connectsphere.test", "Olivia Organiser")
    make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")
    _l, lead_h = make_user(Role.COORDINATOR_LEAD, "lead@connectsphere.test", "Lena Lead")
    event_id = submit_event(client, org_h)

    rows = client.get("/lead/unassigned-queue", headers=lead_h).json()
    assert [r["id"] for r in rows] == [event_id]
    assert rows[0]["status"] == "submitted_awaiting_coordinator" and rows[0]["coordinator"] is None


def test_queue_ac3_oldest_submission_comes_first(client, db, make_user):
    _o, org_h = make_user(Role.ORGANISER, "org@connectsphere.test", "Olivia Organiser")
    _l, lead_h = make_user(Role.COORDINATOR_LEAD, "lead@connectsphere.test", "Lena Lead")
    newest = submit_event(client, org_h, name="Newest")
    oldest = submit_event(client, org_h, name="Oldest")
    now = datetime.now(timezone.utc)
    for event_id, age in ((oldest, 2), (newest, 1)):
        db.query(Event).filter(Event.id == event_id).update({"submitted_at": now - timedelta(hours=age)})
    db.commit()

    names = [r["name"] for r in client.get("/lead/unassigned-queue", headers=lead_h).json()]
    assert names == ["Oldest", "Newest"]
