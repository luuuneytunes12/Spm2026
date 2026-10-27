"""Backend tests for "Record Department & Responsibilities" (SCRUM-19).

  AC1 - only a department from the predefined list can be chosen
  AC2 - a saved department is visible to other internal users
  AC3 - saved responsibilities are visible on the profile
  AC4 - choosing a different department replaces the old one
  AC5 - saving with no department is blocked and the field is flagged
  AC6 - someone else's profile cannot be changed
"""

import pytest

from app.core.departments import Department
from app.core.roles import Role
from app.models.user import User
from event_review_test_helpers import user

ME = "/users/me"
STAFF = "/users/staff"
INTERNAL = [
    Role.COORDINATOR,
    Role.COORDINATOR_LEAD,
    Role.VENUE_STAFF,
    Role.TECH_SUPPORT,
    Role.SAFETY_OFFICER,
]


def _staff(client, db_session, role=Role.COORDINATOR, email="staff@example.com", name="Sam Staff"):
    return user(client, db_session, role, email, name)


def _row(db_session, user_id):
    db_session.expire_all()
    return db_session.get(User, user_id)


# --- AC1: only a listed department ------------------------------------------


@pytest.mark.parametrize("role", INTERNAL)
def test_ac1_every_internal_role_can_choose_a_listed_department(client, db_session, role):
    row, h = _staff(client, db_session, role)
    for dept in Department:
        res = client.patch(ME, json={"department": dept.value}, headers=h)
        assert res.status_code == 200
        assert res.json()["department"] == dept.value


def test_ac1_a_department_outside_the_list_is_rejected_and_nothing_is_written(client, db_session):
    row, h = _staff(client, db_session)
    assert client.patch(ME, json={"department": "venue_operations"}, headers=h).status_code == 200
    res = client.patch(
        ME, json={"department": "marketing", "responsibilities": "x"}, headers=h
    )
    assert res.status_code == 422
    assert "department" in [e["loc"][-1] for e in res.json()["detail"]]
    saved = _row(db_session, row.id)
    assert saved.department == "venue_operations" and saved.responsibilities is None


# --- AC2: visible to other internal users -----------------------------------


def test_ac2_a_saved_department_is_visible_to_other_internal_users(client, db_session):
    _, h = _staff(client, db_session, Role.COORDINATOR, "a@example.com", "Ann Coordinator")
    _, other_h = _staff(client, db_session, Role.VENUE_STAFF, "b@example.com", "Bob Venue")
    client.patch(
        ME, json={"department": "events_coordination", "responsibilities": "Runs gala events"}, headers=h
    )
    rows = client.get(STAFF, headers=other_h).json()
    ann = next(r for r in rows if r["name"] == "Ann Coordinator")
    assert ann["department"] == "events_coordination"
    assert ann["responsibilities"] == "Runs gala events"


def test_ac2_the_directory_lists_only_internal_staff_in_name_order_without_private_fields(
    client, db_session
):
    _, h = _staff(client, db_session, Role.COORDINATOR, "z@example.com", "Zed")
    _staff(client, db_session, Role.SAFETY_OFFICER, "m@example.com", "Mia")
    user(client, db_session, Role.ORGANISER, "o@example.com", "Olive Organiser")
    user(client, db_session, Role.ATTENDEE, "t@example.com", "Tim Attendee")
    rows = client.get(STAFF, headers=h).json()
    assert [r["name"] for r in rows] == ["Mia", "Zed"]
    assert set(rows[0]) == {"id", "name", "email", "role", "department", "responsibilities"}


@pytest.mark.parametrize("role", [Role.ORGANISER, Role.ATTENDEE])
def test_ac2_non_staff_cannot_see_the_staff_directory(client, db_session, role):
    _staff(client, db_session)
    _, h = user(client, db_session, role, "out@example.com", "Outsider")
    assert client.get(STAFF, headers=h).status_code == 403


def test_ac2_the_directory_needs_a_login(client):
    assert client.get(STAFF).status_code == 401


# --- AC3: responsibilities saved and visible --------------------------------


def test_ac3_responsibilities_are_saved_and_visible_on_my_profile(client, db_session):
    row, h = _staff(client, db_session)
    res = client.patch(
        ME,
        json={"department": "technical_support", "responsibilities": "  AV setup and live support  "},
        headers=h,
    )
    assert res.status_code == 200
    assert res.json()["responsibilities"] == "AV setup and live support"
    me = client.get("/auth/me", headers=h).json()["user"]
    assert me["responsibilities"] == "AV setup and live support"
    assert me["department"] == "technical_support"


