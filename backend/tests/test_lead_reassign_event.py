"""Backend tests for SCRUM-81, "Reassign Event as Coordinator Lead".

  AC1 - the new Coordinator can open and act on it; the previous one cannot
  AC2 - status and details are unchanged; earlier Activity Log entries are kept
  AC3 - the Activity Log records the Lead, the previous and new Coordinators, the time
  AC4 - an Event Rejected / Cancelled / Completed cannot be reassigned
  AC5 - anyone without the Lead role is refused; the assignment is unchanged

These tests do not use the `coordinator_auto_assign` fixture.
"""

import pytest

from app.core.roles import Role
from app.models.enums import EventStatus
from app.models.events import Event, EventStatusHistory
from app.models.notifications import Notification
from app.services.lead_assignment import FINISHED_STATUSES, ReassignEvent
from event_review_test_helpers import COMPLETE, user


@pytest.fixture()
def w(client, db_session):
    org, org_h = user(client, db_session, Role.ORGANISER, "org@cs.local", "Olivia Organiser")
    sam, sam_h = user(client, db_session, Role.COORDINATOR, "sam@cs.local", "Sam Tan")
    priya, priya_h = user(client, db_session, Role.COORDINATOR, "priya@cs.local", "Priya Nair")
    lead, lead_h = user(client, db_session, Role.COORDINATOR_LEAD, "lead@cs.local", "Lena Lead")
    return dict(db=db_session, org=org, org_h=org_h, sam=sam, sam_h=sam_h, priya=priya, priya_h=priya_h,
                lead=lead, lead_h=lead_h)


def assigned_event(client, w, coordinator=None) -> int:
    """The real path: Organiser submits, the Lead assigns -- so the log is genuine."""
    event_id = client.post("/events", json=COMPLETE, headers=w["org_h"]).json()["id"]
    assert client.post(f"/events/{event_id}/submit", headers=w["org_h"]).status_code == 200
    res = client.post(f"/lead/unassigned-queue/{event_id}/assign",
                      json={"coordinator_id": (coordinator or w["sam"]).id}, headers=w["lead_h"])
    assert res.status_code == 200
    return event_id


def reassign(client, w, event_id, coordinator, headers=None):
    return client.post(f"/lead/assignments/{event_id}/reassign", json={"coordinator_id": coordinator.id},
                       headers=headers or w["lead_h"])


def set_status(w, event_id, status):
    w["db"].query(Event).filter(Event.id == event_id).update({"status": status})
    w["db"].commit()


def log(client, w, event_id):
    return client.get(f"/events/{event_id}/activity", headers=w["org_h"]).json()


# --- AC1 -------------------------------------------------------------------


def test_ac1_the_new_coordinator_can_open_and_act_on_it(client, w):
    e = assigned_event(client, w)
    assert reassign(client, w, e, w["priya"]).status_code == 200
    assert client.get(f"/events/assigned/{e}", headers=w["priya_h"]).status_code == 200
    assert [r["id"] for r in client.get("/events/assigned", headers=w["priya_h"]).json()] == [e]
    approved = client.post(f"/events/{e}/approve", headers=w["priya_h"])
    assert approved.status_code == 200 and approved.json()["status"] == "event_approved"


def test_ac1_the_previous_coordinator_can_no_longer_open_or_act_on_it(client, w):
    e = assigned_event(client, w)
    reassign(client, w, e, w["priya"])
    old = w["sam_h"]
    assert client.get(f"/events/assigned/{e}", headers=old).status_code == 409  # told it moved, see below
    for res in (
        client.post(f"/events/{e}/approve", headers=old),
        client.post(f"/events/{e}/reject", json={"reason": "no"}, headers=old),
        client.put(f"/events/assigned/{e}/registration", json={"registration_enabled": True}, headers=old),
    ):
        assert res.status_code in (403, 404), res.request.url
    assert client.get("/events/assigned", headers=old).json() == []
    assert w["db"].get(Event, e).status == EventStatus.under_review


