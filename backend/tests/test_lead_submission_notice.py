"""Backend tests for "Notify the Event Coordinator Lead of a submitted Event Request".

  AC1 - a complete request, once submitted, puts a Notification in the Lead's
        Notifications with the Event name, the Organiser and the submitted time
  AC2 - saving a draft sends the Lead nothing
  AC3 - a submit blocked for empty mandatory fields sends the Lead nothing

Plus the negative cases the DoD asks for: nobody but a Lead is told, a repeat
submit does not notify twice, and the existing submit result is unchanged.
"""

import pytest

from app.core.roles import Role
from app.models.enums import EventStatus, NotificationType
from app.models.events import Event
from app.models.notifications import Notification
from app.services.submission_notice import EventNotice, SubmissionNotice
from event_review_test_helpers import COMPLETE, user


@pytest.fixture()
def world(client, db_session):
    _, org = user(client, db_session, Role.ORGANISER, "org@cs.local", "Olivia Organiser")
    _, coord = user(client, db_session, Role.COORDINATOR, "coord@cs.local", "Sam Tan")
    _, lead = user(client, db_session, Role.COORDINATOR_LEAD, "lead@cs.local", "Lena Lead")
    _, attendee = user(client, db_session, Role.ATTENDEE, "att@cs.local", "Alex Attendee")
    return {"org": org, "coord": coord, "lead": lead, "attendee": attendee}


def _draft(client, headers, **over) -> int:
    return client.post("/events", json={**COMPLETE, **over}, headers=headers).json()["id"]


def _inbox(client, headers) -> list[dict]:
    return client.get("/notifications", headers=headers).json()


def _submitted_notices(client, headers) -> list[dict]:
    return [n for n in _inbox(client, headers) if n["type"] == "event_submitted"]


# --- AC1 -------------------------------------------------------------------


def test_ac1_submitting_a_complete_request_notifies_the_lead(client, world):
    event_id = _draft(client, world["org"], name="Partner Summit")
    assert client.post(f"/events/{event_id}/submit", headers=world["org"]).status_code == 200

    notices = _submitted_notices(client, world["lead"])
    assert len(notices) == 1
    assert notices[0]["event_id"] == event_id
    assert notices[0]["is_read"] is False


def test_ac1_notification_carries_event_name_organiser_and_submitted_time(client, db_session, world):
    event_id = _draft(client, world["org"], name="Partner Summit")
    client.post(f"/events/{event_id}/submit", headers=world["org"])

    message = _submitted_notices(client, world["lead"])[0]["message"]
    submitted_at = db_session.get(Event, event_id).submitted_at
    assert "Partner Summit" in message
    assert "Olivia Organiser" in message
    assert submitted_at.strftime("%d %b %Y, %H:%M") in message


def test_ac1_every_lead_is_notified(client, db_session, world):
    _, second_lead = user(client, db_session, Role.COORDINATOR_LEAD, "lead2@cs.local", "Lee Lead")
    event_id = _draft(client, world["org"])
    client.post(f"/events/{event_id}/submit", headers=world["org"])

    assert len(_submitted_notices(client, world["lead"])) == 1
    assert len(_submitted_notices(client, second_lead)) == 1


def test_ac1_each_submitted_request_gets_its_own_notification(client, world):
    first = _draft(client, world["org"], name="First")
    second = _draft(client, world["org"], name="Second")
    client.post(f"/events/{first}/submit", headers=world["org"])
    client.post(f"/events/{second}/submit", headers=world["org"])

    notices = _submitted_notices(client, world["lead"])
    assert sorted(n["event_id"] for n in notices) == [first, second]


def test_ac1_notifies_the_lead_even_when_auto_assign_is_switched_on(client, world, coordinator_auto_assign):
    event_id = _draft(client, world["org"])
    client.post(f"/events/{event_id}/submit", headers=world["org"])
    assert len(_submitted_notices(client, world["lead"])) == 1


# --- AC1 negative: only Leads are told --------------------------------------


