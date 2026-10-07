"""Tests for the Safety Officer's Operational Safety Check stories.

    S1  View the Events waiting for a Safety Check and what is needed to
        judge their safety.
    S2  Approve an Event that passes the Operational Safety Check.
    S3  Reject an Event's safety arrangement or request changes.

Test names carry the story and acceptance criterion they prove.
"""

import pytest

from app.core.roles import Role
from app.models.enums import BookingStatus, EquipmentStatus, EventStatus
from app.models.equipment import Equipment, EquipmentRequest
from app.models.events import Event, EventStatusHistory
from app.models.notifications import Notification
from app.models.venues import VenueBooking
from tests.event_review_test_helpers import submitted_event, user
from tests.test_venue_booking_request import _submit, _venue


def _setup(client, db_session):
    """An event awaiting its safety check: venue approved by Venue Staff and a
    projector reserved by Technical Support, then submitted by its Coordinator."""
    organiser, org_h = user(client, db_session, Role.ORGANISER, "organiser@example.com", "Organiser")
    coordinator, coord_h = user(client, db_session, Role.COORDINATOR, "coordinator@example.com", "Coordinator")
    event_id = submitted_event(client, org_h)
    event = db_session.get(Event, event_id)
    # The Event Coordinator Lead assigns manually; stand in for that here.
    event.coordinator_id = coordinator.id
    event.status = EventStatus.event_approved
    event.room_layout_preference = "Theatre"
    projector = Equipment(name="Projector", category="Projection", total_quantity=10)
    db_session.add(projector)
    db_session.flush()
    line = EquipmentRequest(event_id=event_id, equipment_id=projector.id, quantity_requested=2)
    db_session.add(line)
    db_session.commit()

    venue_staff, staff_h = user(client, db_session, Role.VENUE_STAFF, "staff@example.com", "Vera Staff")
    tech, tech_h = user(client, db_session, Role.TECH_SUPPORT, "tech@example.com", "Tess Tech")
    officer, officer_h = user(client, db_session, Role.SAFETY_OFFICER, "safety@example.com", "Sam Safety")
    bystander, _ = user(client, db_session, Role.VENUE_STAFF, "other@example.com", "Other Staff")

    venue = _venue(
        db_session,
        emergency_access="Two fire exits on the east side",
        known_restrictions="No open flames",
    )
    booking_id = _submit(client, coord_h, event_id, venue.id).json()["id"]
    assert client.post(f"/venue-bookings/{booking_id}/approve", headers=staff_h).status_code == 200
    assert client.post(
        "/equipment-reservations",
        json={"event_id": event_id, "equipment_id": projector.id, "placement_notes": "Back of hall"},
        headers=tech_h,
    ).status_code == 200
    assert client.post(f"/events/{event_id}/confirm", headers=coord_h).status_code == 200
    assert db_session.get(Event, event_id).status == EventStatus.awaiting_safety_check
    db_session.query(Notification).delete()
    db_session.commit()

    return {
        "organiser": organiser,
        "org_h": org_h,
        "coordinator": coordinator,
        "coord_h": coord_h,
        "venue_staff": venue_staff,
        "tech": tech,
        "tech_h": tech_h,
        "officer": officer,
        "officer_h": officer_h,
        "bystander": bystander,
        "event_id": event_id,
        "booking_id": booking_id,
        "line_id": line.id,
    }


def _post(client, s, action, **body):
    return client.post(
        f"/safety-checks/{s['event_id']}/{action}", json=body or None, headers=s["officer_h"]
    )


def _status(db_session, s):
    db_session.expire_all()
    return db_session.get(Event, s["event_id"]).status


def _notified(db_session, s):
    return {n.user_id for n in db_session.query(Notification).filter_by(event_id=s["event_id"])}


def _last_log(db_session, s):
    return (
        db_session.query(EventStatusHistory)
        .filter_by(event_id=s["event_id"])
        .order_by(EventStatusHistory.id.desc())
        .first()
    )


# --- S1 AC1: the queue lists each event with its name, date and Coordinator ----


def test_s1_ac1_queue_shows_each_awaiting_event_with_name_date_and_coordinator(client, db_session):
    s = _setup(client, db_session)
    [row] = client.get("/safety-checks", headers=s["officer_h"]).json()
    assert row["id"] == s["event_id"]
    assert row["name"] == "Regional Partner Conference"
    assert row["proposed_start"].startswith("2026-11-02T09:00")
    assert row["coordinator"]["name"] == "Coordinator"


# --- S1 AC2: no events awaiting -> nothing to review ---------------------------


def test_s1_ac2_queue_is_empty_when_no_event_awaits_a_check(client, db_session):
    _, officer_h = user(client, db_session, Role.SAFETY_OFFICER, "safety@example.com", "Sam Safety")
    res = client.get("/safety-checks", headers=officer_h)
    assert res.status_code == 200
    assert res.json() == []


