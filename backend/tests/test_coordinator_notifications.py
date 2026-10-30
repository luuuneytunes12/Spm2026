"""Tests for the Event Coordinator's notifications about their Events.

    AC1  The Lead assigns or reassigns an Event Request to me: I get a
         notification with the Event name and the Event Organiser.
    AC2  An Event of mine is reassigned to someone else: I am told it moved.
    AC3  The Organiser replies to my clarification request: I am told.
    AC4  Venue Staff approve or reject a Venue Booking of my Event: I get a
         notification naming the Venue and the decision, with the reason or
         alternative if one was given.
    AC5  Several Venue Bookings, one decided: one notification, for that one.
    AC6  A Change Request is submitted on my Event: I am told.
    AC7  Not my Event, or reassigned away from me: no Venue, equipment or
         Change Request notification.
    AC8  Technical Support reserve my Event's equipment in full or mark it
         unavailable: I get a notification naming the Event and the equipment.

Test names carry the acceptance criterion they prove.
"""

import pytest

from app.core.roles import Role
from app.models.enums import EventStatus, NotificationType
from app.models.events import Event
from app.models.notifications import Notification
from app.services.coordinator_notices import (
    ChangeRequestSubmittedNotice,
    CoordinatorEquipmentOutcomeNotice,
    CoordinatorNotice,
    CoordinatorVenueDecisionNotice,
)
from app.services.organiser_notices import EquipmentOutcomeNotice, VenueBookingDecisionNotice
from app.services.submission_notice import EventNotice
from tests.event_review_test_helpers import review_setup, user
from tests.test_equipment_requirement_fulfillment import _reserved, _update, _user, _world
from tests.test_lead_reassign_event import assigned_event, reassign, w  # noqa: F401  (fixture)
from tests.test_venue_booking_request import _submit_many, _venue

ASSIGNED = NotificationType.event_assigned.value
MOVED = NotificationType.event_reassigned_away.value
REPLIED = NotificationType.clarification_replied.value
VENUE = NotificationType.venue_booking_decided.value
EQUIPMENT = NotificationType.equipment_outcome.value
CHANGE = NotificationType.change_request_submitted.value


def _inbox(client, headers, type):
    """`type` notifications, oldest first."""
    return [n["message"] for n in client.get("/notifications", headers=headers).json() if n["type"] == type][::-1]


def _event_with(client, db_session, status):
    """An Event in `status` with its Organiser and Coordinator; the setup's
    own notices are cleared so each test reads only what it caused."""
    organiser, org_h, coordinator, coord_h, event_id = review_setup(client, db_session)
    db_session.get(Event, event_id).status = status
    db_session.commit()
    db_session.query(Notification).delete()
    db_session.commit()
    return {"organiser": organiser, "org_h": org_h, "coordinator": coordinator, "coord_h": coord_h, "event_id": event_id}


def _move_to(db_session, event_id, coordinator):
    db_session.get(Event, event_id).coordinator_id = coordinator.id
    db_session.commit()


# --- AC1: assigned or reassigned to me -> Event name and Organiser ---------


def test_ac1_an_assignment_names_the_event_and_the_organiser(client, w):
    assigned_event(client, w, w["sam"])

    assert _inbox(client, w["sam_h"], ASSIGNED) == [
        "You have been assigned to coordinate 'Regional Partner Conference' "
        "for Olivia Organiser (Event Organiser)."
    ]


def test_ac1_a_reassignment_names_the_event_and_the_organiser_to_the_new_coordinator(client, w):
    event_id = assigned_event(client, w, w["sam"])

    assert reassign(client, w, event_id, w["priya"]).status_code == 200

    assert _inbox(client, w["priya_h"], ASSIGNED) == [
        "You have been assigned to coordinate 'Regional Partner Conference' "
        "for Olivia Organiser (Event Organiser)."
    ]


def test_ac1_only_the_assigned_coordinator_is_told(client, w):
    assigned_event(client, w, w["sam"])

    assert _inbox(client, w["priya_h"], ASSIGNED) == []


def test_ac1_a_refused_assignment_tells_nobody(client, w):
    event_id = assigned_event(client, w, w["sam"])

    refused = reassign(client, w, event_id, w["sam"])  # already theirs

    assert refused.status_code == 409
    assert len(_inbox(client, w["sam_h"], ASSIGNED)) == 1


