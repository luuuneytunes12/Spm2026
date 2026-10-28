"""SCRUM-19 on a real PostgreSQL engine: `department` is a native enum column
and the staff directory filters on the native `user_role` enum."""

import pytest
from sqlalchemy.exc import DBAPIError

from app.core.roles import Role
from app.models.user import User

pytestmark = pytest.mark.integration


def test_ac2_ac4_department_persists_replaces_and_is_listed_on_postgres(client, db, make_user):
    ann, ann_h = make_user(Role.COORDINATOR, "ann@connectsphere.test", "Ann Coordinator")
    _bob, bob_h = make_user(Role.SAFETY_OFFICER, "bob@connectsphere.test", "Bob Safety")
    make_user(Role.ORGANISER, "org@connectsphere.test", "Olive Organiser")

    assert client.patch(
        "/users/me", json={"department": "venue_operations", "responsibilities": "Gala"}, headers=ann_h
    ).status_code == 200
    assert client.patch("/users/me", json={"department": "safety_compliance"}, headers=ann_h).status_code == 200

    rows = client.get("/users/staff", headers=bob_h).json()
    assert [r["name"] for r in rows] == ["Ann Coordinator", "Bob Safety"]
    assert rows[0]["department"] == "safety_compliance" and rows[0]["responsibilities"] == "Gala"
    db.expire_all()
    assert db.get(User, ann.id).department == "safety_compliance"


def test_ac1_ac5_postgres_refuses_an_unlisted_department_and_the_api_blocks_a_missing_one(
    client, db, make_user
):
    row, h = make_user(Role.VENUE_STAFF, "v@connectsphere.test", "Vera Venue")
    assert client.patch("/users/me", json={"department": "marketing"}, headers=h).status_code == 422
    assert client.patch("/users/me", json={"name": "X"}, headers=h).status_code == 422
    row.department = "marketing"
    with pytest.raises(DBAPIError):
        db.commit()
    db.rollback()


def test_ac6_non_staff_directory_and_write_refused_on_postgres(client, db, make_user):
    row, h = make_user(Role.ATTENDEE, "att@connectsphere.test", "Al Attendee")
    assert client.get("/users/staff", headers=h).status_code == 403
    assert client.patch("/users/me", json={"department": "venue_operations"}, headers=h).status_code == 403
    db.expire_all()
    assert db.get(User, row.id).department is None