@pytest.mark.parametrize("who", ["org", "coord", "attendee"])
def test_ac1_nobody_but_a_lead_gets_the_submission_notification(client, world, who):
    event_id = _draft(client, world["org"])
    client.post(f"/events/{event_id}/submit", headers=world["org"])
    assert _submitted_notices(client, world[who]) == []


def test_ac1_submit_succeeds_when_there_is_no_lead_to_tell(client, db_session):
    _, org = user(client, db_session, Role.ORGANISER, "solo@cs.local", "Solo Organiser")
    event_id = _draft(client, org)
    response = client.post(f"/events/{event_id}/submit", headers=org)
    assert response.status_code == 200
    assert db_session.query(Notification).filter_by(type="event_submitted").count() == 0


def test_ac1_a_repeat_submit_is_refused_and_does_not_notify_twice(client, world):
    event_id = _draft(client, world["org"])
    assert client.post(f"/events/{event_id}/submit", headers=world["org"]).status_code == 200
    assert client.post(f"/events/{event_id}/submit", headers=world["org"]).status_code == 409
    assert len(_submitted_notices(client, world["lead"])) == 1


def test_ac1_existing_submit_result_is_unchanged(client, db_session, world):
    event_id = _draft(client, world["org"])
    body = client.post(f"/events/{event_id}/submit", headers=world["org"]).json()
    assert body["status"] == "submitted_awaiting_coordinator"
    assert body["coordinator_id"] is None
    assert db_session.get(Event, event_id).status == EventStatus.submitted_awaiting_coordinator


# --- AC2 -------------------------------------------------------------------


def test_ac2_saving_a_draft_sends_the_lead_nothing(client, world):
    _draft(client, world["org"])
    assert _inbox(client, world["lead"]) == []


def test_ac2_editing_a_saved_draft_sends_the_lead_nothing(client, world):
    event_id = _draft(client, world["org"])
    client.patch(f"/events/{event_id}", json={"name": "Renamed draft"}, headers=world["org"])
    assert _inbox(client, world["lead"]) == []


def test_ac2_an_incomplete_draft_is_saved_without_notifying(client, world):
    created = client.post("/events", json={"name": "Half done"}, headers=world["org"])
    assert created.status_code == 201
    assert _inbox(client, world["lead"]) == []


# --- AC3 -------------------------------------------------------------------


def test_ac3_a_blocked_submit_sends_the_lead_nothing(client, world):
    event_id = _draft(client, world["org"], purpose="")
    response = client.post(f"/events/{event_id}/submit", headers=world["org"])
    assert response.status_code == 422
    assert _inbox(client, world["lead"]) == []


def test_ac3_a_blocked_submit_leaves_the_request_a_draft(client, db_session, world):
    event_id = _draft(client, world["org"], venue_requirements="   ")
    client.post(f"/events/{event_id}/submit", headers=world["org"])
    assert db_session.get(Event, event_id).status == EventStatus.draft


def test_ac3_fixing_the_fields_then_submitting_notifies_once(client, world):
    event_id = _draft(client, world["org"], purpose="")
    client.post(f"/events/{event_id}/submit", headers=world["org"])
    client.patch(f"/events/{event_id}", json={"purpose": "Now filled in"}, headers=world["org"])
    assert client.post(f"/events/{event_id}/submit", headers=world["org"]).status_code == 200
    assert len(_submitted_notices(client, world["lead"])) == 1


def test_ac3_someone_else_cannot_submit_and_the_lead_is_not_notified(client, db_session, world):
    _, other = user(client, db_session, Role.ORGANISER, "other@cs.local", "Other Organiser")
    event_id = _draft(client, world["org"])
    assert client.post(f"/events/{event_id}/submit", headers=other).status_code in (403, 404)
    assert _inbox(client, world["lead"]) == []


# --- OOP -------------------------------------------------------------------


def test_submission_notice_extends_the_base_notice_and_uses_its_own_type():
    assert issubclass(SubmissionNotice, EventNotice)
    assert SubmissionNotice.type == NotificationType.event_submitted == "event_submitted"


def test_base_notice_cannot_be_sent_without_recipients_and_a_message():
    with pytest.raises(NotImplementedError):
        EventNotice().recipients(None, None)
    with pytest.raises(NotImplementedError):
        EventNotice().message(None)
