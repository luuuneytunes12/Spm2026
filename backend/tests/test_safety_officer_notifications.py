"""Tests for the Safety Officer's notifications about their queue.

    AC1  An Event submitted or resubmitted for Safety Check: the Safety
         Officer is notified with its name, date and Event Coordinator.
    AC2  An Event in 'Awaiting Safety Check' that returns to 'Planning Event'
         because its arrangements changed: the Safety Officer is told it has
         left their queue, and why.

Test names carry the acceptance criterion they prove.
"""

import pytest

from app.core.roles import Role
from app.models.enums import EventStatus, NotificationType
from app.models.equipment import Equipment, EquipmentRequest
from app.models.events import Event, EventStatusHistory
from app.models.notifications import Notification
from app.models.venues import VenueBooking
from app.services.safety_notices import (
    SafetyCheckRequestedNotice,
    SafetyCheckWithdrawnNotice,
    SafetyOfficerNotice,
)
from app.services.submission_notice import EventNotice
from tests.event_review_test_helpers import submitted_event, user
from tests.test_safety_checks import _setup
from tests.test_venue_booking_request import _submit, _venue

REQUESTED = NotificationType.safety_check_requested.value
WITHDRAWN = NotificationType.safety_check_withdrawn.value


def _ready(client, db_session):
    """An event whose venue is approved and equipment reserved, not yet
    submitted -- the same arrangement as test_safety_checks._setup."""
    _, org_h = user(client, db_session, Role.ORGANISER, "organiser@example.com", "Olivia Organiser")
    coordinator, coord_h = user(client, db_session, Role.COORDINATOR, "coordinator@example.com", "Casey Coordinator")
    event_id = submitted_event(client, org_h)
    event = db_session.get(Event, event_id)
    event.coordinator_id = coordinator.id
    event.status = EventStatus.event_approved
    projector = Equipment(name="Projector", category="Projection", total_quantity=10)
    db_session.add(projector)
    db_session.flush()
    db_session.add(EquipmentRequest(event_id=event_id, equipment_id=projector.id, quantity_requested=2))
    db_session.commit()

    _, staff_h = user(client, db_session, Role.VENUE_STAFF, "staff@example.com", "Vera Staff")
    _, tech_h = user(client, db_session, Role.TECH_SUPPORT, "tech@example.com", "Tess Tech")
    officer, officer_h = user(client, db_session, Role.SAFETY_OFFICER, "safety@example.com", "Sam Safety")

    booking_id = _submit(client, coord_h, event_id, _venue(db_session).id).json()["id"]
    assert client.post(f"/venue-bookings/{booking_id}/approve", headers=staff_h).status_code == 200
    assert client.post(
        "/equipment-reservations",
        json={"event_id": event_id, "equipment_id": projector.id},
        headers=tech_h,
    ).status_code == 200
    db_session.query(Notification).delete()
    db_session.commit()
    return {
        "event_id": event_id,
        "org_h": org_h,
        "coord_h": coord_h,
        "staff_h": staff_h,
        "tech_h": tech_h,
        "officer": officer,
        "officer_h": officer_h,
    }


def _confirm(client, w):
    return client.post(f"/events/{w['event_id']}/confirm", headers=w["coord_h"])


def _notices(db_session):
    return db_session.query(Notification).filter_by(type=REQUESTED).order_by(Notification.id).all()


def _inbox(client, headers):
    return [n for n in client.get("/notifications", headers=headers).json() if n["type"] == REQUESTED]


def _status(db_session, event_id):
    db_session.expire_all()
    return db_session.get(Event, event_id).status


# --- AC1: submitted -> name, date and Coordinator ---------------------------


def test_ac1_submitting_notifies_the_safety_officer_with_name_date_and_coordinator(client, db_session):
    w = _ready(client, db_session)
    assert _confirm(client, w).status_code == 200

    [notice] = _inbox(client, w["officer_h"])
    assert notice["event_id"] == w["event_id"]
    assert notice["message"] == (
        "'Regional Partner Conference' on 2 Nov 2026 (Event Coordinator: Casey Coordinator) "
        "was submitted for a Safety Check."
    )
    assert _status(db_session, w["event_id"]) == EventStatus.awaiting_safety_check


