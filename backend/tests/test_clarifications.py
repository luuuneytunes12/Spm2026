"""Backend tests for SCRUM-27 "Request Event Clarification" and SCRUM-103
"Respond to Clarification Request as Event Organiser".

SCRUM-27
  AC1 - assigned + Under Review: a text request is saved against the Event
  AC2 - saving it moves the Event to Awaiting Organiser Reply
  AC3 - the Organiser is notified and can read the full message
  AC4 - the activity log shows the Coordinator, the time and the message
  AC5 - an empty message is refused, status unchanged
  AC6 - not assigned to me / not Under Review: refused, Event unchanged
SCRUM-103
  AC1 - reply saved, visible to the Coordinator, status -> Under Review
  AC2 - the Coordinator is notified
  AC3 - the activity log records the reply with author and time
  AC4 - wrong status or not the Event's Organiser: refused, Event unchanged
  AC5 - an empty reply is refused, stays Awaiting Organiser Reply
  AC6 - amended fields are saved and the log shows what changed
"""

import pytest

from app.core.roles import Role
from app.models.clarifications import EventClarification
from app.models.enums import EventStatus
from app.models.events import Event
from app.models.notifications import Notification
from event_review_test_helpers import review_setup, user


@pytest.fixture()
def w(client, db_session):
    org, org_h, coord, coord_h, event_id = review_setup(client, db_session)
    return {"org": org, "org_h": org_h, "coord": coord, "coord_h": coord_h, "id": event_id, "db": db_session}


def _ask(client, w, message="What is the fire marshal plan?", headers=None):
    return client.post(f"/events/{w['id']}/clarifications", json={"message": message}, headers=headers or w["coord_h"])


def _reply(client, w, body=None, headers=None):
    return client.post(
        f"/events/{w['id']}/clarifications/reply",
        json=body or {"message": "Marshals are booked."},
        headers=headers or w["org_h"],
    )


def _event(w):
    w["db"].expire_all()
    return w["db"].get(Event, w["id"])


def _notes(w, user_id, type_):
    return w["db"].query(Notification).filter(Notification.user_id == user_id, Notification.type == type_).all()


def _log(client, w):
    return client.get(f"/events/{w['id']}/activity", headers=w["org_h"]).json()


def _awaiting(client, w):
    assert _ask(client, w).status_code == 201


# --- SCRUM-27 ---------------------------------------------------------------


def test_27_ac1_a_text_request_is_saved_against_the_event(client, w):
    res = _ask(client, w)
    assert res.status_code == 201
    body = res.json()
    assert body["kind"] == "request" and body["message"] == "What is the fire marshal plan?"
    assert body["event_id"] == w["id"] and body["author_name"] == "Coordinator"
    assert w["db"].query(EventClarification).filter_by(event_id=w["id"]).count() == 1


def test_27_ac2_status_becomes_awaiting_organiser_reply(client, w):
    _ask(client, w)
    assert _event(w).status == EventStatus.awaiting_organiser_reply


def test_27_ac3_the_organiser_is_notified_and_reads_the_full_message(client, w):
    long = "Please confirm " + "x" * 600
    _ask(client, w, long)
    assert len(_notes(w, w["org"].id, "clarification_requested")) == 1
    listed = client.get(f"/events/{w['id']}/clarifications", headers=w["org_h"])
    assert listed.status_code == 200 and listed.json()[0]["message"] == long


def test_27_ac4_the_activity_log_shows_coordinator_time_and_message(client, w):
    _ask(client, w)
    top = _log(client, w)[0]
    assert top["to_status"] == "awaiting_organiser_reply"
    assert top["changed_by_name"] == "Coordinator" and top["note"] == "What is the fire marshal plan?"
    assert top["created_at"]


@pytest.mark.parametrize("message", ["", "   ", "\n\t"])
def test_27_ac5_an_empty_message_is_refused_and_status_unchanged(client, w, message):
    res = _ask(client, w, message)
    assert res.status_code == 422
    assert _event(w).status == EventStatus.under_review
    assert w["db"].query(EventClarification).count() == 0
    assert _notes(w, w["org"].id, "clarification_requested") == []


def test_27_ac6_another_coordinator_is_refused_and_event_unchanged(client, w):
    _, other_h = user(client, w["db"], Role.COORDINATOR, "other@cs.local", "Other Coord")
    res = _ask(client, w, headers=other_h)
    assert res.status_code == 403
    assert _event(w).status == EventStatus.under_review
    assert w["db"].query(EventClarification).count() == 0


@pytest.mark.parametrize(
    "status", [EventStatus.event_approved, EventStatus.awaiting_organiser_reply, EventStatus.planning_event]
)
def test_27_ac6_not_under_review_is_refused_and_event_unchanged(client, w, status):
    e = _event(w)
    e.status = status
    w["db"].commit()
    assert _ask(client, w).status_code == 409
    assert _event(w).status == status
    assert w["db"].query(EventClarification).count() == 0


@pytest.mark.parametrize("role", [Role.ORGANISER, Role.VENUE_STAFF, Role.ATTENDEE, Role.COORDINATOR_LEAD])
def test_27_wrong_role_is_denied(client, w, role):
    _, h = user(client, w["db"], role, f"{role.value}@cs.local", "Someone")
    assert _ask(client, w, headers=h).status_code == 403
    assert _event(w).status == EventStatus.under_review