def test_ac1_the_organiser_sees_the_new_coordinator_and_everyone_is_told(client, w):
    e = assigned_event(client, w)
    reassign(client, w, e, w["priya"])
    assert client.get(f"/events/{e}", headers=w["org_h"]).json()["coordinator"]["name"] == "Priya Nair"
    db = w["db"]
    def notes(user_id):
        return [n.message for n in db.query(Notification).filter(Notification.user_id == user_id, Notification.event_id == e)]
    assert any("assigned to coordinate" in m for m in notes(w["priya"].id))
    assert any("Priya Nair has taken over" in m for m in notes(w["sam"].id))
    assert any("Priya Nair" in m and "priya@cs.local" in m for m in notes(w["org"].id))


def test_ac1_workload_counts_move_with_the_event(client, w):
    e = assigned_event(client, w)
    reassign(client, w, e, w["priya"])
    rows = {r["name"]: r["active_events"] for r in client.get("/lead/coordinators", headers=w["lead_h"]).json()}
    assert rows == {"Priya Nair": 1, "Sam Tan": 0}


# --- AC2 -------------------------------------------------------------------


@pytest.mark.parametrize("status", [EventStatus.under_review, EventStatus.awaiting_organiser_reply, EventStatus.event_approved,
                                    EventStatus.planning_event, EventStatus.safety_check_passed])
def test_ac2_status_and_details_are_unchanged(client, w, status):
    e = assigned_event(client, w)
    set_status(w, e, status)
    before = client.get(f"/events/{e}", headers=w["org_h"]).json()
    assert reassign(client, w, e, w["priya"]).status_code == 200
    after = client.get(f"/events/{e}", headers=w["org_h"]).json()
    assert after["status"] == before["status"] == status.value
    changed = {k for k in before if before[k] != after[k]}
    assert changed <= {"coordinator", "coordinator_id", "updated_at"}


def test_ac2_earlier_activity_log_entries_are_kept(client, w):
    e = assigned_event(client, w)
    before = log(client, w, e)  # newest first: [assigned, submitted]
    assert len(before) >= 2
    reassign(client, w, e, w["priya"])
    after = log(client, w, e)
    assert len(after) == len(before) + 1
    assert after[1:] == before  # every earlier entry is still there, untouched


# --- AC3 -------------------------------------------------------------------


def test_ac3_the_activity_log_records_the_lead_both_coordinators_and_the_time(client, w):
    e = assigned_event(client, w)
    reassign(client, w, e, w["priya"])
    line = log(client, w, e)[0]
    assert line["changed_by_name"] == "Lena Lead"
    assert "Sam Tan" in line["note"] and "Priya Nair" in line["note"]
    assert line["note"] == "Reassigned from Sam Tan to Priya Nair."
    assert line["created_at"]
    assert line["from_status"] == line["to_status"] == "under_review"  # a same-status entry


def test_ac3_a_second_reassignment_adds_a_second_line(client, w):
    e = assigned_event(client, w)
    reassign(client, w, e, w["priya"])
    reassign(client, w, e, w["sam"])
    notes = [l["note"] for l in log(client, w, e)[:2]]
    assert notes == ["Reassigned from Priya Nair to Sam Tan.", "Reassigned from Sam Tan to Priya Nair."]


# --- AC4 -------------------------------------------------------------------


@pytest.mark.parametrize("status", list(FINISHED_STATUSES))
def test_ac4_a_finished_event_cannot_be_reassigned(client, w, status):
    e = assigned_event(client, w)
    set_status(w, e, status)
    n = len(log(client, w, e))
    assert reassign(client, w, e, w["priya"]).status_code == 409
    w["db"].expire_all()
    assert w["db"].get(Event, e).coordinator_id == w["sam"].id
    assert len(log(client, w, e)) == n  # nothing was written


def test_ac4_an_event_in_the_queue_cannot_be_reassigned(client, w):
    qid = client.post("/events", json=COMPLETE, headers=w["org_h"]).json()["id"]
    client.post(f"/events/{qid}/submit", headers=w["org_h"])
    assert reassign(client, w, qid, w["priya"]).status_code == 409
    assert w["db"].get(Event, qid).coordinator_id is None


def test_ac4_reassigning_to_the_coordinator_who_already_has_it_is_refused(client, w):
    e = assigned_event(client, w)
    assert reassign(client, w, e, w["sam"]).status_code == 409
    assert len(log(client, w, e)) == 2  # submitted + assigned only


