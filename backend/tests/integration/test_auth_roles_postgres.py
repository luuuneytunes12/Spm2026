"""Signing in, roles and landing pages on real PostgreSQL:

    SCRUM-14  Log In to System
    SCRUM-18  Edit User Profile
    SCRUM-62  Set Up Role-Based Access Control (RBAC) Infrastructure
    SCRUM-63  Log Out System
    SCRUM-70  Create Event Coordinator Lead Role
    SCRUM-71..77  Login as <role> (each role's landing page and its counts)
    SCRUM-91  Create Safety Officer Role

The SQLite tests (tests/test_auth.py, test_users.py, test_coordinator_lead_role.py
and the *_landing.py files) prove the rules. Here the real path runs on the
production engine: accounts are rows in a table whose `role` column is the
native `user_role` enum -- so every role the code knows must be a value
Postgres accepts -- passwords are real bcrypt hashes checked by /auth/login,
and every request gets its own session. The landing pages count rows from
existing endpoints, so each role's counts are proven to be that role's own
rows and nobody else's.
"""

import pytest
from sqlalchemy import text

from app.core.roles import ROLE_PERMISSIONS, Permission, Role
from app.models.enums import EquipmentStatus, EventStatus, RegistrationStatus
from app.models.equipment import CoordinatorEquipmentRequirement
from app.models.events import Event
from app.models.notifications import Notification
from app.models.registrations import Registration
from app.models.user import User
from app.models.venues import Venue, VenueBooking
from tests.integration.conftest import submit_event

pytestmark = pytest.mark.integration

PASSWORD = "password123"  # what make_user hashes


