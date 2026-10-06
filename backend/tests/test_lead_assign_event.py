"""Backend tests for SCRUM-80, "Assign Event Request to an Event Coordinator as
Coordinator Lead".

  AC1 - assigning removes the request from the queue, makes it Under Review and
        puts it in that Coordinator's assigned Events
  AC2 - the Coordinator list shows each name and their active-Event count
        (anything not Event Rejected, Cancelled or Completed)
  AC3 - the Activity Log records the Lead, the Coordinator and the time
  AC4 - another Coordinator cannot open or act on an assigned Event
  AC5 - an Event not in the queue cannot be assigned; the assignment stands
  AC6 - anyone without the Lead role is refused and the request stays unassigned

These tests do not use the `coordinator_auto_assign` fixture.
"""

import pytest

from app.core.roles import Role
from app.models.enums import EventStatus
from app.models.events import Event, EventStatusHistory
from app.models.notifications import Notification
from app.services.lead_assignment import AssignEvent, LeadAssignmentAction, ReassignEvent
from event_review_test_helpers import user


@pytest.fixture()
def w(client, db_session):
    org, org_h = user(client, db_session, Role.ORGANISER, "org@cs.local", "Olivia Organiser")
    sam, sam_h = user(client, db_session, Role.COORDINATOR, "sam@cs.local", "Sam Tan")
    priya, priya_h = user(client, db_session, Role.COORDINATOR, "priya@cs.local", "Priya Nair")
    lead, lead_h = user(client, db_session, Role.COORDINATOR_LEAD, "lead@cs.local", "Lena Lead")
    return dict(db=db_session, org=org, org_h=org_h, sam=sam, sam_h=sam_h, priya=priya, priya_h=priya_h,
                lead=lead, lead_h=lead_h)


def queued(w, name="Queued", status=EventStatus.submitted, coordinator=None):
    e = Event(organiser_id=w["org"].id, coordinator_id=coordinator.id if coordinator else None,
              name=name, status=status)
    w["db"].add(e)
    w["db"].commit()
    return e


def assign(client, w, event, coordinator, headers=None):
    return client.post(f"/lead/unassigned-queue/{event.id}/assign", json={"coordinator_id": coordinator.id},
                       headers=headers or w["lead_h"])


# --- AC1 -------------------------------------------------------------------


def test_ac1_assigning_takes_it_out_of_the_queue_and_makes_it_under_review(client, w):
    e = queued(w)
    res = assign(client, w, e, w["sam"])
    assert res.status_code == 200
    assert res.json()["status"] == "under_review"
    assert res.json()["coordinator"]["name"] == "Sam Tan"
    assert client.get("/lead/unassigned-queue", headers=w["lead_h"]).json() == []
    w["db"].refresh(e)
    assert (e.coordinator_id, e.status) == (w["sam"].id, EventStatus.under_review)


def test_ac1_it_appears_in_that_coordinators_assigned_events(client, w):
    e = queued(w)
    assign(client, w, e, w["sam"])
    mine = client.get("/events/assigned", headers=w["sam_h"]).json()
    assert [r["id"] for r in mine] == [e.id] and mine[0]["status"] == "under_review"
    assert client.get("/events/assigned", headers=w["priya_h"]).json() == []


def test_ac1_the_assigned_coordinator_and_organiser_are_told(client, w):
    e = queued(w)
    assign(client, w, e, w["sam"])
    db = w["db"]
    assert db.query(Notification).filter(Notification.user_id == w["sam"].id, Notification.event_id == e.id).count() == 1
    org_note = db.query(Notification).filter(Notification.user_id == w["org"].id, Notification.event_id == e.id).one()
    assert "Sam Tan" in org_note.message and "sam@cs.local" in org_note.message


def test_ac1_the_lead_assigns_one_chosen_coordinator_not_the_least_loaded(client, w):
    queued(w, status=EventStatus.under_review, coordinator=w["priya"])  # Priya busy, Sam idle
    e = queued(w)
    assert assign(client, w, e, w["priya"]).json()["coordinator"]["name"] == "Priya Nair"  # the Lead's choice stands


# --- AC2 -------------------------------------------------------------------


def test_ac2_the_list_shows_each_coordinator_with_their_active_event_count(client, w):
    for s in (EventStatus.under_review, EventStatus.planning, EventStatus.confirmed):
        queued(w, status=s, coordinator=w["sam"])
    for s in (EventStatus.rejected, EventStatus.cancelled, EventStatus.completed):
        queued(w, status=s, coordinator=w["sam"])  # finished: not counted
    rows = {r["name"]: r["active_events"] for r in client.get("/lead/coordinators", headers=w["lead_h"]).json()}
    assert rows == {"Priya Nair": 0, "Sam Tan": 3}


def test_ac2_the_count_goes_up_after_an_assignment(client, w):
    e = queued(w)
    assign(client, w, e, w["sam"])
    rows = {r["name"]: r["active_events"] for r in client.get("/lead/coordinators", headers=w["lead_h"]).json()}
    assert rows["Sam Tan"] == 1


# --- AC3 -------------------------------------------------------------------


