"""SCRUM-82 on a real PostgreSQL engine: the filter and the per-Coordinator
count are a real GROUP BY / enum comparison, so they are repeated here."""

import pytest

from app.core.roles import Role
from app.models.enums import EventStatus
from app.models.events import Event

pytestmark = pytest.mark.integration


def _event(db, organiser_id, coordinator_id, status):
    db.add(Event(organiser_id=organiser_id, coordinator_id=coordinator_id, name="E", status=status))
    db.commit()


def test_ac2_counts_and_filter_agree_on_postgres(client, db, make_user):
    org, _ = make_user(Role.ORGANISER, "org@connectsphere.test", "Olivia Organiser")
    sam, _ = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")
    priya, _ = make_user(Role.COORDINATOR, "priya@connectsphere.test", "Priya Nair")
    _l, lead_h = make_user(Role.COORDINATOR_LEAD, "lead@connectsphere.test", "Lena Lead")
    for status in (EventStatus.under_review, EventStatus.planning, EventStatus.completed):
        _event(db, org.id, sam.id, status)
    _event(db, org.id, priya.id, EventStatus.confirmed)

    counts = {r["name"]: r["active_events"] for r in client.get("/lead/coordinators", headers=lead_h).json()}
    assert counts == {"Priya Nair": 1, "Sam Tan": 2}
    sams = client.get("/lead/assignments", params={"coordinator_id": sam.id}, headers=lead_h).json()
    assert len(sams) == counts["Sam Tan"] and {r["status"] for r in sams} == {"under_review", "planning"}
