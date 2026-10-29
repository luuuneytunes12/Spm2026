"""Tests for the Event Organiser's notifications about their own Events.

    AC1  My Event's status changes: I get a notification naming the Event
         and its new status.
    AC2  Someone else's Event changes status: I get nothing.
    AC3  A notification I received is there when I log in.
    AC4  One of my Event's Venue Bookings is approved or rejected: I get a
         notification naming the Event, that Venue and the decision -- and
         none for the Venues whose decision did not change.
    AC5  Technical Support confirm my Event's equipment or find it
         unavailable: I get a notification naming the Event, the equipment
         and the outcome.
    AC6  Another Organiser's Event: no status, Venue or equipment notice.
    AC7  My Event passes or fails its Safety Check: I am told.

Test names carry the acceptance criterion they prove.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.roles import Role
from app.models.enums import BookingStatus, EventStatus, NotificationType
from app.models.events import Event
from app.models.notifications import Notification
from app.services.organiser_notices import (
    EquipmentOutcomeNotice,
    EventStatusChangedNotice,
    OrganiserNotice,
    VenueBookingDecisionNotice,
)
from app.services.submission_notice import EventNotice
from tests.event_review_test_helpers import review_setup, submitted_event, user
from tests.test_equipment_requirement_fulfillment import _reserved, _update, _user, _world
from tests.test_safety_officer_notifications import _confirm, _ready
from tests.test_venue_booking_request import _submit_many, _venue

STATUS = NotificationType.event_status_changed.value
VENUE = NotificationType.venue_booking_decided.value
EQUIPMENT = NotificationType.equipment_outcome.value


def _inbox(client, headers, type=None):
    return [
        n["message"]
        for n in client.get("/notifications", headers=headers).json()
        if type is None or n["type"] == type
    ][::-1]  # oldest first


def _types(client, headers):
    return [n["type"] for n in client.get("/notifications", headers=headers).json()][::-1]


def _other_organiser(client, db_session):
    return user(client, db_session, Role.ORGANISER, "other.organiser@example.com", "Otto Other")


def _assigned(client, db_session, status=EventStatus.under_review):
    """An Event with its Organiser and Coordinator, in `status`. The setup's
    own notices are cleared so each test reads only what it caused."""
    organiser, org_h, coordinator, coord_h, event_id = review_setup(client, db_session)
    db_session.get(Event, event_id).status = status
    db_session.commit()
    db_session.query(Notification).delete()
    db_session.commit()
    return {"organiser": organiser, "org_h": org_h, "coord_h": coord_h, "event_id": event_id}


# --- AC1: my Event's status changes -> event and new status -----------------


def test_ac1_submitting_names_the_event_and_its_new_status(client, db_session):
    _, org_h = user(client, db_session, Role.ORGANISER, "organiser@example.com", "Organiser")
    submitted_event(client, org_h)

    assert _inbox(client, org_h, STATUS) == [
        "Your event 'Regional Partner Conference' is now Submitted – Awaiting Coordinator."
    ]


def test_ac1_cancelling_names_the_event_and_cancelled(client, db_session):
    w = _assigned(client, db_session, EventStatus.planning_event)

    res = client.post(f"/events/{w['event_id']}/cancel", json={"reason": "Budget cut"}, headers=w["coord_h"])

    assert res.status_code == 200, res.text
    assert _inbox(client, w["org_h"], STATUS) == [
        "Your event 'Regional Partner Conference' is now Event Cancelled."
    ]


def test_ac1_an_edit_that_reopens_a_confirmed_event_names_planning_event(client, db_session):
    w = _assigned(client, db_session, EventStatus.safety_check_passed)

    res = client.patch(
        f"/events/assigned/{w['event_id']}/planning",
        json={"proposed_start": "2026-11-03T09:00:00Z", "proposed_end": "2026-11-03T17:00:00Z"},
        headers=w["coord_h"],
    )

    assert res.status_code == 200, res.text
    assert _inbox(client, w["org_h"], STATUS) == [
        "Your event 'Regional Partner Conference' is now Planning Event."
    ]


def test_ac1_approval_is_told_once_not_twice(client, db_session):
    """The approval notice already names the new status; no second one."""
    w = _assigned(client, db_session)

    assert client.post(f"/events/{w['event_id']}/approve", headers=w["coord_h"]).status_code == 200

    assert _types(client, w["org_h"]) == [NotificationType.event_approved.value]


def test_ac1_rejection_is_told_once_not_twice(client, db_session):
    w = _assigned(client, db_session)

    res = client.post(f"/events/{w['event_id']}/reject", json={"reason": "Clashes"}, headers=w["coord_h"])

    assert res.status_code == 200, res.text
    assert _types(client, w["org_h"]) == [NotificationType.event_rejected.value]


def test_ac1_a_save_that_does_not_change_the_status_sends_no_status_notice(client, db_session):
    w = _assigned(client, db_session, EventStatus.planning_event)

    res = client.patch(
        f"/events/assigned/{w['event_id']}/planning", json={"description": "Longer."}, headers=w["coord_h"]
    )

    assert res.status_code == 200, res.text
    assert _inbox(client, w["org_h"], STATUS) == []


def test_ac1_a_status_that_moves_and_comes_back_in_one_save_is_not_news(client, db_session):
    w = _assigned(client, db_session, EventStatus.planning_event)
    event = db_session.get(Event, w["event_id"])
    event.status = EventStatus.awaiting_safety_check
    db_session.flush()
    event.status = EventStatus.planning_event
    db_session.commit()

    assert _inbox(client, w["org_h"], STATUS) == []


def test_ac1_a_change_that_rolls_back_tells_nobody(client, db_session):
    w = _assigned(client, db_session, EventStatus.planning_event)
    event = db_session.get(Event, w["event_id"])
    event.status = EventStatus.event_cancelled
    db_session.flush()
    db_session.rollback()

    db_session.get(Event, w["event_id"]).name = "Renamed"  # a later, unrelated save
    db_session.commit()

    assert _inbox(client, w["org_h"], STATUS) == []


def test_ac1_the_status_still_changes(client, db_session):
    """Frozen: cancelling still cancels; the notice adds to it, nothing else."""
    w = _assigned(client, db_session, EventStatus.planning_event)
    client.post(f"/events/{w['event_id']}/cancel", json={"reason": "Budget cut"}, headers=w["coord_h"])
    db_session.expire_all()
    assert db_session.get(Event, w["event_id"]).status == EventStatus.event_cancelled


# --- AC2 / AC6: not my Event -> nothing --------------------------------------


def test_ac2_another_organisers_status_change_is_not_sent_to_me(client, db_session):
    w = _assigned(client, db_session, EventStatus.planning_event)
    _, other_h = _other_organiser(client, db_session)

    client.post(f"/events/{w['event_id']}/cancel", json={"reason": "Budget cut"}, headers=w["coord_h"])

    assert len(_inbox(client, w["org_h"], STATUS)) == 1
    assert _inbox(client, other_h) == []


def test_ac2_only_the_organiser_gets_the_status_notice(client, db_session):
    w = _assigned(client, db_session, EventStatus.planning_event)

    client.post(f"/events/{w['event_id']}/cancel", json={"reason": "Budget cut"}, headers=w["coord_h"])

    db_session.expire_all()
    recipients = {n.user_id for n in db_session.query(Notification).filter_by(type=STATUS)}
    assert recipients == {w["organiser"].id}


# --- AC3: received -> there when I log in -----------------------------------


def test_ac3_the_notice_is_there_after_logging_in_again(client, db_session):
    w = _assigned(client, db_session, EventStatus.planning_event)
    client.post(f"/events/{w['event_id']}/cancel", json={"reason": "Budget cut"}, headers=w["coord_h"])

    login = client.post("/auth/login", json={"email": "organiser@example.com", "password": "password123"})
    assert login.status_code == 200, login.text
    fresh = {"Authorization": f"Bearer {login.json()['access_token']}"}

    [notice] = [n for n in client.get("/notifications", headers=fresh).json() if n["type"] == STATUS]
    assert notice["event_id"] == w["event_id"]
    assert notice["is_read"] is False


def test_ac3_signed_out_nothing_is_shown(client):
    assert client.get("/notifications").status_code == 401


# --- AC4: one Venue Booking decided -> that Venue and the decision ----------


def _two_bookings(client, db_session):
    w = _assigned(client, db_session, EventStatus.event_approved)
    _, staff_h = user(client, db_session, Role.VENUE_STAFF, "staff@example.com", "Vera Staff")
    marina, harbour = _venue(db_session, "Marina Hall"), _venue(db_session, "Harbour Room")
    res = _submit_many(
        client, w["coord_h"], w["event_id"], [{"venue_id": marina.id}, {"venue_id": harbour.id}]
    )
    assert res.status_code == 201, res.text
    by_venue = {b["venue"]["id"]: b["id"] for b in res.json()}
    db_session.query(Notification).delete()
    db_session.commit()
    return {**w, "staff_h": staff_h, "marina": by_venue[marina.id], "harbour": by_venue[harbour.id]}


def test_ac4_approving_one_booking_names_the_event_that_venue_and_approved(client, db_session):
    w = _two_bookings(client, db_session)

    assert client.post(f"/venue-bookings/{w['marina']}/approve", headers=w["staff_h"]).status_code == 200

    assert _inbox(client, w["org_h"], VENUE) == [
        "The venue booking of Marina Hall for 'Regional Partner Conference' was approved by Venue Staff."
    ]


def test_ac4_rejecting_one_booking_names_that_venue_rejected_and_why(client, db_session):
    w = _two_bookings(client, db_session)

    res = client.post(
        f"/venue-bookings/{w['harbour']}/reject",
        json={"reason": "Closed for works", "suggested_alternative": "Marina Hall"},
        headers=w["staff_h"],
    )

    assert res.status_code == 200, res.text
    assert _inbox(client, w["org_h"], VENUE) == [
        "The venue booking of Harbour Room for 'Regional Partner Conference' was rejected by Venue Staff. "
        "Reason: Closed for works Suggested alternative: Marina Hall"
    ]


def test_ac4_no_notice_for_the_venue_whose_decision_did_not_change(client, db_session):
    w = _two_bookings(client, db_session)

    client.post(f"/venue-bookings/{w['marina']}/approve", headers=w["staff_h"])

    [message] = _inbox(client, w["org_h"], VENUE)
    assert "Harbour Room" not in message


def test_ac4_each_decision_gets_its_own_notice(client, db_session):
    w = _two_bookings(client, db_session)

    client.post(f"/venue-bookings/{w['marina']}/approve", headers=w["staff_h"])
    client.post(f"/venue-bookings/{w['harbour']}/reject", json={"reason": "Full"}, headers=w["staff_h"])

    messages = _inbox(client, w["org_h"], VENUE)
    assert len(messages) == 2
    assert "Marina Hall" in messages[0] and "approved" in messages[0]
    assert "Harbour Room" in messages[1] and "rejected" in messages[1]


def test_ac4_a_tentative_hold_is_not_a_decision(client, db_session):
    w = _two_bookings(client, db_session)

    expires = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    res = client.post(
        f"/venue-bookings/{w['marina']}/hold",
        json={"expires_at": expires, "required_action": "Confirm the numbers"},
        headers=w["staff_h"],
    )

    assert res.status_code == 200, res.text
    assert _inbox(client, w["org_h"], VENUE) == []


def test_ac4_a_refused_decision_sends_nothing(client, db_session):
    w = _two_bookings(client, db_session)

    refused = client.post(f"/venue-bookings/{w['harbour']}/reject", json={}, headers=w["staff_h"])

    assert refused.status_code == 422
    assert _inbox(client, w["org_h"], VENUE) == []


def test_ac4_a_decided_booking_decided_again_sends_nothing_new(client, db_session):
    w = _two_bookings(client, db_session)
    client.post(f"/venue-bookings/{w['marina']}/approve", headers=w["staff_h"])

    again = client.post(f"/venue-bookings/{w['marina']}/approve", headers=w["staff_h"])

    assert again.status_code == 409
    assert len(_inbox(client, w["org_h"], VENUE)) == 1


def test_ac4_the_decision_is_still_recorded(client, db_session):
    """Frozen: approving still approves the booking."""
    w = _two_bookings(client, db_session)
    body = client.post(f"/venue-bookings/{w['marina']}/approve", headers=w["staff_h"]).json()
    assert body["status"] == BookingStatus.approved.value


# --- AC5: equipment confirmed or unavailable -> event, equipment, outcome ---


def test_ac5_fully_reserved_equipment_is_confirmed(client, db_session):
    w = _world(client, db_session, needed=1)

    _reserved(client, w.tech, w.rid, w.mic.id, 1)

    assert _inbox(client, w.organiser_headers, EQUIPMENT) == [
        "Equipment for 'Regional Partner Conference': 1 x Audio is confirmed by Technical Support."
    ]


def test_ac5_unavailable_equipment_names_the_outcome_and_reason(client, db_session):
    w = _world(client, db_session, needed=3)

    res = _update(client, w.tech, w.rid, status="unavailable", reason="All units out for repair")

    assert res.status_code == 200, res.text
    assert _inbox(client, w.organiser_headers, EQUIPMENT) == [
        "Equipment for 'Regional Partner Conference': 3 x Audio is unavailable by Technical Support. "
        "Reason: All units out for repair"
    ]


def test_ac5_a_partial_reservation_is_not_an_outcome_yet(client, db_session):
    w = _world(client, db_session, needed=5)

    _reserved(client, w.tech, w.rid, w.mic.id, 1)

    assert _inbox(client, w.organiser_headers, EQUIPMENT) == []


def test_ac5_the_last_part_reserved_confirms_it_once(client, db_session):
    w = _world(client, db_session, needed=2)

    _reserved(client, w.tech, w.rid, w.mic.id, 1)
    _reserved(client, w.tech, w.rid, w.pa.id, 1)

    assert len(_inbox(client, w.organiser_headers, EQUIPMENT)) == 1


def test_ac5_back_to_requested_is_not_an_outcome(client, db_session):
    w = _world(client, db_session, needed=3)
    _update(client, w.tech, w.rid, status="unavailable", reason="Out for repair")

    _update(client, w.tech, w.rid, status="requested")

    assert len(_inbox(client, w.organiser_headers, EQUIPMENT)) == 1


def test_ac5_unavailable_twice_is_told_once(client, db_session):
    w = _world(client, db_session, needed=3)

    _update(client, w.tech, w.rid, status="unavailable", reason="Out for repair")
    _update(client, w.tech, w.rid, status="unavailable", reason="Still out")

    assert len(_inbox(client, w.organiser_headers, EQUIPMENT)) == 1


def test_ac5_a_refused_update_sends_nothing(client, db_session):
    w = _world(client, db_session, needed=3)

    refused = _update(client, w.tech, w.rid, status="unavailable")  # no reason

    assert refused.status_code == 422
    assert _inbox(client, w.organiser_headers, EQUIPMENT) == []


# --- AC6: another Organiser's Event -> no Venue or equipment notice ---------


def test_ac6_another_organiser_gets_no_venue_decision(client, db_session):
    w = _two_bookings(client, db_session)
    _, other_h = _other_organiser(client, db_session)

    client.post(f"/venue-bookings/{w['marina']}/approve", headers=w["staff_h"])

    assert _inbox(client, other_h) == []


def test_ac6_another_organiser_gets_no_equipment_outcome(client, db_session):
    w = _world(client, db_session, needed=1)
    other, other_h = _user(client, db_session, Role.ORGANISER, name="Otto Other")

    _reserved(client, w.tech, w.rid, w.mic.id, 1)

    assert _inbox(client, other_h) == []
    db_session.expire_all()
    recipients = {n.user_id for n in db_session.query(Notification).filter_by(type=EQUIPMENT)}
    assert w.organiser.id in recipients and other.id not in recipients


# --- AC7: Safety Check passed or failed -> I am told ------------------------


def _awaiting_safety(client, db_session):
    w = _ready(client, db_session)
    assert _confirm(client, w).status_code == 200
    db_session.query(Notification).delete()
    db_session.commit()
    return w


def test_ac7_a_passed_safety_check_is_told_once(client, db_session):
    w = _awaiting_safety(client, db_session)

    res = client.post(f"/safety-checks/{w['event_id']}/approve", headers=w["officer_h"])

    assert res.status_code == 200, res.text
    assert _types(client, w["org_h"]) == [NotificationType.safety_check_passed.value]
    assert "passed its Safety Check" in _inbox(client, w["org_h"])[0]


def test_ac7_a_rejected_safety_check_is_told_once(client, db_session):
    w = _awaiting_safety(client, db_session)

    res = client.post(f"/safety-checks/{w['event_id']}/reject", json={"reason": "No fire exits"}, headers=w["officer_h"])

    assert res.status_code == 200, res.text
    assert _types(client, w["org_h"]) == [NotificationType.safety_check_rejected.value]
    assert "No fire exits" in _inbox(client, w["org_h"])[0]


def test_ac7_sending_for_safety_check_is_told(client, db_session):
    w = _ready(client, db_session)

    _confirm(client, w)

    assert _inbox(client, w["org_h"], STATUS) == [
        "Your event 'Regional Partner Conference' is now Awaiting Safety Check."
    ]


# --- the classes --------------------------------------------------------------


def test_organiser_notices_extend_the_base_notice_with_their_own_types():
    for cls in (EventStatusChangedNotice, VenueBookingDecisionNotice, EquipmentOutcomeNotice):
        assert issubclass(cls, OrganiserNotice) and issubclass(cls, EventNotice)
    assert len({EventStatusChangedNotice.type, VenueBookingDecisionNotice.type, EquipmentOutcomeNotice.type}) == 3


def test_a_booking_status_that_is_not_a_decision_is_refused():
    with pytest.raises(ValueError):
        VenueBookingDecisionNotice("Marina Hall", BookingStatus.tentative_hold)


def test_an_event_without_an_organiser_has_nobody_to_tell(db_session):
    assert OrganiserNotice().recipients(db_session, Event(organiser_id=None)) == []