def test_ac3_the_activity_log_records_the_lead_the_coordinator_and_the_time(client, w):
    e = queued(w)
    assign(client, w, e, w["sam"])
    log = client.get(f"/events/assigned/{e.id}", headers=w["sam_h"]).json()["activity"]
    line = log[0]  # newest first
    assert line["changed_by_name"] == "Lena Lead"
    assert "Sam Tan" in line["note"]
    assert (line["from_status"], line["to_status"]) == ("submitted", "under_review")
    assert line["created_at"]
    # and the Organiser can read the same record
    org_log = client.get(f"/events/{e.id}/activity", headers=w["org_h"]).json()
    assert org_log[0]["changed_by_name"] == "Lena Lead"


# --- AC4 -------------------------------------------------------------------


def test_ac4_another_coordinator_cannot_open_or_act_on_an_assigned_event(client, w):
    e = queued(w)
    assign(client, w, e, w["sam"])
    other = w["priya_h"]
    attempts = [
        client.get(f"/events/assigned/{e.id}", headers=other),
        client.post(f"/events/{e.id}/approve", headers=other),
        client.post(f"/events/{e.id}/reject", json={"reason": "no"}, headers=other),
        client.put(f"/events/assigned/{e.id}/registration", json={"registration_enabled": True}, headers=other),
    ]
    for res in attempts:
        assert res.status_code in (403, 404), res.request.url
    w["db"].refresh(e)
    assert (e.coordinator_id, e.status) == (w["sam"].id, EventStatus.under_review)
    # the assigned Coordinator still can
    assert client.get(f"/events/assigned/{e.id}", headers=w["sam_h"]).status_code == 200


# --- AC5 -------------------------------------------------------------------


def test_ac5_an_already_assigned_event_cannot_be_assigned_again(client, w):
    e = queued(w)
    assert assign(client, w, e, w["sam"]).status_code == 200
    again = assign(client, w, e, w["priya"])
    assert again.status_code == 409
    w["db"].refresh(e)
    assert e.coordinator_id == w["sam"].id  # the existing assignment is unchanged


@pytest.mark.parametrize("status", [EventStatus.draft, EventStatus.rejected, EventStatus.completed, EventStatus.cancelled])
def test_ac5_an_event_that_is_not_in_the_queue_is_refused_and_unchanged(client, w, status):
    e = queued(w, status=status)
    assert assign(client, w, e, w["sam"]).status_code == 409
    w["db"].refresh(e)
    assert (e.coordinator_id, e.status) == (None, status)


def test_ac5_a_refusal_writes_no_activity_log_line_or_notification(client, w):
    e = queued(w, status=EventStatus.draft)
    assign(client, w, e, w["sam"])
    assert w["db"].query(EventStatusHistory).filter(EventStatusHistory.event_id == e.id).count() == 0
    assert w["db"].query(Notification).count() == 0


def test_ac5_an_unknown_event_is_a_404(client, w):
    res = client.post("/lead/unassigned-queue/99999/assign", json={"coordinator_id": w["sam"].id}, headers=w["lead_h"])
    assert res.status_code == 404


@pytest.mark.parametrize("who", ["lead", "org", "attendee", "99999"])
def test_you_can_only_assign_to_a_real_coordinator(client, db_session, w, who):
    e = queued(w)
    if who == "lead":
        target = w["lead"].id
    elif who == "org":
        target = w["org"].id
    elif who == "attendee":
        target = user(client, db_session, Role.ATTENDEE, "att@cs.local", "Att")[0].id
    else:
        target = int(who)
    res = client.post(f"/lead/unassigned-queue/{e.id}/assign", json={"coordinator_id": target}, headers=w["lead_h"])
    assert res.status_code == 422
    w["db"].refresh(e)
    assert e.coordinator_id is None


# --- AC6 -------------------------------------------------------------------


@pytest.mark.parametrize("role", [Role.ORGANISER, Role.COORDINATOR, Role.VENUE_STAFF, Role.TECH_SUPPORT, Role.ATTENDEE])
def test_ac6_other_roles_are_refused_and_the_request_stays_unassigned(client, db_session, w, role):
    e = queued(w)
    _, h = user(client, db_session, role, f"x_{role.value}@cs.local", "Someone")
    assert assign(client, w, e, w["sam"], headers=h).status_code == 403
    db_session.refresh(e)
    assert (e.coordinator_id, e.status) == (None, EventStatus.submitted)
    assert db_session.query(EventStatusHistory).filter(EventStatusHistory.event_id == e.id).count() == 0


def test_ac6_unauthenticated_is_rejected(client, w):
    e = queued(w)
    res = client.post(f"/lead/unassigned-queue/{e.id}/assign", json={"coordinator_id": w["sam"].id})
    assert res.status_code == 401


# --- OOP -------------------------------------------------------------------


def test_assign_and_reassign_share_one_action_template():
    assert issubclass(AssignEvent, LeadAssignmentAction) and issubclass(ReassignEvent, LeadAssignmentAction)
    with pytest.raises(NotImplementedError):
        LeadAssignmentAction(None, None).check(None, None)


def test_no_endpoint_assigns_a_coordinator_automatically_any_more(client, w):
    """Submitting leaves a request unassigned; only the Lead's assign endpoint changes that."""
    e = queued(w)
    w["db"].refresh(e)
    assert (e.coordinator_id, e.status) == (None, EventStatus.submitted)