def _login(client, email, password=PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


def _bearer(res):
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


# --------------------------------------------------------------------------
# SCRUM-14 Log In / SCRUM-63 Log Out
# --------------------------------------------------------------------------


@pytest.mark.parametrize("role", list(Role))
def test_scrum14_ac1_every_role_signs_in_and_sees_its_own_role_and_grants(client, make_user, role):
    make_user(role, f"{role.value}@connectsphere.test", "Robin Role")

    res = _login(client, f"{role.value}@connectsphere.test")

    assert res.status_code == 200
    me = client.get("/auth/me", headers=_bearer(res)).json()
    assert me["user"]["role"] == role.value and me["user"]["name"] == "Robin Role"
    assert set(me["permissions"]) == {p.value for p in ROLE_PERMISSIONS.get(role, frozenset())}


def test_scrum14_login_is_case_insensitive_on_email_and_sets_a_refresh_cookie(client, make_user):
    make_user(Role.ORGANISER, "olivia@connectsphere.test", "Olivia Organiser")

    res = _login(client, "Olivia@ConnectSphere.TEST")

    assert res.status_code == 200
    assert "refresh_token" in res.cookies


def test_scrum14_ac3_wrong_password_and_unknown_account_get_the_same_answer(client, make_user):
    make_user(Role.ORGANISER, "olivia@connectsphere.test", "Olivia Organiser")

    wrong_password = _login(client, "olivia@connectsphere.test", "not-the-password")
    no_account = _login(client, "nobody@connectsphere.test")

    assert wrong_password.status_code == no_account.status_code == 401
    assert wrong_password.json() == no_account.json() == {"detail": "Invalid credentials"}
    assert "refresh_token" not in wrong_password.cookies and "refresh_token" not in no_account.cookies


@pytest.mark.parametrize("path", ["/auth/me", "/events", "/notifications", "/venues",
                                  "/equipment", "/registrations/mine", "/safety-checks", "/lead/unassigned-queue"])
def test_scrum14_ac4_scrum62_ac3_no_account_means_no_page(client, path):
    res = client.get(path)

    assert res.status_code == 401 and res.json()["detail"] == "Not authenticated"


def test_scrum14_a_registered_account_is_an_attendee_and_can_sign_straight_in(client, db):
    created = client.post("/auth/register", json={"name": "Ava Attendee", "email": "ava@connectsphere.test",
                                                  "password": PASSWORD, "role": "organiser"})
    assert created.status_code == 201

    db.expire_all()
    stored = db.query(User).filter_by(email="ava@connectsphere.test").one()
    assert stored.role == Role.ATTENDEE.value  # a client can never choose its own role
    assert stored.password_hash != PASSWORD and stored.created_at is not None
    assert _login(client, "ava@connectsphere.test").status_code == 200
    duplicate = client.post("/auth/register", json={"name": "Ava Again", "email": "AVA@connectsphere.test",
                                                    "password": PASSWORD})
    assert duplicate.status_code == 409


def test_scrum63_ac1_ac2_logout_ends_the_session(client, make_user):
    make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")
    signed_in = _login(client, "sam@connectsphere.test")
    assert client.post("/auth/refresh").status_code == 200  # the session can renew itself

    out = client.post("/auth/logout")

    assert out.status_code == 204
    assert "refresh_token" not in client.cookies
    assert client.post("/auth/refresh").status_code == 401  # it can no longer renew
    assert client.get("/auth/me").status_code == 401
    assert signed_in.status_code == 200


# --------------------------------------------------------------------------
# SCRUM-62 RBAC / SCRUM-70 Lead role / SCRUM-91 Safety Officer role
# --------------------------------------------------------------------------


def test_scrum61_scrum70_scrum91_every_role_is_a_value_of_the_database_enum(db):
    labels = set(db.execute(text("select unnest(enum_range(null::user_role))::text")).scalars())

    assert {r.value for r in Role} <= labels


ROLE_ONLY = {
    "/lead/unassigned-queue": Role.COORDINATOR_LEAD,
    "/safety-checks": Role.SAFETY_OFFICER,
    "/venue-bookings/queue": Role.VENUE_STAFF,
    "/equipment-requirements/support/requested": Role.TECH_SUPPORT,
    "/registrations/mine": Role.ATTENDEE,
}


@pytest.mark.parametrize("path,owner", ROLE_ONLY.items())
def test_scrum62_ac1_ac4_each_role_only_page_is_open_to_its_role_and_closed_to_the_rest(client, make_user, path, owner):
    accounts = {role: make_user(role, f"{role.value}@connectsphere.test")[1] for role in Role}

    for role, headers in accounts.items():
        status = client.get(path, headers=headers).status_code
        if role == owner:
            assert status == 200, f"{role} should reach {path}"
        else:
            assert status == 403, f"{role} should be refused {path} (got {status})"


def test_scrum62_ac2_a_coordinator_reaches_coordinator_features(client, make_user):
    _c, coord_h = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")

    for path in ("/events/assigned", "/venues", "/equipment", "/events/queue"):
        assert client.get(path, headers=coord_h).status_code == 200, path


def test_scrum62_ac1_an_organiser_cannot_decide_staff_actions(client, make_user, db):
    _o, org_h = make_user(Role.ORGANISER, "org@connectsphere.test", "Olivia Organiser")
    coordinator, coord_h = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")
    event_id = submit_event(client, org_h)
    db.get(Event, event_id).coordinator_id = coordinator.id
    db.get(Event, event_id).status = EventStatus.under_review
    db.commit()

    assert client.post(f"/events/{event_id}/approve", headers=org_h).status_code == 403
    assert client.post(f"/safety-checks/{event_id}/approve", headers=org_h).status_code == 403
    assert client.get("/venue-bookings/queue", headers=org_h).status_code == 403


def test_scrum62_a_token_role_the_system_does_not_know_gets_no_access_not_a_crash(client, make_user):
    from app.core.security import create_access_token

    user, _ = make_user(Role.ATTENDEE, "ava@connectsphere.test")
    headers = {"Authorization": f"Bearer {create_access_token(user.id, 'superuser')}"}

    assert client.get("/auth/me", headers=headers).json()["permissions"] == []
    assert client.get("/events", headers=headers).status_code == 403


def test_scrum70_ac1_the_lead_has_coordinator_grants_plus_assignment(client, make_user):
    make_user(Role.COORDINATOR_LEAD, "lena@connectsphere.test", "Lena Lead")

    perms = set(client.get("/auth/me", headers=_bearer(_login(client, "lena@connectsphere.test"))).json()["permissions"])

    assert {p.value for p in ROLE_PERMISSIONS[Role.COORDINATOR]} < perms
    assert {Permission.ASSIGNMENT_MANAGE.value, Permission.ASSIGNMENT_VIEW_ALL.value} <= perms


@pytest.mark.parametrize("role, department", [
    (Role.COORDINATOR_LEAD, "events_coordination"),
    (Role.SAFETY_OFFICER, "safety_compliance"),
])
def test_scrum70_ac2_scrum91_ac2_new_roles_log_in_out_and_edit_their_profile(client, make_user, db, role, department):
    user, _ = make_user(role, f"{role.value}@connectsphere.test", "New Role")
    headers = _bearer(_login(client, f"{role.value}@connectsphere.test"))

    # Internal staff must have a department to save their profile (SCRUM-19 AC5).
    body = {"organisation": "ConnectSphere", "department": department}
    assert client.patch("/users/me", json=body, headers=headers).status_code == 200
    assert client.post("/auth/logout").status_code == 204
    assert client.post("/auth/refresh").status_code == 401
    db.expire_all()
    assert db.get(User, user.id).organisation == "ConnectSphere"


def test_scrum91_ac3_only_a_safety_officer_may_decide_a_safety_check(client, make_user, db):
    _o, org_h = make_user(Role.ORGANISER, "org@connectsphere.test", "Olivia Organiser")
    event_id = submit_event(client, org_h)
    db.get(Event, event_id).status = EventStatus.awaiting_safety_check
    db.commit()

    for role in Role:
        if role == Role.SAFETY_OFFICER:
            continue
        _u, headers = make_user(role, f"x-{role.value}@connectsphere.test")
        for action, body in (("approve", None), ("reject", {"reason": "x"}), ("request-changes", {"reason": "x"})):
            res = client.post(f"/safety-checks/{event_id}/{action}", json=body, headers=headers)
            assert res.status_code == 403, (role, action)
    db.expire_all()
    assert db.get(Event, event_id).status == EventStatus.awaiting_safety_check


# --------------------------------------------------------------------------
# SCRUM-18 Edit User Profile
# --------------------------------------------------------------------------


def test_scrum18_ac1_ac4_every_field_saves_and_survives_logout_and_login(client, make_user, db):
    user, _ = make_user(Role.VENUE_STAFF, "vic@connectsphere.test", "Vic Venue")
    headers = _bearer(_login(client, "vic@connectsphere.test"))
    changes = {"name": "Victoria Venue", "organisation": "Facilities", "email": "victoria@connectsphere.test",
               "phone_country_code": "+65", "phone_number": "91234567", "communication_preference": "sms",
               "department": "venue_operations"}  # staff must have one (SCRUM-19 AC5)

    res = client.patch("/users/me", json=changes, headers=headers)

    assert res.status_code == 200
    client.post("/auth/logout")
    again = _login(client, "Victoria@connectsphere.test")  # the NEW email signs in
    assert again.status_code == 200
    me = client.get("/auth/me", headers=_bearer(again)).json()["user"]
    assert {k: me[k] for k in changes} == changes
    assert _login(client, "vic@connectsphere.test").status_code == 401  # the old one no longer does


@pytest.mark.parametrize("bad", [
    {"email": "not-an-email"},
    {"phone_country_code": "+65", "phone_number": "9123abcd"},
    {"phone_country_code": "+65", "phone_number": "912"},
    {"phone_number": "91234567"},
    {"name": "   "},
    {"communication_preference": "pigeon"},
])
def test_scrum18_ac2_ac3_an_invalid_field_is_named_and_nothing_is_saved(client, make_user, db, bad):
    user, headers = make_user(Role.ORGANISER, "olivia@connectsphere.test", "Olivia Organiser")

    res = client.patch("/users/me", json={"organisation": "Should not stick", **bad}, headers=headers)

    assert res.status_code == 422
    assert res.text  # the field is named in the body
    db.expire_all()
    stored = db.get(User, user.id)
    assert stored.organisation is None and stored.name == "Olivia Organiser"


def test_scrum18_an_email_belonging_to_someone_else_is_refused_by_the_database_check(client, make_user, db):
    make_user(Role.ORGANISER, "taken@connectsphere.test", "Taken")
    user, headers = make_user(Role.ATTENDEE, "ava@connectsphere.test", "Ava")

    res = client.patch("/users/me", json={"email": "TAKEN@connectsphere.test"}, headers=headers)

    assert res.status_code == 409
    db.expire_all()
    assert db.get(User, user.id).email == "ava@connectsphere.test"


# --------------------------------------------------------------------------
# SCRUM-71..77 Landing pages -- each count is that role's own rows
# --------------------------------------------------------------------------


def _unread(client, headers):
    return len([n for n in client.get("/notifications", headers=headers).json() if not n["is_read"]])


def _notify(db, user, n):
    for i in range(n):
        db.add(Notification(user_id=user.id, type="event_approved", message=f"note {i}"))
    db.commit()


def test_scrum71_organiser_counts_drafts_submitted_and_unread(client, make_user, db):
    me, org_h = make_user(Role.ORGANISER, "olivia@connectsphere.test", "Olivia Organiser")
    _x, other_h = make_user(Role.ORGANISER, "oscar@connectsphere.test", "Oscar Other")
    assert client.get("/events?status=draft", headers=org_h).json() == []  # AC4: nothing to count
    assert _unread(client, org_h) == 0

    for name in ("Draft A", "Draft B"):
        client.post("/events", json={"name": name}, headers=org_h)
    submit_event(client, org_h)
    submit_event(client, other_h)
    client.post("/events", json={"name": "Not mine"}, headers=other_h)
    _notify(db, me, 3)

    assert len(client.get("/events?status=draft", headers=org_h).json()) == 2
    assert len([e for e in client.get("/events", headers=org_h).json() if e["status"] != "draft"]) == 1
    # 3 seeded + the "now Submitted" status notice for her one submitted request.
    assert _unread(client, org_h) == 4
    first = client.get("/notifications", headers=org_h).json()[0]["id"]
    client.post("/notifications/read", json={"ids": [first]}, headers=org_h)
    assert _unread(client, org_h) == 3


def test_scrum72_coordinator_counts_only_their_assigned_events(client, make_user, db):
    _o, org_h = make_user(Role.ORGANISER, "olivia@connectsphere.test", "Olivia Organiser")
    sam, sam_h = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")
    priya, _ = make_user(Role.COORDINATOR, "priya@connectsphere.test", "Priya Nair")
    _l, lead_h = make_user(Role.COORDINATOR_LEAD, "lena@connectsphere.test", "Lena Lead")
    assert client.get("/events/assigned", headers=sam_h).json() == []

    for coordinator in (sam, sam, priya):
        event_id = submit_event(client, org_h)
        client.post(f"/lead/unassigned-queue/{event_id}/assign", json={"coordinator_id": coordinator.id}, headers=lead_h)

    assert len(client.get("/events/assigned", headers=sam_h).json()) == 2
    assert _unread(client, sam_h) == 2  # one "assigned to you" per event


def test_scrum73_venue_staff_count_pending_booking_requests(client, make_user, db):
    _o, org_h = make_user(Role.ORGANISER, "olivia@connectsphere.test", "Olivia Organiser")
    coordinator, _ = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")
    _v, staff_h = make_user(Role.VENUE_STAFF, "vic@connectsphere.test", "Vic Venue")
    assert client.get("/venue-bookings/queue", headers=staff_h).json() == []

    event_id = submit_event(client, org_h)
    venues = [Venue(name=f"Hall {i}", location="Block A", capacity=200) for i in range(3)]
    db.add_all(venues)
    db.commit()
    for venue, status in zip(venues, ("pending", "pending", "approved")):
        db.add(VenueBooking(event_id=event_id, venue_id=venue.id, requested_by=coordinator.id, status=status,
                            start_time="2026-11-02T09:00:00Z", end_time="2026-11-02T17:00:00Z"))
    db.commit()

    assert len(client.get("/venue-bookings/queue", headers=staff_h).json()) == 2


def test_scrum74_tech_support_count_requested_requirements(client, make_user, db):
    _o, org_h = make_user(Role.ORGANISER, "olivia@connectsphere.test", "Olivia Organiser")
    coordinator, _ = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")
    _t, tech_h = make_user(Role.TECH_SUPPORT, "tia@connectsphere.test", "Tia Tech")
    assert client.get("/equipment-requirements/support/requested", headers=tech_h).json() == []

    planning = submit_event(client, org_h)
    db.get(Event, planning).status = EventStatus.planning_event
    still_draft = client.post("/events", json={"name": "Draft"}, headers=org_h).json()["id"]
    # Two waiting on a live event; one on a draft, which Technical Support never sees.
    for event_id in (planning, planning, still_draft):
        db.add(CoordinatorEquipmentRequirement(event_id=event_id, category="Projector", quantity_needed=1,
                                               status=EquipmentStatus.requested, created_by=coordinator.id))
    db.commit()

    assert len(client.get("/equipment-requirements/support/requested", headers=tech_h).json()) == 2


def test_scrum75_attendee_counts_current_registrations(client, make_user, db):
    _o, org_h = make_user(Role.ORGANISER, "olivia@connectsphere.test", "Olivia Organiser")
    ava, ava_h = make_user(Role.ATTENDEE, "ava@connectsphere.test", "Ava Attendee")
    other, _ = make_user(Role.ATTENDEE, "ben@connectsphere.test", "Ben Attendee")
    assert client.get("/registrations/mine", headers=ava_h).json() == []

    events = [submit_event(client, org_h) for _ in range(3)]
    db.add_all([
        Registration(event_id=events[0], attendee_id=ava.id, status=RegistrationStatus.registered),
        Registration(event_id=events[1], attendee_id=ava.id, status=RegistrationStatus.withdrawn),
        Registration(event_id=events[2], attendee_id=other.id, status=RegistrationStatus.registered),
    ])
    db.commit()

    mine = client.get("/registrations/mine", headers=ava_h).json()
    assert sorted(e["id"] for e in mine) == sorted(events[:2])
    assert len([e for e in mine if e["my_status"] == "registered"]) == 1


def test_scrum76_lead_counts_unassigned_requests(client, make_user, db):
    _o, org_h = make_user(Role.ORGANISER, "olivia@connectsphere.test", "Olivia Organiser")
    sam, _ = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")
    lead, lead_h = make_user(Role.COORDINATOR_LEAD, "lena@connectsphere.test", "Lena Lead")
    assert client.get("/lead/unassigned-queue", headers=lead_h).json() == []
    assert _unread(client, lead_h) == 0

    ids = [submit_event(client, org_h) for _ in range(3)]
    client.post(f"/lead/unassigned-queue/{ids[0]}/assign", json={"coordinator_id": sam.id}, headers=lead_h)

    assert len(client.get("/lead/unassigned-queue", headers=lead_h).json()) == 2
    assert _unread(client, lead_h) == 3  # one "new request" notice per submission
    assert len(client.get("/lead/assignments", headers=lead_h).json()) >= 1


def test_scrum77_safety_officer_counts_events_awaiting_a_check(client, make_user, db):
    _o, org_h = make_user(Role.ORGANISER, "olivia@connectsphere.test", "Olivia Organiser")
    sam, _ = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")
    _s, safety_h = make_user(Role.SAFETY_OFFICER, "sol@connectsphere.test", "Sol Safety")
    assert client.get("/safety-checks", headers=safety_h).json() == []

    for status in (EventStatus.awaiting_safety_check, EventStatus.awaiting_safety_check, EventStatus.planning_event):
        event_id = submit_event(client, org_h)
        row = db.get(Event, event_id)
        row.status, row.coordinator_id = status, sam.id
    db.commit()

    assert len(client.get("/safety-checks", headers=safety_h).json()) == 2
    # AC4: another role's page says "no access"
    assert client.get("/lead/unassigned-queue", headers=safety_h).status_code == 403
