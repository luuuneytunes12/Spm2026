"""Tests for SCRUM-61 "Set Up Core Database Schema".

    As a developer, I want the core database schema set up with all primary
    entities, so that all user-facing features have a reliable and consistent
    data layer to build on.

Reads the models' metadata and db/schema.sql without a database server. That
the constraints are enforced is PostgreSQL's job and is proved by
tests/integration/test_platform_postgres.py.
"""

import re
from pathlib import Path

import pytest

from app.core.db import Base
from app.core.roles import Role
from app.models.enums import EventStatus, NotificationType
from app.models.equipment import Equipment
from app.models.events import Event, EventStatusHistory
from app.models.notifications import Notification
from app.models.registrations import Registration
from app.models.user import User
from app.models.venues import Venue

SCHEMA = (Path(__file__).resolve().parents[1] / "db/schema.sql").read_text(encoding="utf-8")
SQL_TABLES = set(re.findall(r"create table (\w+)", SCHEMA))


@pytest.mark.parametrize(
    "table",
    ["users", "events", "venues", "equipment", "registrations", "notifications", "event_status_history"],
)
def test_ac1_each_primary_entity_has_a_table_in_the_models_and_in_schema_sql(table):
    assert table in Base.metadata.tables
    assert table in SQL_TABLES


def test_ac1_roles_are_the_native_enum_on_users_rather_than_a_table():
    block = re.search(r"create type user_role as enum \((.*?)\);", SCHEMA, flags=re.S).group(1)
    assert {r.value for r in Role} == set(re.findall(r"'(\w+)'", block))
    assert "role" in Base.metadata.tables["users"].columns


def test_ac1_every_model_table_is_created_by_schema_sql():
    assert set(Base.metadata.tables) <= SQL_TABLES


@pytest.mark.parametrize(
    "table, column, target",
    [
        ("events", "organiser_id", "users.id"),
        ("events", "coordinator_id", "users.id"),
        ("event_status_history", "event_id", "events.id"),
        ("event_status_history", "changed_by", "users.id"),
        ("venue_bookings", "event_id", "events.id"),
        ("venue_bookings", "venue_id", "venues.id"),
        ("equipment_requests", "event_id", "events.id"),
        ("equipment_requests", "equipment_id", "equipment.id"),
        ("registrations", "event_id", "events.id"),
        ("registrations", "attendee_id", "users.id"),
        ("notifications", "user_id", "users.id"),
        ("notifications", "event_id", "events.id"),
    ],
)
def test_ac2_related_tables_are_joined_by_a_foreign_key(table, column, target):
    keys = Base.metadata.tables[table].columns[column].foreign_keys
    assert target in {key.target_fullname for key in keys}


def _owner_and_event():
    owner = User(name="Owner", email="owner@example.com", password_hash="x", role=Role.ORGANISER.value)
    event = Event(organiser=owner, name="Summit", status=EventStatus.draft)
    return owner, event


def _read_back(db_session, row):
    db_session.add(row)
    db_session.commit()
    model, key = type(row), row.id
    db_session.expire_all()
    return db_session.get(model, key)


def test_ac3_a_user_persists(db_session):
    owner, _ = _owner_and_event()
    assert _read_back(db_session, owner).email == "owner@example.com"


def test_ac3_an_event_persists(db_session):
    _, event = _owner_and_event()
    found = _read_back(db_session, event)
    assert found.name == "Summit" and found.organiser.name == "Owner"


def test_ac3_a_venue_persists(db_session):
    venue = Venue(name="Marina Hall", location="10 Bayfront Ave", capacity=250)
    assert _read_back(db_session, venue).capacity == 250


def test_ac3_equipment_persists(db_session):
    item = Equipment(name="Projector", category="Projection", total_quantity=8)
    assert _read_back(db_session, item).total_quantity == 8


def test_ac3_a_registration_persists(db_session):
    owner, event = _owner_and_event()
    db_session.add(event)
    db_session.flush()
    found = _read_back(db_session, Registration(event_id=event.id, attendee_id=owner.id))
    assert found.event_id == event.id and found.attendee_id == owner.id


def test_ac3_a_notification_persists(db_session):
    owner, _ = _owner_and_event()
    db_session.add(owner)
    db_session.flush()
    row = Notification(user_id=owner.id, type=NotificationType.event_assigned, message="Hello")
    assert _read_back(db_session, row).message == "Hello"


def test_ac3_an_activity_log_line_persists(db_session):
    owner, event = _owner_and_event()
    db_session.add(event)
    db_session.flush()
    row = EventStatusHistory(
        event_id=event.id,
        changed_by=owner.id,
        from_status=EventStatus.draft,
        to_status=EventStatus.submitted_awaiting_coordinator,
        note="Submitted",
    )
    assert _read_back(db_session, row).note == "Submitted"
