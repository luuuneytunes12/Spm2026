"""SCRUM-115 Mark Equipment Damaged or Under Maintenance on real PostgreSQL.

tests/test_equipment_condition.py proves the rules. SQLite has no row locks or
triggers, so these prove the race on the last units, the database's own
constraints, and that the log cannot be rewritten.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.roles import Role
from app.models.enums import EquipmentOperationalStatus
from app.models.equipment import Equipment, EquipmentActivity
from tests.integration.test_coordinator_concurrency_postgres import THREADS, race

pytestmark = pytest.mark.integration


@pytest.fixture()
def item(db):
    row = Equipment(
        name="Shure BLX24",
        category="Audio",
        total_quantity=4,
        operational_status=EquipmentOperationalStatus.available,
    )
    db.add(row)
    db.commit()
    return row


def _mark_path(item_id):
    return f"/equipment/{item_id}/out-of-service"


def test_ac1_ac3_mark_and_return_persist(client, make_user, db, item):
    _, tech_h = make_user(Role.TECH_SUPPORT, "tia@connectsphere.test", "Tia Tech")

    marked = client.post(_mark_path(item.id), json={"condition": "damaged", "quantity": 3}, headers=tech_h)
    assert marked.json()["available_quantity"] == 1

    returned = client.post(
        f"/equipment/{item.id}/return-to-service",
        json={"condition": "damaged", "quantity": 2},
        headers=tech_h,
    )
    assert returned.json()["available_quantity"] == 3
    db.expire_all()
    assert db.get(Equipment, item.id).damaged_quantity == 1
    assert db.query(EquipmentActivity).filter_by(equipment_id=item.id).count() == 2


def test_ac4_racing_marks_cannot_exceed_the_total(make_client, make_user, db, item):
    _, tech_h = make_user(Role.TECH_SUPPORT, "tia@connectsphere.test", "Tia Tech")
    item_id = item.id

    results = race(
        make_client,
        THREADS,
        lambda c: c.post(
            _mark_path(item_id), json={"condition": "maintenance", "quantity": 3}, headers=tech_h
        ).status_code,
    )

    assert results.count(200) == 1
    assert results.count(422) == THREADS - 1
    db.expire_all()
    assert db.get(Equipment, item_id).maintenance_quantity == 3
    assert db.query(EquipmentActivity).filter_by(equipment_id=item_id).count() == 1


@pytest.mark.parametrize(
    "assignment",
    ["damaged_quantity = -1", "maintenance_quantity = -1", "damaged_quantity = 3, maintenance_quantity = 2"],
)
def test_ac4_the_database_refuses_impossible_counts(db, item, assignment):
    with pytest.raises(DBAPIError):
        db.execute(text(f"update equipment set {assignment} where id = :id"), {"id": item.id})
    db.rollback()


def _entry(client, make_user, db, item):
    tech, tech_h = make_user(Role.TECH_SUPPORT, "tia@connectsphere.test", "Tia Tech")
    client.post(_mark_path(item.id), json={"condition": "damaged", "quantity": 1}, headers=tech_h)
    return tech, db.query(EquipmentActivity).filter_by(equipment_id=item.id).one().id


@pytest.mark.parametrize(
    "statement",
    [
        "update equipment_activity set note = 'rewritten' where id = :id",
        "delete from equipment_activity where id = :id",
    ],
)
def test_audit_entries_cannot_be_rewritten_or_removed(client, make_user, db, item, statement):
    _, entry_id = _entry(client, make_user, db, item)

    with pytest.raises(DBAPIError, match="immutable"):
        db.execute(text(statement), {"id": entry_id})
    db.rollback()


def test_audit_entry_outlives_its_actor_and_goes_with_its_item(client, make_user, db, item):
    tech, entry_id = _entry(client, make_user, db, item)
    item_id = item.id

    db.execute(text("delete from users where id = :id"), {"id": tech.id})
    db.commit()
    db.expire_all()
    assert db.get(EquipmentActivity, entry_id).changed_by is None

    db.execute(text("delete from equipment where id = :id"), {"id": item_id})
    db.commit()
    db.expire_all()
    assert db.get(EquipmentActivity, entry_id) is None