def test_27_unknown_event_is_404_and_anonymous_is_401(client, w):
    assert client.post("/events/99999/clarifications", json={"message": "hi"}, headers=w["coord_h"]).status_code == 404
    assert client.post(f"/events/{w['id']}/clarifications", json={"message": "hi"}).status_code == 401


def test_27_a_repeated_request_is_refused_because_it_is_no_longer_under_review(client, w):
    assert _ask(client, w).status_code == 201
    assert _ask(client, w, "again").status_code == 409
    assert w["db"].query(EventClarification).count() == 1
    assert len(_notes(w, w["org"].id, "clarification_requested")) == 1


# --- SCRUM-103 --------------------------------------------------------------


def test_103_ac1_reply_saved_visible_to_coordinator_status_under_review(client, w):
    _awaiting(client, w)
    res = _reply(client, w)
    assert res.status_code == 201 and res.json()["kind"] == "reply"
    assert _event(w).status == EventStatus.under_review
    seen = client.get(f"/events/{w['id']}/clarifications", headers=w["coord_h"]).json()
    assert [m["kind"] for m in seen] == ["request", "reply"]
    assert seen[1]["message"] == "Marshals are booked." and seen[1]["author_name"] == "Organiser"


def test_103_ac2_the_coordinator_is_notified(client, w):
    _awaiting(client, w)
    _reply(client, w)
    assert len(_notes(w, w["coord"].id, "clarification_replied")) == 1
    assert _notes(w, w["org"].id, "clarification_replied") == []


def test_103_ac3_the_activity_log_records_the_reply_with_author_and_time(client, w):
    _awaiting(client, w)
    _reply(client, w)
    top = _log(client, w)[0]
    assert top["from_status"] == "awaiting_organiser_reply" and top["to_status"] == "under_review"
    assert top["changed_by_name"] == "Organiser" and top["note"] == "Marshals are booked." and top["created_at"]


def test_103_ac4_wrong_status_is_refused_and_event_unchanged(client, w):
    res = _reply(client, w)  # still Under Review
    assert res.status_code == 409
    assert _event(w).status == EventStatus.under_review
    assert w["db"].query(EventClarification).count() == 0


def test_103_ac4_another_organiser_is_refused_and_event_unchanged(client, w):
    _awaiting(client, w)
    _, other_h = user(client, w["db"], Role.ORGANISER, "other-org@cs.local", "Other Organiser")
    assert _reply(client, w, headers=other_h).status_code == 404
    assert client.get(f"/events/{w['id']}/clarifications", headers=other_h).status_code == 404
    assert _event(w).status == EventStatus.awaiting_organiser_reply
    assert w["db"].query(EventClarification).filter_by(kind="reply").count() == 0
    assert _notes(w, w["coord"].id, "clarification_replied") == []


@pytest.mark.parametrize("headers_key", ["coord_h"])
def test_103_ac4_the_coordinator_cannot_reply_for_the_organiser(client, w, headers_key):
    _awaiting(client, w)
    assert _reply(client, w, headers=w[headers_key]).status_code == 403
    assert _event(w).status == EventStatus.awaiting_organiser_reply


@pytest.mark.parametrize("message", ["", "   "])
def test_103_ac5_an_empty_reply_is_refused_and_stays_awaiting(client, w, message):
    _awaiting(client, w)
    assert _reply(client, w, {"message": message}).status_code == 422
    assert _event(w).status == EventStatus.awaiting_organiser_reply
    assert w["db"].query(EventClarification).filter_by(kind="reply").count() == 0


def test_103_ac6_amended_fields_are_saved_and_the_log_shows_what_changed(client, w):
    _awaiting(client, w)
    before = _event(w).expected_attendance
    res = _reply(client, w, {"message": "Updated numbers.", "updates": {"expected_attendance": 250, "venue_requirements": "Hall B"}})
    assert res.status_code == 201
    e = _event(w)
    assert e.expected_attendance == 250 and e.venue_requirements == "Hall B"
    assert e.status == EventStatus.under_review
    note = _log(client, w)[0]["note"]
    assert note.startswith("Updated numbers.")
    assert f"expected_attendance: {before} -> 250" in note and "venue_requirements: Main hall -> Hall B" in note


def test_103_ac6_invalid_amendments_are_refused_and_nothing_is_written(client, w):
    _awaiting(client, w)
    before = _event(w).expected_attendance
    res = _reply(client, w, {"message": "Updated.", "updates": {"expected_attendance": -5}})
    assert res.status_code == 422
    assert _event(w).expected_attendance == before
    assert _event(w).status == EventStatus.awaiting_organiser_reply
    assert w["db"].query(EventClarification).filter_by(kind="reply").count() == 0


def test_103_a_repeated_reply_is_refused_and_does_not_double_notify(client, w):
    _awaiting(client, w)
    assert _reply(client, w).status_code == 201
    assert _reply(client, w, {"message": "again"}).status_code == 409
    assert w["db"].query(EventClarification).filter_by(kind="reply").count() == 1
    assert len(_notes(w, w["coord"].id, "clarification_replied")) == 1


def test_no_notification_or_exchange_reaches_outsiders(client, w):
    _awaiting(client, w)
    _reply(client, w)
    out, out_h = user(client, w["db"], Role.VENUE_STAFF, "outsider@cs.local", "Outsider")
    assert w["db"].query(Notification).filter(Notification.user_id == out.id).count() == 0
    assert client.get(f"/events/{w['id']}/clarifications", headers=out_h).status_code == 404