# --- AC2: reassigned away -> told it has moved -----------------------------


def test_ac2_the_previous_coordinator_is_told_it_has_moved(client, w):
    event_id = assigned_event(client, w, w["sam"])

    reassign(client, w, event_id, w["priya"])

    assert _inbox(client, w["sam_h"], MOVED) == [
        "Priya Nair has taken over coordinating 'Regional Partner Conference' (previously assigned to you)."
    ]
    assert _inbox(client, w["priya_h"], MOVED) == []


# --- AC3: the Organiser replies to a clarification -> told -----------------


def test_ac3_the_organisers_reply_reaches_the_coordinator(client, db_session):
    e = _event_with(client, db_session, EventStatus.under_review)
    asked = client.post(f"/events/{e['event_id']}/clarifications", json={"message": "Fire plan?"}, headers=e["coord_h"])
    assert asked.status_code == 201, asked.text

    replied = client.post(
        f"/events/{e['event_id']}/clarifications/reply", json={"message": "Marshals booked."}, headers=e["org_h"]
    )

    assert replied.status_code == 201, replied.text
    assert _inbox(client, e["coord_h"], REPLIED) == [
        "Organiser replied to your clarification request on 'Regional Partner Conference'."
    ]


# --- AC4 / AC5: one Venue Booking decided -> that Venue, decision, reason --


def _two_bookings(client, db_session):
    e = _event_with(client, db_session, EventStatus.event_approved)
    _, staff_h = user(client, db_session, Role.VENUE_STAFF, "staff@example.com", "Vera Staff")
    marina, harbour = _venue(db_session, "Marina Hall"), _venue(db_session, "Harbour Room")
    res = _submit_many(client, e["coord_h"], e["event_id"], [{"venue_id": marina.id}, {"venue_id": harbour.id}])
    assert res.status_code == 201, res.text
    by_venue = {b["venue"]["id"]: b["id"] for b in res.json()}
    db_session.query(Notification).delete()
    db_session.commit()
    return {**e, "staff_h": staff_h, "marina": by_venue[marina.id], "harbour": by_venue[harbour.id]}


def test_ac4_an_approval_names_the_venue_and_approved(client, db_session):
    e = _two_bookings(client, db_session)

    assert client.post(f"/venue-bookings/{e['marina']}/approve", headers=e["staff_h"]).status_code == 200

    assert _inbox(client, e["coord_h"], VENUE) == [
        "The venue booking of Marina Hall for 'Regional Partner Conference' was approved by Venue Staff."
    ]


def test_ac4_a_rejection_names_the_venue_rejected_the_reason_and_the_alternative(client, db_session):
    e = _two_bookings(client, db_session)

    res = client.post(
        f"/venue-bookings/{e['harbour']}/reject",
        json={"reason": "Closed for works", "suggested_alternative": "Marina Hall"},
        headers=e["staff_h"],
    )

    assert res.status_code == 200, res.text
    assert _inbox(client, e["coord_h"], VENUE) == [
        "The venue booking of Harbour Room for 'Regional Partner Conference' was rejected by Venue Staff. "
        "Reason: Closed for works Suggested alternative: Marina Hall"
    ]


@pytest.mark.parametrize(
    "body, shown, hidden",
    [
        ({"reason": "Closed for works"}, "Reason: Closed for works", "Suggested alternative"),
        ({"suggested_alternative": "Marina Hall"}, "Suggested alternative: Marina Hall", "Reason:"),
    ],
)
def test_ac4_a_rejection_shows_whichever_was_given(client, db_session, body, shown, hidden):
    e = _two_bookings(client, db_session)

    client.post(f"/venue-bookings/{e['harbour']}/reject", json=body, headers=e["staff_h"])

    [message] = _inbox(client, e["coord_h"], VENUE)
    assert shown in message and hidden not in message


def test_ac5_one_booking_decided_gives_one_notice_for_that_booking_only(client, db_session):
    e = _two_bookings(client, db_session)

    client.post(f"/venue-bookings/{e['marina']}/approve", headers=e["staff_h"])

    [message] = _inbox(client, e["coord_h"], VENUE)
    assert "Marina Hall" in message and "Harbour Room" not in message