def test_ac1_every_safety_officer_is_notified(client, db_session):
    w = _ready(client, db_session)
    _, second_h = user(client, db_session, Role.SAFETY_OFFICER, "safety2@example.com", "Sid Safety")
    _confirm(client, w)

    assert len(_inbox(client, w["officer_h"])) == 1
    assert len(_inbox(client, second_h)) == 1


def test_ac1_the_notification_reaches_the_safety_officer_live(client, db_session, monkeypatch):
    from app.services import notifications

    pushed = []
    monkeypatch.setattr(notifications.broker, "publish", lambda uid, payload: pushed.append((uid, payload)))
    w = _ready(client, db_session)
    _confirm(client, w)

    assert [(uid, p["type"]) for uid, p in pushed] == [(w["officer"].id, REQUESTED)]


# --- AC1: resubmitted -------------------------------------------------------


@pytest.mark.parametrize("decision", ["request-changes", "reject"])
def test_ac1_resubmitting_after_being_sent_back_says_resubmitted(client, db_session, decision):
    s = _setup(client, db_session)
    body = {"reason": "Move the projector"}
    if decision == "request-changes":
        body["equipment_request_ids"] = [s["line_id"]]
    assert client.post(
        f"/safety-checks/{s['event_id']}/{decision}", json=body, headers=s["officer_h"]
    ).status_code == 200
    # Staff clear what the officer flagged, then the Coordinator resubmits.
    assert client.post(
        f"/equipment-reservations/{s['line_id']}/safety-recheck/confirm", json={}, headers=s["tech_h"]
    ).status_code == 200
    if decision == "reject":
        _, staff_h = user(client, db_session, Role.VENUE_STAFF, "staff2@example.com", "Second Staff")
        for booking_id in (s["booking_id"], s["second_booking_id"]):
            assert (
                client.post(f"/venue-bookings/{booking_id}/approve", headers=staff_h).status_code
                == 200
            )

    assert client.post(f"/events/{s['event_id']}/confirm", headers=s["coord_h"]).status_code == 200

    [notice] = _inbox(client, s["officer_h"])
    assert notice["message"] == (
        "'Regional Partner Conference' on 2 Nov 2026 (Event Coordinator: Coordinator) "
        "was resubmitted for a Safety Check."
    )


# --- AC1 negative and edge cases -------------------------------------------


@pytest.mark.parametrize("who", ["org_h", "coord_h", "staff_h", "tech_h"])
def test_ac1_nobody_but_a_safety_officer_gets_the_notification(client, db_session, who):
    w = _ready(client, db_session)
    _confirm(client, w)
    assert _inbox(client, w[who]) == []


def test_ac1_only_safety_officers_are_recipients(client, db_session):
    w = _ready(client, db_session)
    _confirm(client, w)
    assert {n.user_id for n in _notices(db_session)} == {w["officer"].id}


def test_ac1_a_blocked_submit_notifies_nobody_and_leaves_the_event_in_planning(client, db_session):
    w = _ready(client, db_session)
    # A requirement Technical Support has not reserved yet blocks the submit.
    assert client.post(
        f"/equipment-requirements/events/{w['event_id']}",
        json={"category": "Projection", "quantity_needed": 2},
        headers=w["coord_h"],
    ).status_code == 201

    assert _confirm(client, w).status_code == 409
    assert _notices(db_session) == []
    assert _status(db_session, w["event_id"]) == EventStatus.planning_event


def test_ac1_a_repeat_submit_is_refused_and_notifies_once(client, db_session):
    w = _ready(client, db_session)
    assert _confirm(client, w).status_code == 200
    assert _confirm(client, w).status_code == 409
    assert len(_notices(db_session)) == 1


def test_ac1_another_coordinator_cannot_submit_and_nobody_is_notified(client, db_session):
    w = _ready(client, db_session)
    _, other_h = user(client, db_session, Role.COORDINATOR, "coord2@example.com", "Other Coordinator")
    assert client.post(f"/events/{w['event_id']}/confirm", headers=other_h).status_code == 404
    assert _notices(db_session) == []


