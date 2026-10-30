"""Platform stories on real PostgreSQL:

    SCRUM-60  Set Up Notification Infrastructure
    SCRUM-61  Set Up Core Database Schema

The schema is db/schema.sql itself -- the file production is built from --
applied to a throwaway container by the session fixture. SCRUM-61 is checked
against Postgres' own catalogue (tables, foreign keys) and by writing and
reading a row in each core table. SCRUM-60 is checked end to end: a real
status change writes the notification in the same transaction, it reaches
only its recipient, it carries a timezone-aware timestamp, and a request
that fails writes nothing -- the guarantee `notify` documents.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.roles import Role
from app.models.enums import EventStatus, RegistrationStatus
from app.models.events import Event, EventStatusHistory
from app.models.notifications import Notification
from app.models.registrations import Registration
from app.models.user import User
from app.services.notifications import notify
from tests.integration.conftest import assign_event, submit_event

pytestmark = pytest.mark.integration


# --------------------------------------------------------------------------
# SCRUM-61 Core Database Schema
# --------------------------------------------------------------------------

CORE_TABLES = {
    "users", "events", "venues", "venue_bookings", "equipment", "equipment_requests",
    "registrations", "notifications", "event_status_history",  # the activity log
}


def test_scrum61_ac1_every_core_table_exists_and_roles_are_a_database_type(db):
    tables = set(db.execute(text("select tablename from pg_tables where schemaname = 'public'")).scalars())
    assert CORE_TABLES <= tables
    # Roles are a closed set enforced by Postgres (the user_role enum), not free text.
    roles = set(db.execute(text("select unnest(enum_range(null::user_role))::text")).scalars())
    assert {r.value for r in Role} <= roles


@pytest.mark.parametrize("child,column,parent", [
    ("events", "organiser_id", "users"),
    ("events", "coordinator_id", "users"),
    ("venue_bookings", "event_id", "events"),
    ("venue_bookings", "venue_id", "venues"),
    ("equipment_requests", "event_id", "events"),
    ("equipment_requests", "equipment_id", "equipment"),
    ("registrations", "event_id", "events"),
    ("registrations", "attendee_id", "users"),
    ("notifications", "user_id", "users"),
    ("event_status_history", "event_id", "events"),
])
def test_scrum61_ac2_related_tables_are_joined_by_foreign_keys(db, child, column, parent):
    found = db.execute(text("""
        select ccu.table_name
          from information_schema.table_constraints tc
          join information_schema.key_column_usage kcu
            on tc.constraint_name = kcu.constraint_name and tc.table_schema = kcu.table_schema
          join information_schema.constraint_column_usage ccu
            on tc.constraint_name = ccu.constraint_name and tc.table_schema = ccu.table_schema
         where tc.constraint_type = 'FOREIGN KEY' and tc.table_name = :child and kcu.column_name = :column
    """), {"child": child, "column": column}).scalars().all()
    assert found == [parent]


def test_scrum61_ac2_the_database_refuses_an_orphan_row(db):
    db.add(Event(organiser_id=999_999, name="Nobody's event", status=EventStatus.draft))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_scrum61_ac3_rows_persist_and_read_back_from_a_fresh_session(session_factory, make_user):
    attendee, _ = make_user(Role.ATTENDEE, "ava@connectsphere.test", "Ava Attendee")
    organiser, _ = make_user(Role.ORGANISER, "olivia@connectsphere.test", "Olivia Organiser")
    with session_factory() as writer:
        event = Event(organiser_id=organiser.id, name="Persisted", status=EventStatus.draft)
        writer.add(event)
        writer.flush()
        writer.add_all([
            Registration(event_id=event.id, attendee_id=attendee.id),
            EventStatusHistory(event_id=event.id, changed_by=organiser.id, to_status=EventStatus.draft, note="made"),
            Notification(user_id=attendee.id, event_id=event.id, type="event_confirmed", message="hello"),
        ])
        writer.commit()
        event_id = event.id

    with session_factory() as reader:
        assert reader.get(Event, event_id).name == "Persisted"
        reg = reader.query(Registration).filter_by(event_id=event_id).one()
        assert reg.status == RegistrationStatus.registered and reg.registered_at.tzinfo is not None
        assert reader.query(EventStatusHistory).filter_by(event_id=event_id).one().note == "made"
        assert reader.query(Notification).filter_by(event_id=event_id).one().is_read is False


def test_scrum61_unique_and_check_rules_live_in_the_database(db, make_user):
    make_user(Role.ATTENDEE, "ava@connectsphere.test")
    db.add(User(name="Twin", email="ava@connectsphere.test", password_hash="x", role=Role.ATTENDEE.value))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    with pytest.raises(Exception):
        db.execute(text("insert into users (name, email, password_hash, role) values ('X', 'x@x.test', 'x', 'admin')"))
    db.rollback()


# --------------------------------------------------------------------------
# SCRUM-60 Notification Infrastructure
# --------------------------------------------------------------------------


def test_scrum60_ac1_ac2_a_status_change_notifies_its_recipient_with_message_and_time(client, make_user, db):
    organiser, org_h = make_user(Role.ORGANISER, "olivia@connectsphere.test", "Olivia Organiser")
    coordinator, coord_h = make_user(Role.COORDINATOR, "cora@connectsphere.test", "Cora Coord")
    _l, lead_h = make_user(Role.COORDINATOR_LEAD, "lena@connectsphere.test", "Lena Lead")
    event_id = submit_event(client, org_h)
    assign_event(client, lead_h, event_id, coordinator.id)

    client.post(f"/events/{event_id}/approve", headers=coord_h)

    approved = [n for n in client.get("/notifications", headers=org_h).json() if n["type"] == "event_approved"]
    assert len(approved) == 1
    note = approved[0]
    assert note["event_id"] == event_id and "approved" in note["message"]
    assert note["created_at"].endswith(("Z", "+00:00"))  # an instant, not a wall-clock time
    row = db.get(Notification, note["id"])
    assert row.user_id == organiser.id


def test_scrum60_ac3_nobody_else_receives_or_can_read_it(client, make_user, db):
    organiser, org_h = make_user(Role.ORGANISER, "olivia@connectsphere.test", "Olivia Organiser")
    coordinator, coord_h = make_user(Role.COORDINATOR, "cora@connectsphere.test", "Cora Coord")
    _l, lead_h = make_user(Role.COORDINATOR_LEAD, "lena@connectsphere.test", "Lena Lead")
    _a, ava_h = make_user(Role.ATTENDEE, "ava@connectsphere.test", "Ava Attendee")
    event_id = submit_event(client, org_h)
    assign_event(client, lead_h, event_id, coordinator.id)
    client.post(f"/events/{event_id}/approve", headers=coord_h)
    approved_id = db.query(Notification).filter_by(type="event_approved").one().id

    assert all(n["type"] != "event_approved" for n in client.get("/notifications", headers=coord_h).json())
    assert client.get("/notifications", headers=ava_h).json() == []
    # Marking someone else's notification read is silently ignored.
    assert client.post("/notifications/read", json={"ids": [approved_id]}, headers=ava_h).json()["updated"] == 0
    db.expire_all()
    assert db.get(Notification, approved_id).is_read is False


def test_scrum60_newest_first_and_read_state_persists(client, make_user, db):
    me, headers = make_user(Role.COORDINATOR, "cora@connectsphere.test", "Cora Coord")
    for i in range(3):
        db.add(Notification(user_id=me.id, type="event_assigned", message=f"n{i}"))
        db.commit()

    listed = client.get("/notifications", headers=headers).json()
    assert [n["message"] for n in listed] == ["n2", "n1", "n0"]

    assert client.post("/notifications/read", json={"ids": [listed[0]["id"]]}, headers=headers).json()["updated"] == 1
    assert client.post("/notifications/read-all", headers=headers).json()["updated"] == 2
    assert client.post("/notifications/read-all", headers=headers).json()["updated"] == 0
    assert all(n["is_read"] for n in client.get("/notifications", headers=headers).json())


def test_scrum60_a_rolled_back_change_leaves_no_notification(session_factory, make_user):
    organiser, _ = make_user(Role.ORGANISER, "olivia@connectsphere.test", "Olivia Organiser")

    with session_factory() as session:
        notify(session, user_id=organiser.id, type="event_approved", message="never happened")
        session.rollback()

    with session_factory() as check:
        assert check.query(Notification).count() == 0


def test_scrum60_a_refused_action_sends_no_notification(client, make_user, db):
    organiser, org_h = make_user(Role.ORGANISER, "olivia@connectsphere.test", "Olivia Organiser")
    make_user(Role.COORDINATOR_LEAD, "lena@connectsphere.test", "Lena Lead")
    event_id = client.post("/events", json={"name": "Incomplete"}, headers=org_h).json()["id"]

    assert client.post(f"/events/{event_id}/submit", headers=org_h).status_code == 422
    assert db.query(Notification).count() == 0
