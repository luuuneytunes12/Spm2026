"""SCRUM-27 / SCRUM-103 on a real PostgreSQL engine: the status moves, the
log rows and the CHECK constraint, and a double-clicked reply."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.roles import Role
from app.models.clarifications import EventClarification
from app.models.enums import EventStatus
from app.models.events import Event

pytestmark = pytest.mark.integration


def _setup(db, make_user):
    org, org_h = make_user(Role.ORGANISER, "org@connectsphere.test", "Olivia Organiser")
    coord, coord_h = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")
    e = Event(organiser_id=org.id, coordinator_id=coord.id, name="Gala", status=EventStatus.under_review)
    db.add(e)
    db.commit()
    return e.id, org_h, coord_h


def test_request_then_reply_round_trip_on_postgres(client, db, make_user):
    eid, org_h, coord_h = _setup(db, make_user)
    assert client.post(f"/events/{eid}/clarifications", json={"message": "Fire plan?"}, headers=coord_h).status_code == 201
    db.expire_all()
    assert db.get(Event, eid).status == EventStatus.awaiting_organiser_reply
    res = client.post(
        f"/events/{eid}/clarifications/reply",
        json={"message": "Booked.", "updates": {"expected_attendance": 80}},
        headers=org_h,
    )
    assert res.status_code == 201
    db.expire_all()
    e = db.get(Event, eid)
    assert e.status == EventStatus.under_review and e.expected_attendance == 80
    thread = client.get(f"/events/{eid}/clarifications", headers=coord_h).json()
    assert [m["kind"] for m in thread] == ["request", "reply"]
    log = client.get(f"/events/{eid}/activity", headers=org_h).json()
    assert [r["to_status"] for r in log][:2] == ["under_review", "awaiting_organiser_reply"]


def test_repeat_reply_is_refused_on_postgres(client, db, make_user):
    eid, org_h, coord_h = _setup(db, make_user)
    client.post(f"/events/{eid}/clarifications", json={"message": "Q"}, headers=coord_h)
    codes = [client.post(f"/events/{eid}/clarifications/reply", json={"message": "A"}, headers=org_h).status_code for _ in range(2)]
    assert codes == [201, 409]
    assert db.query(EventClarification).filter_by(kind="reply").count() == 1


def test_kind_check_constraint_rejects_unknown_kinds(db, make_user):
    eid, _, _ = _setup(db, make_user)
    org_id = db.get(Event, eid).organiser_id
    with pytest.raises(IntegrityError):
        db.execute(
            text("insert into event_clarifications (event_id, kind, message, author_id) values (:e, 'shout', 'x', :a)"),
            {"e": eid, "a": org_id},
        )
    db.rollback()