def test_ac1_submit_succeeds_when_there_is_no_safety_officer(client, db_session):
    w = _ready(client, db_session)
    db_session.delete(w["officer"])
    db_session.commit()
    assert _confirm(client, w).status_code == 200
    assert _notices(db_session) == []


def test_ac1_safety_officer_decisions_do_not_notify_the_officer(client, db_session):
    """Frozen: the officer's own decisions still go to the Organiser,
    Coordinator and staff only."""
    s = _setup(client, db_session)
    client.post(f"/safety-checks/{s['event_id']}/approve", headers=s["officer_h"])
    assert db_session.query(Notification).filter_by(user_id=s["officer"].id).count() == 0


# --- AC2: back to planning -> told it left the queue, and why ---------------


def _change_attendance(client, w, attendance=400, approve=True):
    """The Organiser asks to change the attendance; the Coordinator decides."""
    requested = client.post(
        f"/events/{w['event_id']}/change-requests",
        json={"description": "More guests", "proposed_changes": {"expected_attendance": attendance}},
        headers=w["org_h"],
    )
    assert requested.status_code == 201, requested.text
    decision = "approve" if approve else "reject"
    body = {} if approve else {"review_notes": "Not now."}
    res = client.post(
        f"/events/change-requests/{requested.json()['id']}/{decision}", json=body, headers=w["coord_h"]
    )
    assert res.status_code == 200, res.text


def _withdrawn(client, headers):
    return [n for n in client.get("/notifications", headers=headers).json() if n["type"] == WITHDRAWN]


def _awaiting(client, db_session):
    w = _ready(client, db_session)
    assert _confirm(client, w).status_code == 200
    db_session.query(Notification).delete()
    db_session.commit()
    return w


def test_ac2_leaving_the_queue_tells_the_safety_officer_which_event_and_why(client, db_session):
    w = _awaiting(client, db_session)

    _change_attendance(client, w, attendance=400)

    assert _status(db_session, w["event_id"]) == EventStatus.planning_event
    [notice] = _withdrawn(client, w["officer_h"])
    assert notice["event_id"] == w["event_id"]
    assert notice["message"] == (
        "'Regional Partner Conference' on 2 Nov 2026 (Event Coordinator: Casey Coordinator) "
        "has left your Safety Check queue and is back in planning: its expected attendance "
        "changed from 120 to 400, so its venue and safety arrangements must be reviewed again. "
        "Do not review it until it is submitted again."
    )


def test_ac2_a_new_date_and_time_also_takes_it_out_of_the_queue_and_says_so(client, db_session):
    w = _awaiting(client, db_session)
    requested = client.post(
        f"/events/{w['event_id']}/change-requests",
        json={
            "description": "Moved",
            "proposed_changes": {"proposed_start": "2026-11-09T09:00:00Z", "proposed_end": "2026-11-09T17:00:00Z"},
        },
        headers=w["org_h"],
    )
    assert requested.status_code == 201, requested.text
    approved = client.post(
        f"/events/change-requests/{requested.json()['id']}/approve", json={}, headers=w["coord_h"]
    )
    assert approved.status_code == 200, approved.text

    assert _status(db_session, w["event_id"]) == EventStatus.planning_event
    [notice] = _withdrawn(client, w["officer_h"])
    assert "has left your Safety Check queue" in notice["message"]
    assert "its date and time changed, so its venue and safety arrangements must be reviewed again." in notice["message"]


def test_ac2_every_safety_officer_is_told(client, db_session):
    w = _awaiting(client, db_session)
    _, second_h = user(client, db_session, Role.SAFETY_OFFICER, "safety2@example.com", "Sid Safety")
    _change_attendance(client, w)
    assert len(_withdrawn(client, w["officer_h"])) == len(_withdrawn(client, second_h)) == 1