# --- S1 AC3: the detail carries what is needed to judge the event ---------------


def test_s1_ac3_detail_shows_attendance_venue_accessibility_and_equipment_placement(client, db_session):
    s = _setup(client, db_session)
    detail = client.get(f"/safety-checks/{s['event_id']}", headers=s["officer_h"]).json()
    assert detail["expected_attendance"] == 120
    assert detail["accessibility_needs"] == "Step-free access"
    assert detail["room_layout_preference"] == "Theatre"
    venue = detail["venue_booking"]["venue"]
    assert venue["capacity"] == 250
    assert venue["supported_layouts"] == ["Theatre"]
    assert venue["emergency_access"] == "Two fire exits on the east side"
    assert venue["known_restrictions"] == "No open flames"
    [line] = detail["equipment"]
    assert (line["equipment_name"], line["placement_notes"]) == ("Projector", "Back of hall")


def test_s1_only_a_safety_officer_can_use_the_safety_checks(client, db_session):
    s = _setup(client, db_session)
    assert client.get("/safety-checks", headers=s["org_h"]).status_code == 403
    assert client.post(f"/safety-checks/{s['event_id']}/approve", headers=s["org_h"]).status_code == 403
    assert _status(db_session, s) == EventStatus.awaiting_safety_check


# --- S2 AC1: approving confirms the event --------------------------------------


def test_s2_ac1_approving_makes_the_event_safety_check_passed_confirmed(client, db_session):
    s = _setup(client, db_session)
    res = _post(client, s, "approve")
    assert res.status_code == 200
    assert res.json()["status"] == EventStatus.safety_check_passed
    assert _status(db_session, s) == EventStatus.safety_check_passed


# --- S2 AC2: approval notifies Organiser, Coordinator and preparing staff -------


def test_s2_ac2_approval_notifies_organiser_coordinator_venue_staff_and_tech_support(client, db_session):
    s = _setup(client, db_session)
    _post(client, s, "approve")
    assert _notified(db_session, s) == {
        s["organiser"].id,
        s["coordinator"].id,
        s["venue_staff"].id,
        s["tech"].id,
    }


# --- S2 AC3: approval is in the Activity Log with name and time -----------------


def test_s2_ac3_approval_is_recorded_with_the_officers_name_and_time(client, db_session):
    s = _setup(client, db_session)
    _post(client, s, "approve")
    entry = client.get(f"/safety-checks/{s['event_id']}", headers=s["officer_h"]).json()["activity"][0]
    assert entry["from_status"] == EventStatus.awaiting_safety_check
    assert entry["to_status"] == EventStatus.safety_check_passed
    assert entry["changed_by_name"] == "Sam Safety"
    assert entry["created_at"]


# --- S2 AC4: an event not awaiting a check cannot be approved -------------------


def test_s2_ac4_approving_an_event_not_awaiting_a_check_is_refused(client, db_session):
    s = _setup(client, db_session)
    assert _post(client, s, "approve").status_code == 200
    assert _post(client, s, "approve").status_code == 409  # already confirmed
    assert db_session.query(Notification).count() == 4  # nobody told twice


# --- S2 AC5: only a passed event may move to preparation ------------------------


def test_s2_ac5_an_event_that_has_not_passed_cannot_move_to_preparation(client, db_session):
    s = _setup(client, db_session)
    settings = {
        "registration_enabled": True,
        "registration_opens_at": "2026-10-10T09:00:00Z",
        "registration_closes_at": "2026-10-20T09:00:00Z",
    }
    url = f"/events/assigned/{s['event_id']}/registration"
    assert client.put(url, json=settings, headers=s["coord_h"]).status_code == 409

    _post(client, s, "approve")
    assert client.put(url, json=settings, headers=s["coord_h"]).status_code == 200


# --- S2 AC6: a booking or equipment no longer approved blocks approval ----------


@pytest.mark.parametrize("withdraw", ["venue", "equipment"])
def test_s2_ac6_approval_is_refused_when_an_arrangement_is_no_longer_approved(
    client, db_session, withdraw
):
    s = _setup(client, db_session)
    if withdraw == "venue":
        db_session.get(VenueBooking, s["booking_id"]).status = BookingStatus.cancelled
    else:
        db_session.get(EquipmentRequest, s["line_id"]).status = EquipmentStatus.reviewing
    db_session.commit()

    res = _post(client, s, "approve")
    assert res.status_code == 409
    assert "Outstanding" in res.json()["detail"]
    assert _status(db_session, s) == EventStatus.awaiting_safety_check


# --- S3 AC1: no reason -> decision not saved ------------------------------------