def test_ac3_responsibilities_can_be_cleared_and_have_a_length_limit(client, db_session):
    row, h = _staff(client, db_session)
    client.patch(ME, json={"department": "technical_support", "responsibilities": "AV"}, headers=h)
    assert client.patch(ME, json={"responsibilities": "   "}, headers=h).json()["responsibilities"] is None
    res = client.patch(ME, json={"responsibilities": "x" * 1001}, headers=h)
    assert res.status_code == 422
    assert _row(db_session, row.id).responsibilities is None


def test_ac3_an_edit_that_omits_them_keeps_department_and_responsibilities(client, db_session):
    row, h = _staff(client, db_session)
    client.patch(ME, json={"department": "venue_operations", "responsibilities": "Keys"}, headers=h)
    res = client.patch(ME, json={"organisation": "Acme"}, headers=h)
    assert res.status_code == 200
    assert (res.json()["department"], res.json()["responsibilities"]) == ("venue_operations", "Keys")


# --- AC4: a different department replaces the old one -----------------------


def test_ac4_choosing_a_different_department_replaces_the_old_one(client, db_session):
    row, h = _staff(client, db_session)
    client.patch(ME, json={"department": "venue_operations"}, headers=h)
    res = client.patch(ME, json={"department": "safety_compliance"}, headers=h)
    assert res.json()["department"] == "safety_compliance"
    assert _row(db_session, row.id).department == "safety_compliance"
    _, other = _staff(client, db_session, Role.TECH_SUPPORT, "o@example.com", "Other")
    mine = next(r for r in client.get(STAFF, headers=other).json() if r["id"] == row.id)
    assert mine["department"] == "safety_compliance"


# --- AC5: no department blocks the save -------------------------------------


def test_ac5_saving_without_a_department_is_blocked_and_the_field_is_flagged(client, db_session):
    row, h = _staff(client, db_session)
    res = client.patch(ME, json={"name": "Renamed", "responsibilities": "Things"}, headers=h)
    assert res.status_code == 422
    assert [e["loc"] for e in res.json()["detail"]] == [["body", "department"]]
    saved = _row(db_session, row.id)
    assert saved.name == "Sam Staff" and saved.responsibilities is None and saved.department is None


def test_ac5_clearing_a_saved_department_is_blocked_and_it_stays(client, db_session):
    row, h = _staff(client, db_session)
    client.patch(ME, json={"department": "venue_operations"}, headers=h)
    res = client.patch(ME, json={"department": None}, headers=h)
    assert res.status_code == 422
    assert _row(db_session, row.id).department == "venue_operations"


# --- AC6: not mine ----------------------------------------------------------


def test_ac6_someone_elses_profile_cannot_be_changed(client, db_session):
    victim, _ = _staff(client, db_session, Role.COORDINATOR, "v@example.com", "Vic")
    _, h = _staff(client, db_session, Role.VENUE_STAFF, "a@example.com", "Attacker")
    client.patch(ME, json={"department": "venue_operations"}, headers=h)
    victim.department = "events_coordination"
    victim.responsibilities = "Original"
    db_session.commit()

    for method in (client.patch, client.put):
        res = method(f"/users/{victim.id}", json={"department": "technical_support"}, headers=h)
        assert res.status_code in (404, 405)
    saved = _row(db_session, victim.id)
    assert (saved.department, saved.responsibilities) == ("events_coordination", "Original")


def test_ac6_an_id_in_the_body_cannot_redirect_the_update_to_another_user(client, db_session):
    victim, _ = _staff(client, db_session, Role.COORDINATOR, "v@example.com", "Vic")
    mine, h = _staff(client, db_session, Role.VENUE_STAFF, "a@example.com", "Attacker")
    victim.department = "events_coordination"
    db_session.commit()
    res = client.patch(ME, json={"id": victim.id, "department": "technical_support"}, headers=h)
    assert res.status_code == 200 and res.json()["id"] == mine.id
    assert _row(db_session, victim.id).department == "events_coordination"
    assert _row(db_session, mine.id).department == "technical_support"


# --- Negative: wrong role ---------------------------------------------------


@pytest.mark.parametrize("role", [Role.ORGANISER, Role.ATTENDEE])
@pytest.mark.parametrize(
    "body", [{"department": "venue_operations"}, {"responsibilities": "Lots"}]
)
def test_non_staff_cannot_record_a_department_or_responsibilities(client, db_session, role, body):
    row, h = user(client, db_session, role, "out@example.com", "Outsider")
    res = client.patch(ME, json={**body, "name": "Changed"}, headers=h)
    assert res.status_code == 403
    saved = _row(db_session, row.id)
    assert (saved.department, saved.responsibilities, saved.name) == (None, None, "Outsider")


def test_non_staff_can_still_edit_their_ordinary_profile(client, db_session):
    _, h = user(client, db_session, Role.ORGANISER, "out@example.com", "Outsider")
    assert client.patch(ME, json={"name": "New"}, headers=h).status_code == 200