def test_ac2_the_event_is_no_longer_in_the_queue(client, db_session):
    w = _awaiting(client, db_session)
    assert [e["id"] for e in client.get("/safety-checks", headers=w["officer_h"]).json()] == [w["event_id"]]
    _change_attendance(client, w)
    assert client.get("/safety-checks", headers=w["officer_h"]).json() == []


@pytest.mark.parametrize("who", ["org_h", "coord_h", "staff_h", "tech_h"])
def test_ac2_negative_nobody_but_a_safety_officer_is_told_it_left_the_queue(client, db_session, who):
    w = _awaiting(client, db_session)
    _change_attendance(client, w)
    assert _withdrawn(client, w[who]) == []


@pytest.mark.parametrize("start", [EventStatus.event_approved, EventStatus.planning_event, EventStatus.safety_check_passed])
def test_ac2_negative_an_event_not_in_the_queue_tells_the_safety_officer_nothing(client, db_session, start):
    """Frozen: the same attendance change outside the queue still moves the
    event to planning, but there is no queue for it to leave."""
    w = _ready(client, db_session)
    db_session.get(Event, w["event_id"]).status = start
    db_session.commit()
    _change_attendance(client, w)
    assert _status(db_session, w["event_id"]) == EventStatus.planning_event
    assert db_session.query(Notification).filter_by(type=WITHDRAWN).count() == 0


def test_ac2_negative_a_rejected_change_keeps_it_in_the_queue_and_tells_nobody(client, db_session):
    w = _awaiting(client, db_session)
    _change_attendance(client, w, approve=False)
    assert _status(db_session, w["event_id"]) == EventStatus.awaiting_safety_check
    assert db_session.query(Notification).filter_by(type=WITHDRAWN).count() == 0


def test_ac2_a_change_that_is_not_the_attendance_keeps_it_in_the_queue(client, db_session):
    w = _awaiting(client, db_session)
    requested = client.post(
        f"/events/{w['event_id']}/change-requests",
        json={"description": "Typo", "proposed_changes": {"name": "Regional Partner Summit"}},
        headers=w["org_h"],
    ).json()
    client.post(f"/events/change-requests/{requested['id']}/approve", json={}, headers=w["coord_h"])
    assert _status(db_session, w["event_id"]) == EventStatus.awaiting_safety_check
    assert db_session.query(Notification).filter_by(type=WITHDRAWN).count() == 0


def test_ac2_the_move_back_to_planning_is_in_the_activity_log(client, db_session):
    w = _awaiting(client, db_session)
    _change_attendance(client, w)
    db_session.expire_all()
    entry = (
        db_session.query(EventStatusHistory)
        .filter_by(
            event_id=w["event_id"],
            from_status=EventStatus.awaiting_safety_check,
            to_status=EventStatus.planning_event,
        )
        .one()
    )
    assert "new safety check is required" in entry.note


def test_ac2_resubmitting_after_leaving_the_queue_says_resubmitted(client, db_session):
    """It left the queue, the Coordinator re-arranges, and submits again."""
    w = _awaiting(client, db_session)
    _change_attendance(client, w, attendance=200)  # still fits the 250-seat venue
    # The change reopened the venue booking for review; Venue Staff approve it again.
    booking = db_session.query(VenueBooking).filter_by(event_id=w["event_id"]).one()
    assert client.post(f"/venue-bookings/{booking.id}/approve", headers=w["staff_h"]).status_code == 200
    assert _confirm(client, w).status_code == 200
    [notice] = _inbox(client, w["officer_h"])
    assert notice["message"].endswith("was resubmitted for a Safety Check.")


# --- OOP -------------------------------------------------------------------


def test_safety_officer_notice_extends_the_base_notice_with_its_own_type():
    assert issubclass(SafetyOfficerNotice, EventNotice)
    assert issubclass(SafetyCheckRequestedNotice, SafetyOfficerNotice)
    assert SafetyCheckRequestedNotice.type == "safety_check_requested"
    assert issubclass(SafetyCheckWithdrawnNotice, SafetyOfficerNotice)
    assert SafetyCheckWithdrawnNotice.type == "safety_check_withdrawn"