@pytest.mark.parametrize(
    "action, body",
    [
        ("reject", {}),
        ("reject", {"reason": "   "}),
        ("request-changes", {"reason": "", "equipment_request_ids": [0]}),
    ],
)
def test_s3_ac1_rejecting_or_requesting_changes_without_a_reason_is_not_saved(
    client, db_session, action, body
):
    s = _setup(client, db_session)
    if "equipment_request_ids" in body:
        body["equipment_request_ids"] = [s["line_id"]]
    assert _post(client, s, action, **body).status_code == 422
    assert _status(db_session, s) == EventStatus.awaiting_safety_check
    assert db_session.get(EquipmentRequest, s["line_id"]).safety_recheck_reason is None
    assert db_session.query(Notification).count() == 0


# --- S3 AC2: request changes -> planning, only the marked items to review -------


def test_s3_ac2_requesting_changes_returns_to_planning_with_only_marked_items_to_review(
    client, db_session
):
    s = _setup(client, db_session)
    res = _post(client, s, "request-changes", reason="Projector blocks a fire exit",
                equipment_request_ids=[s["line_id"]])
    assert res.status_code == 200
    assert _status(db_session, s) == EventStatus.planning_event

    line = db_session.get(EquipmentRequest, s["line_id"])
    booking = db_session.get(VenueBooking, s["booking_id"])
    assert line.safety_recheck_reason == "Projector blocks a fire exit"
    assert booking.safety_recheck_reason is None
    # Held, not released: the line is still reserved and the venue still booked.
    assert line.status == EquipmentStatus.reserved
    assert booking.status == BookingStatus.approved

    # The marked item must be reviewed before the event can go back.
    assert client.post(f"/events/{s['event_id']}/confirm", headers=s["coord_h"]).status_code == 409
    assert client.post(
        f"/equipment-reservations/{s['line_id']}/safety-recheck/confirm",
        json={"placement_notes": "Side wall, clear of exits"},
        headers=s["tech_h"],
    ).status_code == 200
    assert client.post(f"/events/{s['event_id']}/confirm", headers=s["coord_h"]).status_code == 200


# --- S3 AC3: reject -> planning, everything to review, nothing cancelled --------


def test_s3_ac3_rejecting_returns_to_planning_with_every_arrangement_to_review_uncancelled(
    client, db_session
):
    s = _setup(client, db_session)
    assert _post(client, s, "reject", reason="Capacity too tight for the layout").status_code == 200
    assert _status(db_session, s) == EventStatus.planning_event

    booking = db_session.get(VenueBooking, s["booking_id"])
    line = db_session.get(EquipmentRequest, s["line_id"])
    assert booking.safety_recheck_reason == line.safety_recheck_reason == "Capacity too tight for the layout"
    assert booking.status == BookingStatus.approved
    assert line.status == EquipmentStatus.reserved


# --- S3 AC4: Organiser, Coordinator and affected staff are told the reason ------


def test_s3_ac4_changes_notify_organiser_coordinator_and_only_the_affected_staff(client, db_session):
    s = _setup(client, db_session)
    _post(client, s, "request-changes", reason="Move the projector",
          equipment_request_ids=[s["line_id"]])
    assert _notified(db_session, s) == {s["organiser"].id, s["coordinator"].id, s["tech"].id}
    assert all("Move the projector" in n.message for n in db_session.query(Notification))


def test_s3_ac4_rejection_notifies_everyone_responsible_with_the_reason(client, db_session):
    s = _setup(client, db_session)
    _post(client, s, "reject", reason="Unsafe crowd flow")
    assert _notified(db_session, s) == {
        s["organiser"].id,
        s["coordinator"].id,
        s["venue_staff"].id,
        s["tech"].id,
    }
    assert s["bystander"].id not in _notified(db_session, s)
    assert all("Unsafe crowd flow" in n.message for n in db_session.query(Notification))


# --- S3 AC5: decision and reason are in the Activity Log with name and time -----


@pytest.mark.parametrize("action", ["reject", "request-changes"])
def test_s3_ac5_decision_and_reason_are_recorded_with_name_and_time(client, db_session, action):
    s = _setup(client, db_session)
    _post(client, s, action, reason="Blocked exit", venue_booking_ids=[s["booking_id"]])
    entry = _last_log(db_session, s)
    assert entry.to_status == EventStatus.planning_event
    assert "Blocked exit" in entry.note
    assert entry.changed_by == s["officer"].id
    assert entry.created_at is not None


# --- S3 AC6: an event not awaiting a check cannot be rejected or changed --------


@pytest.mark.parametrize("action", ["reject", "request-changes"])
def test_s3_ac6_deciding_an_event_not_awaiting_a_check_is_refused(client, db_session, action):
    s = _setup(client, db_session)
    _post(client, s, "approve")
    res = _post(client, s, action, reason="Too late", venue_booking_ids=[s["booking_id"]])
    assert res.status_code == 409
    assert _status(db_session, s) == EventStatus.safety_check_passed
    assert db_session.get(VenueBooking, s["booking_id"]).safety_recheck_reason is None