def test_ac5_each_decision_is_its_own_notice(client, db_session):
    e = _two_bookings(client, db_session)

    client.post(f"/venue-bookings/{e['marina']}/approve", headers=e["staff_h"])
    client.post(f"/venue-bookings/{e['harbour']}/reject", json={"reason": "Full"}, headers=e["staff_h"])

    first, second = _inbox(client, e["coord_h"], VENUE)
    assert "Marina Hall" in first and "approved" in first
    assert "Harbour Room" in second and "rejected" in second


def test_ac4_a_refused_or_repeated_decision_sends_nothing_new(client, db_session):
    e = _two_bookings(client, db_session)
    assert client.post(f"/venue-bookings/{e['harbour']}/reject", json={}, headers=e["staff_h"]).status_code == 422
    client.post(f"/venue-bookings/{e['marina']}/approve", headers=e["staff_h"])

    again = client.post(f"/venue-bookings/{e['marina']}/approve", headers=e["staff_h"])

    assert again.status_code == 409
    assert len(_inbox(client, e["coord_h"], VENUE)) == 1


# --- AC6: a Change Request is submitted -> told ----------------------------


def _request_changes(client, e, description="Move it a day later"):
    return client.post(
        f"/events/{e['event_id']}/change-requests",
        json={"description": description, "proposed_changes": {"expected_attendance": 150}},
        headers=e["org_h"],
    )


def test_ac6_a_submitted_change_request_reaches_the_coordinator(client, db_session):
    e = _event_with(client, db_session, EventStatus.planning_event)

    res = _request_changes(client, e)

    assert res.status_code == 201, res.text
    assert _inbox(client, e["coord_h"], CHANGE) == [
        "Organiser submitted a change request for 'Regional Partner Conference': Move it a day later"
    ]


def test_ac6_a_refused_change_request_sends_nothing(client, db_session):
    e = _event_with(client, db_session, EventStatus.planning_event)

    refused = client.post(
        f"/events/{e['event_id']}/change-requests",
        json={"description": "Bad dates", "proposed_changes": {
            "proposed_start": "2026-11-03T18:00:00Z", "proposed_end": "2026-11-03T09:00:00Z"}},
        headers=e["org_h"],
    )

    assert refused.status_code == 422
    assert _inbox(client, e["coord_h"], CHANGE) == []


def test_ac6_each_change_request_is_its_own_notice(client, db_session):
    e = _event_with(client, db_session, EventStatus.planning_event)

    first = _request_changes(client, e, "First").json()["id"]
    decided = client.post(f"/events/change-requests/{first}/reject", json={}, headers=e["coord_h"])
    assert decided.status_code == 200, decided.text  # one pending request at a time
    assert _request_changes(client, e, "Second").status_code == 201

    assert [m.rsplit(": ", 1)[1] for m in _inbox(client, e["coord_h"], CHANGE)] == ["First", "Second"]


# --- AC7: not mine, or reassigned away -> nothing ---------------------------


def _another_coordinator(client, db_session):
    return user(client, db_session, Role.COORDINATOR, "other.coordinator@example.com", "Otto Other")


def test_ac7_another_coordinator_gets_no_venue_decision(client, db_session):
    e = _two_bookings(client, db_session)
    _, other_h = _another_coordinator(client, db_session)

    client.post(f"/venue-bookings/{e['marina']}/approve", headers=e["staff_h"])

    assert _inbox(client, other_h, VENUE) == []


def test_ac7_reassigned_away_gets_no_venue_decision_and_the_new_coordinator_does(client, db_session):
    e = _two_bookings(client, db_session)
    other, other_h = _another_coordinator(client, db_session)
    _move_to(db_session, e["event_id"], other)

    client.post(f"/venue-bookings/{e['marina']}/approve", headers=e["staff_h"])

    assert _inbox(client, e["coord_h"], VENUE) == []
    assert len(_inbox(client, other_h, VENUE)) == 1


