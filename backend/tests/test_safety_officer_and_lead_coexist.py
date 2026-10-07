"""The Safety Officer role (from main) and the Event Coordinator Lead role
(weilun_stories) must both be present and must not widen each other."""

import re
from pathlib import Path

from app.core.roles import ROLE_PERMISSIONS, Permission, Role
from event_review_test_helpers import user

SCHEMA = (Path(__file__).resolve().parents[1] / "db/schema.sql").read_text(encoding="utf-8")


def test_both_roles_exist_in_code_and_in_the_database_enum():
    block = re.search(r"create type user_role as enum \((.*?)\);", SCHEMA, flags=re.S).group(1)
    stored = set(re.findall(r"'(\w+)'", block))
    assert {r.value for r in Role} == stored
    assert {"event_coordinator_lead", "safety_officer"} <= stored


def test_safety_officer_can_only_read_events():
    assert ROLE_PERMISSIONS[Role.SAFETY_OFFICER] == frozenset({Permission.EVENT_READ})


def test_lead_keeps_assignment_powers_and_safety_officer_has_none():
    assert Permission.ASSIGNMENT_MANAGE in ROLE_PERMISSIONS[Role.COORDINATOR_LEAD]
    assert Permission.ASSIGNMENT_MANAGE not in ROLE_PERMISSIONS[Role.SAFETY_OFFICER]
    assert Permission.ASSIGNMENT_VIEW_ALL not in ROLE_PERMISSIONS[Role.SAFETY_OFFICER]


def test_a_safety_officer_can_sign_in_and_is_refused_the_leads_endpoints(client, db_session):
    _, headers = user(client, db_session, Role.SAFETY_OFFICER, "safety@cs.local", "Sasha Safety")
    me = client.get("/auth/me", headers=headers)
    assert me.status_code == 200 and me.json()["user"]["role"] == "safety_officer"
    for path in ("/lead/unassigned-queue", "/lead/assignments", "/lead/coordinators"):
        assert client.get(path, headers=headers).status_code == 403, path


def test_a_lead_can_sign_in_and_still_works_beside_a_safety_officer(client, db_session):
    user(client, db_session, Role.SAFETY_OFFICER, "safety@cs.local", "Sasha Safety")
    _, lead = user(client, db_session, Role.COORDINATOR_LEAD, "lead@cs.local", "Lena Lead")
    assert client.get("/auth/me", headers=lead).json()["user"]["role"] == "event_coordinator_lead"
    assert client.get("/lead/unassigned-queue", headers=lead).status_code == 200