@pytest.mark.parametrize("who", ["lead", "org", "99999"])
def test_ac4_the_new_owner_must_be_a_real_coordinator(client, w, who):
    e = assigned_event(client, w)
    target = {"lead": w["lead"].id, "org": w["org"].id}.get(who, 99999)
    res = client.post(f"/lead/assignments/{e}/reassign", json={"coordinator_id": target}, headers=w["lead_h"])
    assert res.status_code == 422
    assert w["db"].get(Event, e).coordinator_id == w["sam"].id


def test_ac4_an_unknown_event_is_a_404(client, w):
    res = client.post("/lead/assignments/99999/reassign", json={"coordinator_id": w["priya"].id}, headers=w["lead_h"])
    assert res.status_code == 404


# --- AC5 -------------------------------------------------------------------


@pytest.mark.parametrize("role", [Role.ORGANISER, Role.COORDINATOR, Role.VENUE_STAFF, Role.TECH_SUPPORT, Role.ATTENDEE])
def test_ac5_other_roles_are_refused_and_the_assignment_is_unchanged(client, db_session, w, role):
    e = assigned_event(client, w)
    n = len(log(client, w, e))
    _, h = user(client, db_session, role, f"x_{role.value}@cs.local", "Someone")
    assert reassign(client, w, e, w["priya"], headers=h).status_code == 403
    db_session.expire_all()
    assert db_session.get(Event, e).coordinator_id == w["sam"].id
    assert len(log(client, w, e)) == n


def test_ac5_the_assigned_coordinator_cannot_hand_it_on_themselves(client, w):
    e = assigned_event(client, w)
    assert reassign(client, w, e, w["priya"], headers=w["sam_h"]).status_code == 403
    assert w["db"].get(Event, e).coordinator_id == w["sam"].id


def test_ac5_unauthenticated_is_rejected(client, w):
    e = assigned_event(client, w)
    assert client.post(f"/lead/assignments/{e}/reassign", json={"coordinator_id": w["priya"].id}).status_code == 401


# --- OOP -------------------------------------------------------------------


def test_reassign_inherits_the_shared_action_and_keeps_the_stories_finished_set():
    from app.services.lead_assignment import LeadAssignmentAction

    assert issubclass(ReassignEvent, LeadAssignmentAction)
    assert set(FINISHED_STATUSES) == {EventStatus.event_rejected, EventStatus.event_cancelled, EventStatus.event_completed}



# --- previous Coordinator is told who has it now -------------------------------


def test_previous_coordinator_opening_it_is_told_who_it_was_reassigned_to(client, w):
    e = assigned_event(client, w)
    name = w["db"].get(Event, e).name
    reassign(client, w, e, w["priya"])
    res = client.get(f"/events/assigned/{e}", headers=w["sam_h"])
    assert res.status_code == 409
    assert res.json()["detail"] == (
        f"'{name}' that was initially assigned to you by the Event Coordinator Lead "
        "has been reassigned to Priya Nair."
    )


def test_message_follows_a_later_reassignment_to_the_current_coordinator(client, w, db_session):
    _, third_h = user(client, db_session, Role.COORDINATOR, "third@cs.local", "Tara Third")
    third = db_session.query(type(w["sam"])).filter_by(email="third@cs.local").one()
    e = assigned_event(client, w)
    reassign(client, w, e, w["priya"])
    reassign(client, w, e, third)
    assert "reassigned to Tara Third." in client.get(f"/events/assigned/{e}", headers=w["sam_h"]).json()["detail"]


def test_a_coordinator_who_never_held_it_learns_nothing(client, w, db_session):
    _, third_h = user(client, db_session, Role.COORDINATOR, "third@cs.local", "Tara Third")
    e = assigned_event(client, w)
    reassign(client, w, e, w["priya"])
    res = client.get(f"/events/assigned/{e}", headers=third_h)
    assert res.status_code == 404
    assert "Priya" not in res.text


def test_reassigned_back_the_original_coordinator_opens_it_normally(client, w):
    e = assigned_event(client, w)
    reassign(client, w, e, w["priya"])
    reassign(client, w, e, w["sam"])
    assert client.get(f"/events/assigned/{e}", headers=w["sam_h"]).status_code == 200