def test_ac7_reassigned_away_gets_no_change_request_notice(client, w):
    event_id = assigned_event(client, w, w["sam"])
    reassign(client, w, event_id, w["priya"])

    res = _request_changes(client, {"event_id": event_id, "org_h": w["org_h"]})

    assert res.status_code == 201, res.text
    assert _inbox(client, w["sam_h"], CHANGE) == []
    assert len(_inbox(client, w["priya_h"], CHANGE)) == 1


def test_ac7_another_coordinator_gets_no_equipment_outcome(client, db_session):
    w8 = _world(client, db_session, needed=1)
    _, other_h = _user(client, db_session, Role.COORDINATOR, name="Otto Other")

    _reserved(client, w8.tech, w8.rid, w8.mic.id, 1)

    assert _inbox(client, other_h, EQUIPMENT) == []


def test_ac7_reassigned_away_gets_no_equipment_outcome(client, db_session):
    w8 = _world(client, db_session, needed=3)
    other, other_h = _user(client, db_session, Role.COORDINATOR, name="Otto Other")
    _move_to(db_session, w8.event.id, other)

    res = _update(client, w8.tech, w8.rid, status="unavailable", reason="Out for repair")

    assert res.status_code == 200, res.text
    assert _inbox(client, w8.headers, EQUIPMENT) == []
    assert len(_inbox(client, other_h, EQUIPMENT)) == 1


def test_ac7_an_event_with_no_coordinator_tells_no_coordinator(client, db_session):
    e = _event_with(client, db_session, EventStatus.planning_event)
    db_session.get(Event, e["event_id"]).coordinator_id = None
    db_session.commit()

    _request_changes(client, e)

    db_session.expire_all()
    assert db_session.query(Notification).filter_by(type=CHANGE).count() == 0


# --- AC8: equipment reserved in full or unavailable -> Event and equipment --


def test_ac8_reserved_in_full_names_the_event_and_the_equipment(client, db_session):
    w8 = _world(client, db_session, needed=1)

    _reserved(client, w8.tech, w8.rid, w8.mic.id, 1)

    assert _inbox(client, w8.headers, EQUIPMENT) == [
        "Equipment for 'Regional Partner Conference': 1 x Audio is confirmed by Technical Support."
    ]


def test_ac8_unavailable_names_the_event_the_equipment_and_the_reason(client, db_session):
    w8 = _world(client, db_session, needed=3)

    _update(client, w8.tech, w8.rid, status="unavailable", reason="All units out for repair")

    assert _inbox(client, w8.headers, EQUIPMENT) == [
        "Equipment for 'Regional Partner Conference': 3 x Audio is unavailable by Technical Support. "
        "Reason: All units out for repair"
    ]


def test_ac8_a_partial_reservation_is_not_yet_reserved(client, db_session):
    w8 = _world(client, db_session, needed=5)

    _reserved(client, w8.tech, w8.rid, w8.mic.id, 1)

    assert _inbox(client, w8.headers, EQUIPMENT) == []


def test_ac8_the_organiser_is_still_told_too(client, db_session):
    """Frozen: the Organiser's equipment notice is unchanged."""
    w8 = _world(client, db_session, needed=1)

    _reserved(client, w8.tech, w8.rid, w8.mic.id, 1)

    assert len(_inbox(client, w8.organiser_headers, EQUIPMENT)) == 1


# --- the classes --------------------------------------------------------------


def test_coordinator_notices_extend_the_base_and_reuse_the_organisers_wording():
    for cls in (CoordinatorVenueDecisionNotice, CoordinatorEquipmentOutcomeNotice, ChangeRequestSubmittedNotice):
        assert issubclass(cls, CoordinatorNotice) and issubclass(cls, EventNotice)
    assert issubclass(CoordinatorVenueDecisionNotice, VenueBookingDecisionNotice)
    assert issubclass(CoordinatorEquipmentOutcomeNotice, EquipmentOutcomeNotice)


def test_the_coordinator_version_goes_to_the_coordinator_not_the_organiser(db_session):
    event = Event(organiser_id=1, coordinator_id=2)
    assert CoordinatorNotice().recipients(db_session, event) == [2]
    assert CoordinatorEquipmentOutcomeNotice.__mro__.index(CoordinatorNotice) < (
        CoordinatorEquipmentOutcomeNotice.__mro__.index(EquipmentOutcomeNotice)
    )
