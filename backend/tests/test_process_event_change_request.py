"""US3 - Process Event Change Request.

Each test is named after the acceptance criterion it proves:

  AC1   a Pending request on an Event not assigned to me cannot be approved
        or rejected (screen or direct request); it stays Pending
  AC2   a major request lists each affected Venue Booking and Equipment
        Requirement separately; the others stay unchanged unless I choose
        otherwise
  AC3   the Event Organiser is notified of my decision
  AC4   the decision is in the Activity Log with my name and the time
  AC5   unassigned: the Lead sees it; assigned: only the assignee and the Lead
  AC6   each affected Venue Booking's suitability is re-checked with the new values
  AC7   a request already Approved or Rejected cannot be decided again
  AC8   a date/time move shows conflicts at the Venue, setup and turnaround included
  AC9   approving a major request on an Awaiting Safety Check / Confirmed Event
        returns it to Planning Event and it must pass the Safety Check again
  AC10  a request on a Cancelled or Completed Event cannot be approved
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.roles import Role
from app.models.enums import (
    BookingStatus,
    ChangeRequestStatus,
    EquipmentOperationalStatus,
    EquipmentStatus,
    EventStatus,
)
from app.models.equipment import (
    CoordinatorEquipmentRequirement,
    Equipment,
    EquipmentRequest,
    RequirementReservationLink,
)
from app.models.events import Event, EventChangeRequest, EventStatusHistory
from app.models.notifications import Notification
from app.models.venues import Venue, VenueBooking
from event_review_test_helpers import submitted_event, user


def _submitted(client, db_session):
    organiser, organiser_headers = user(
        client, db_session, Role.ORGANISER, "change-owner@example.com", "Event Organiser"
    )
    event_id = submitted_event(client, organiser_headers)
    return organiser, organiser_headers, event_id


def _change_request(client, event_id, headers, changes=None):
    response = client.post(
        f"/events/{event_id}/change-requests",
        headers=headers,
        json={
            "description": "Please update the event arrangements.",
            "proposed_changes": changes or {"description": "Updated event description"},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _assign(db_session, event_id, coordinator):
    event = db_session.get(Event, event_id)
    event.coordinator_id = coordinator.id
    event.status = EventStatus.under_review
    db_session.commit()


def _assigned(client, db_session, status=EventStatus.under_review):
    organiser, organiser_headers, event_id = _submitted(client, db_session)
    coordinator, coordinator_headers = user(
        client, db_session, Role.COORDINATOR, "assigned-cr@example.com", "Assigned Coordinator"
    )
    _assign(db_session, event_id, coordinator)
    db_session.get(Event, event_id).status = status
    db_session.commit()
    return organiser, organiser_headers, coordinator, coordinator_headers, event_id


def _two_arrangements(db_session, event_id, organiser, coordinator):
    """An approved booking, and a reserved item fulfilling a requirement."""
    event = db_session.get(Event, event_id)
    venue = Venue(name="Main Hall", location="Building A", capacity=300)
    equipment = Equipment(
        name="Projector",
        total_quantity=2,
        operational_status=EquipmentOperationalStatus.available,
    )
    db_session.add_all([venue, equipment])
    db_session.flush()
    booking = VenueBooking(
        event_id=event_id,
        venue_id=venue.id,
        requested_by=organiser.id,
        start_time=event.proposed_start,
        end_time=event.proposed_end,
        status=BookingStatus.approved,
    )
    reservation = EquipmentRequest(
        event_id=event_id,
        equipment_id=equipment.id,
        quantity_requested=1,
        status=EquipmentStatus.reserved,
    )
    requirement = CoordinatorEquipmentRequirement(
        event_id=event_id,
        category="Projection",
        quantity_needed=1,
        status=EquipmentStatus.reserved,
        created_by=coordinator.id,
    )
    db_session.add_all([booking, reservation, requirement])
    db_session.commit()
    return booking, reservation, requirement


def _decision_entries(db_session, event_id):
    return (
        db_session.query(EventStatusHistory)
        .filter(
            EventStatusHistory.event_id == event_id,
            EventStatusHistory.note.like("Change Request %"),
        )
        .count()
    )


# --- AC1 / AC5 --------------------------------------------------------------------


def test_ac1_ac5_unassigned_change_request_is_visible_to_lead_then_only_lead_and_assignee(
    client, db_session
):
    _, organiser_headers, event_id = _submitted(client, db_session)
    lead, lead_headers = user(
        client, db_session, Role.COORDINATOR_LEAD, "lead@example.com", "Coordinator Lead"
    )
    coordinator, coordinator_headers = user(
        client,
        db_session,
        Role.COORDINATOR,
        "assigned@example.com",
        "Assigned Coordinator",
    )
    unrelated, unrelated_headers = user(
        client,
        db_session,
        Role.COORDINATOR,
        "unrelated@example.com",
        "Unrelated Coordinator",
    )
    request = _change_request(client, event_id, organiser_headers)

    lead_view = client.get(
        f"/lead/unassigned-queue/{event_id}", headers=lead_headers
    )
    assert lead_view.status_code == 200
    assert lead_view.json()["change_requests"][0]["id"] == request["id"]
    assert client.get(
        f"/events/change-requests/{request['id']}", headers=lead_headers
    ).status_code == 200
    queue = client.get("/lead/unassigned-queue", headers=lead_headers)
    assert queue.status_code == 200
    assert next(row for row in queue.json() if row["id"] == event_id)[
        "has_pending_change_request"
    ]
    assert client.get(
        f"/events/change-requests/{request['id']}", headers=coordinator_headers
    ).status_code == 404

    _assign(db_session, event_id, coordinator)
    assigned_view = client.get(
        f"/events/assigned/{event_id}", headers=coordinator_headers
    )
    assert assigned_view.status_code == 200
    assert assigned_view.json()["change_requests"][0]["id"] == request["id"]
    assert client.get(
        f"/lead/assignments/{event_id}", headers=lead_headers
    ).json()["change_requests"][0]["id"] == request["id"]
    assert client.get(
        f"/events/change-requests/{request['id']}", headers=unrelated_headers
    ).status_code == 404
    assert client.get(
        f"/events/assigned/{event_id}", headers=unrelated_headers
    ).status_code == 404

    refused = client.post(
        f"/events/change-requests/{request['id']}/approve",
        headers=unrelated_headers,
        json={},
    )
    assert refused.status_code == 403
    assert db_session.get(EventChangeRequest, request["id"]).status == ChangeRequestStatus.pending


@pytest.mark.parametrize("decision", ["approve", "reject"])
@pytest.mark.parametrize("assigned", [True, False], ids=["someone-else's", "not-yet-assigned"])
def test_ac1_a_coordinator_not_assigned_cannot_decide_and_it_stays_pending(
    client, db_session, decision, assigned
):
    organiser, organiser_headers, event_id = _submitted(client, db_session)
    if assigned:
        owner, _ = user(client, db_session, Role.COORDINATOR, "owner-cr@example.com", "Owner")
        _assign(db_session, event_id, owner)
    _, outsider_headers = user(
        client, db_session, Role.COORDINATOR, "outsider-cr@example.com", "Outsider"
    )
    request = _change_request(client, event_id, organiser_headers)
    description_before = db_session.get(Event, event_id).description

    response = client.post(
        f"/events/change-requests/{request['id']}/{decision}",
        headers=outsider_headers,
        json={"review_notes": "Trying anyway."},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "Only the assigned Event Coordinator may review this change request."
    )
    db_session.expire_all()
    assert db_session.get(EventChangeRequest, request["id"]).status == ChangeRequestStatus.pending
    assert db_session.get(Event, event_id).description == description_before
    assert _decision_entries(db_session, event_id) == 0
    assert (
        db_session.query(Notification)
        .filter_by(user_id=organiser.id, event_id=event_id)
        .filter(Notification.type.in_(["event_change_approved", "event_change_rejected"]))
        .count()
        == 0
    )


@pytest.mark.parametrize("decision", ["approve", "reject"])
@pytest.mark.parametrize("role", [Role.COORDINATOR_LEAD, Role.ORGANISER])
def test_ac1_other_roles_cannot_decide_a_change_request(client, db_session, decision, role):
    _, organiser_headers, _, _, event_id = _assigned(client, db_session)
    request = _change_request(client, event_id, organiser_headers)
    if role is Role.ORGANISER:
        headers = organiser_headers
    else:
        _, headers = user(client, db_session, role, "lead-cr@example.com", "Lead")

    response = client.post(
        f"/events/change-requests/{request['id']}/{decision}", headers=headers, json={}
    )

    assert response.status_code == 403
    assert db_session.get(EventChangeRequest, request["id"]).status == ChangeRequestStatus.pending


def test_ac1_a_change_request_that_does_not_exist_is_not_found(client, db_session):
    _, _, _, coordinator_headers, _ = _assigned(client, db_session)

    response = client.post(
        "/events/change-requests/999999/approve", headers=coordinator_headers, json={}
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Change request not found"}


# --- AC3 / AC4 / AC7 ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("decision", "expected_status", "notification_type"),
    [
        ("approve", ChangeRequestStatus.approved, "event_change_approved"),
        ("reject", ChangeRequestStatus.rejected, "event_change_rejected"),
    ],
)
def test_ac3_ac4_ac7_decision_notifies_organiser_and_is_activity_logged_once(
    client, db_session, decision, expected_status, notification_type
):
    organiser, organiser_headers, event_id = _submitted(client, db_session)
    coordinator, coordinator_headers = user(
        client,
        db_session,
        Role.COORDINATOR,
        f"{decision}-coordinator@example.com",
        "Decision Coordinator",
    )
    _assign(db_session, event_id, coordinator)
    request = _change_request(client, event_id, organiser_headers)

    response = client.post(
        f"/events/change-requests/{request['id']}/{decision}",
        headers=coordinator_headers,
        json={"review_notes": "Reviewed and recorded."},
    )

    assert response.status_code == 200
    assert response.json()["status"] == expected_status
    notification = (
        db_session.query(Notification)
        .filter_by(user_id=organiser.id, event_id=event_id)
        .filter(Notification.type != "event_status_changed")  # the status notice is the Organiser story's
        .one()
    )
    assert notification.type == notification_type
    decision_label = "approved" if decision == "approve" else "rejected"
    decision_entry = (
        db_session.query(EventStatusHistory)
        .filter(
            EventStatusHistory.event_id == event_id,
            EventStatusHistory.note.startswith(f"Change Request {decision_label}:"),
        )
        .one()
    )
    assert decision_entry.changed_by == coordinator.id
    assert decision_entry.created_at is not None
    assert decision_entry.changed_by_user.name == coordinator.name

    activity = client.get(f"/events/{event_id}/activity", headers=coordinator_headers).json()
    logged = next(e for e in activity if e["note"].startswith(f"Change Request {decision_label}:"))
    assert logged["changed_by_name"] == "Decision Coordinator"
    assert logged["created_at"]

    repeated = client.post(
        f"/events/change-requests/{request['id']}/{'reject' if decision == 'approve' else 'approve'}",
        headers=coordinator_headers,
        json={},
    )
    assert repeated.status_code == 409
    assert repeated.json()["detail"] == "Change request is no longer pending."
    assert db_session.get(EventChangeRequest, request["id"]).status == expected_status
    assert (
        db_session.query(Notification)
        .filter_by(user_id=organiser.id, event_id=event_id)
        .filter(Notification.type != "event_status_changed")  # the status notice is the Organiser story's
        .count()
        == 1
    )


@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_ac7_the_same_decision_twice_is_refused_and_the_first_stands(
    client, db_session, decision
):
    organiser, organiser_headers, _, coordinator_headers, event_id = _assigned(
        client, db_session
    )
    request = _change_request(client, event_id, organiser_headers)
    url = f"/events/change-requests/{request['id']}/{decision}"
    first = client.post(url, headers=coordinator_headers, json={"review_notes": "First."})
    assert first.status_code == 200

    second = client.post(url, headers=coordinator_headers, json={"review_notes": "Second."})

    assert second.status_code == 409
    stored = db_session.get(EventChangeRequest, request["id"])
    assert stored.review_notes == "First."
    assert _decision_entries(db_session, event_id) == 1


def test_ac3_the_organiser_of_another_event_is_not_notified(client, db_session):
    _, organiser_headers, _, coordinator_headers, event_id = _assigned(client, db_session)
    other, other_headers = user(
        client, db_session, Role.ORGANISER, "other-owner@example.com", "Other Owner"
    )
    submitted_event(client, other_headers)
    request = _change_request(client, event_id, organiser_headers)

    client.post(
        f"/events/change-requests/{request['id']}/reject",
        headers=coordinator_headers,
        json={"review_notes": "Not possible."},
    )

    assert db_session.query(Notification).filter_by(user_id=other.id).filter(
        Notification.type.in_(["event_change_approved", "event_change_rejected"])
    ).count() == 0


# --- AC2 / AC6 / AC8 / AC9 ----------------------------------------------------------


def test_ac2_ac6_ac8_ac9_major_change_preview_rechecks_each_venue_and_setup_turnaround_conflicts(
    client, db_session
):
    organiser, organiser_headers, event_id = _submitted(client, db_session)
    coordinator, coordinator_headers = user(
        client,
        db_session,
        Role.COORDINATOR,
        "suitability-coordinator@example.com",
        "Suitability Coordinator",
    )
    _assign(db_session, event_id, coordinator)
    event = db_session.get(Event, event_id)
    event.status = EventStatus.safety_check_passed
    event.proposed_start = datetime(2026, 11, 2, 9, tzinfo=timezone.utc)
    event.proposed_end = datetime(2026, 11, 2, 17, tzinfo=timezone.utc)
    venue = Venue(
        name="Small Hall",
        location="Building A",
        capacity=100,
        setup_minutes=30,
        turnaround_minutes=45,
    )
    equipment = Equipment(
        name="Projector",
        total_quantity=3,
        operational_status=EquipmentOperationalStatus.available,
    )
    db_session.add_all([venue, equipment])
    db_session.flush()
    own_booking = VenueBooking(
        event_id=event_id,
        venue_id=venue.id,
        requested_by=organiser.id,
        start_time=event.proposed_start,
        end_time=event.proposed_end,
        status=BookingStatus.approved,
    )
    other_event = Event(
        organiser_id=organiser.id,
        name="Another event",
        status=EventStatus.event_approved,
        proposed_start=datetime(2026, 11, 3, 14, tzinfo=timezone.utc),
        proposed_end=datetime(2026, 11, 3, 15, tzinfo=timezone.utc),
        expected_attendance=20,
    )
    db_session.add_all([own_booking, other_event])
    db_session.flush()
    db_session.add(
        VenueBooking(
            event_id=other_event.id,
            venue_id=venue.id,
            requested_by=organiser.id,
            start_time=datetime(2026, 11, 3, 14, tzinfo=timezone.utc),
            end_time=datetime(2026, 11, 3, 15, tzinfo=timezone.utc),
            status=BookingStatus.approved,
        )
    )
    requirement = CoordinatorEquipmentRequirement(
        event_id=event_id,
        category="Projection",
        quantity_needed=2,
        status=EquipmentStatus.reserved,
        created_by=coordinator.id,
    )
    equipment_request = EquipmentRequest(
        event_id=event_id,
        equipment_id=equipment.id,
        quantity_requested=2,
        status=EquipmentStatus.reserved,
    )
    db_session.add_all([requirement, equipment_request])
    db_session.flush()
    db_session.add(
        RequirementReservationLink(
            requirement_id=requirement.id,
            event_id=event_id,
            equipment_id=equipment.id,
        )
    )
    db_session.commit()

    request = _change_request(
        client,
        event_id,
        organiser_headers,
        {
            "proposed_start": "2026-11-03T12:00:00Z",
            "proposed_end": "2026-11-03T13:00:00Z",
            "expected_attendance": 150,
        },
    )

    assert request["important_change"] is True
    assert request["safety_check_required"] is True
    assert len(request["venue_bookings_to_reconsider"]) == 1
    venue_impact = request["venue_bookings_to_reconsider"][0]
    assert venue_impact["id"] == own_booking.id
    assert venue_impact["suitable"] is False
    assert any("Insufficient capacity" in item for item in venue_impact["unmet_requirements"])
    assert any("setup and turnaround included" in item for item in venue_impact["conflicts"])
    assert [item["id"] for item in request["equipment_requirements_to_reconsider"]] == [
        requirement.id
    ]

    event.status = EventStatus.safety_check_passed
    db_session.commit()
    approved = client.post(
        f"/events/change-requests/{request['id']}/approve",
        headers=coordinator_headers,
        json={},
    )
    assert approved.status_code == 200, approved.text
    db_session.refresh(own_booking)
    db_session.refresh(equipment_request)
    assert own_booking.status == BookingStatus.pending
    assert own_booking.start_time.isoformat().startswith("2026-11-03T12:00")
    assert equipment_request.status == EquipmentStatus.requested
    assert db_session.get(Event, event_id).status == EventStatus.planning_event


def test_ac6_frozen_literal_a_booking_that_still_fits_is_suitable_with_no_conflicts(
    client, db_session
):
    organiser, organiser_headers, coordinator, _, event_id = _assigned(
        client, db_session, status=EventStatus.planning_event
    )
    booking, _, _ = _two_arrangements(db_session, event_id, organiser, coordinator)
    # what the submitted Event asks of its venue (event_review_test_helpers.COMPLETE)
    booking.venue.facilities = ["Main hall"]
    booking.venue.accessibility_features = ["Step-free access"]
    db_session.commit()

    request = _change_request(client, event_id, organiser_headers, {"expected_attendance": 250})

    impact = request["venue_bookings_to_reconsider"][0]
    assert impact["suitable"] is True
    assert impact["unmet_requirements"] == []
    assert impact["conflicts"] == []


def test_ac2_unaffected_venue_booking_stays_approved_for_equipment_only_change(
    client, db_session
):
    organiser, organiser_headers, event_id = _submitted(client, db_session)
    coordinator, coordinator_headers = user(
        client,
        db_session,
        Role.COORDINATOR,
        "equipment-only-coordinator@example.com",
        "Equipment Coordinator",
    )
    _assign(db_session, event_id, coordinator)
    db_session.get(Event, event_id).status = EventStatus.planning_event
    db_session.commit()
    booking, reservation, requirement = _two_arrangements(
        db_session, event_id, organiser, coordinator
    )

    request = _change_request(
        client,
        event_id,
        organiser_headers,
        {"equipment_requirements": "Updated projection setup"},
    )
    assert request["venue_bookings_to_reconsider"] == []
    assert [item["id"] for item in request["equipment_requirements_to_reconsider"]] == [
        requirement.id
    ]

    response = client.post(
        f"/events/change-requests/{request['id']}/approve",
        headers=coordinator_headers,
        json={},
    )

    assert response.status_code == 200
    db_session.refresh(booking)
    db_session.refresh(reservation)
    assert booking.status == BookingStatus.approved
    assert reservation.status == EquipmentStatus.requested


def test_ac2_attendance_change_reopens_venue_only_and_preserves_equipment_reservations(
    client, db_session
):
    organiser, organiser_headers, event_id = _submitted(client, db_session)
    coordinator, coordinator_headers = user(
        client,
        db_session,
        Role.COORDINATOR,
        "attendance-coordinator@example.com",
        "Attendance Coordinator",
    )
    _assign(db_session, event_id, coordinator)
    db_session.get(Event, event_id).status = EventStatus.safety_check_passed
    db_session.commit()
    booking, reservation, requirement = _two_arrangements(
        db_session, event_id, organiser, coordinator
    )

    request = _change_request(
        client,
        event_id,
        organiser_headers,
        {"expected_attendance": 180},
    )
    assert [item["id"] for item in request["venue_bookings_to_reconsider"]] == [
        booking.id
    ]
    assert request["equipment_reservations_to_reconsider"] == []
    assert request["equipment_requirements_to_reconsider"] == []

    response = client.post(
        f"/events/change-requests/{request['id']}/approve",
        headers=coordinator_headers,
        json={},
    )

    assert response.status_code == 200
    db_session.refresh(booking)
    db_session.refresh(reservation)
    db_session.refresh(requirement)
    assert booking.status == BookingStatus.pending
    assert reservation.status == EquipmentStatus.reserved
    assert requirement.status == EquipmentStatus.reserved
    assert db_session.get(Event, event_id).status == EventStatus.planning_event


# --- AC2: "unless I choose otherwise" ------------------------------------------------


def test_ac2_a_pending_request_offers_the_unaffected_arrangements_as_choices(
    client, db_session
):
    organiser, organiser_headers, coordinator, _, event_id = _assigned(
        client, db_session, status=EventStatus.planning_event
    )
    booking, reservation, _ = _two_arrangements(db_session, event_id, organiser, coordinator)

    request = _change_request(client, event_id, organiser_headers, {"expected_attendance": 180})

    assert [b["id"] for b in request["venue_bookings_to_reconsider"]] == [booking.id]
    assert request["other_venue_bookings"] == []
    assert [r["id"] for r in request["other_equipment_reservations"]] == [reservation.id]
    assert request["other_equipment_reservations"][0]["equipment_name"] == "Projector"


def test_ac2_the_coordinator_can_choose_to_reopen_an_unaffected_arrangement(
    client, db_session
):
    organiser, organiser_headers, coordinator, coordinator_headers, event_id = _assigned(
        client, db_session, status=EventStatus.safety_check_passed
    )
    booking, reservation, _ = _two_arrangements(db_session, event_id, organiser, coordinator)
    request = _change_request(client, event_id, organiser_headers, {"expected_attendance": 180})

    response = client.post(
        f"/events/change-requests/{request['id']}/approve",
        headers=coordinator_headers,
        json={"reopen_equipment_reservation_ids": [reservation.id]},
    )

    assert response.status_code == 200, response.text
    db_session.refresh(booking)
    db_session.refresh(reservation)
    assert booking.status == BookingStatus.pending
    assert reservation.status == EquipmentStatus.requested
    assert response.json()["other_equipment_reservations"] == []
    entry = (
        db_session.query(EventStatusHistory)
        .filter(
            EventStatusHistory.event_id == event_id,
            EventStatusHistory.note.startswith("Also reopened for review"),
        )
        .one()
    )
    assert f"Equipment reservation #{reservation.id} (Projector)" in entry.note
    assert entry.changed_by == coordinator.id


def test_ac2_choosing_to_reopen_on_a_minor_change_returns_a_confirmed_event_to_planning(
    client, db_session
):
    organiser, organiser_headers, coordinator, coordinator_headers, event_id = _assigned(
        client, db_session, status=EventStatus.safety_check_passed
    )
    booking, reservation, _ = _two_arrangements(db_session, event_id, organiser, coordinator)
    request = _change_request(client, event_id, organiser_headers, {"description": "Typo fixed"})
    assert [b["id"] for b in request["other_venue_bookings"]] == [booking.id]

    response = client.post(
        f"/events/change-requests/{request['id']}/approve",
        headers=coordinator_headers,
        json={"reopen_venue_booking_ids": [booking.id]},
    )

    assert response.status_code == 200
    db_session.refresh(booking)
    db_session.refresh(reservation)
    assert booking.status == BookingStatus.pending
    assert reservation.status == EquipmentStatus.reserved
    assert db_session.get(Event, event_id).status == EventStatus.planning_event


def test_ac2_reopening_something_not_on_this_event_is_refused_and_nothing_changes(
    client, db_session
):
    organiser, organiser_headers, coordinator, coordinator_headers, event_id = _assigned(
        client, db_session, status=EventStatus.planning_event
    )
    booking, reservation, _ = _two_arrangements(db_session, event_id, organiser, coordinator)
    request = _change_request(client, event_id, organiser_headers, {"expected_attendance": 180})

    response = client.post(
        f"/events/change-requests/{request['id']}/approve",
        headers=coordinator_headers,
        json={"reopen_venue_booking_ids": [999999], "reopen_equipment_reservation_ids": [888888]},
    )

    assert response.status_code == 422
    messages = [item["msg"] for item in response.json()["detail"]]
    assert messages == [
        "Venue Booking #999999 is not an active booking on this Event, so it cannot be reopened for review.",
        "Equipment reservation #888888 is not a Reserved item on this Event, so it cannot be reopened for review.",
    ]
    db_session.expire_all()
    assert db_session.get(EventChangeRequest, request["id"]).status == ChangeRequestStatus.pending
    assert db_session.get(VenueBooking, booking.id).status == BookingStatus.approved
    assert db_session.get(EquipmentRequest, reservation.id).status == EquipmentStatus.reserved
    assert db_session.get(Event, event_id).expected_attendance != 180


def test_ac2_frozen_literal_a_decided_request_offers_no_choices(client, db_session):
    organiser, organiser_headers, coordinator, coordinator_headers, event_id = _assigned(
        client, db_session, status=EventStatus.planning_event
    )
    _two_arrangements(db_session, event_id, organiser, coordinator)
    request = _change_request(client, event_id, organiser_headers, {"description": "Typo"})

    rejected = client.post(
        f"/events/change-requests/{request['id']}/reject", headers=coordinator_headers, json={}
    ).json()

    assert rejected["other_venue_bookings"] == []
    assert rejected["other_equipment_reservations"] == []


# --- AC9 / AC10 ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "confirmed_status", [EventStatus.awaiting_safety_check, EventStatus.safety_check_passed]
)
def test_ac9_a_major_approval_returns_the_event_to_planning_for_a_new_safety_check(
    client, db_session, confirmed_status
):
    organiser, organiser_headers, coordinator, coordinator_headers, event_id = _assigned(
        client, db_session, status=confirmed_status
    )
    _two_arrangements(db_session, event_id, organiser, coordinator)
    request = _change_request(client, event_id, organiser_headers, {"expected_attendance": 200})
    assert request["safety_check_required"] is True

    response = client.post(
        f"/events/change-requests/{request['id']}/approve", headers=coordinator_headers, json={}
    )

    assert response.status_code == 200
    assert db_session.get(Event, event_id).status == EventStatus.planning_event
    entry = (
        db_session.query(EventStatusHistory)
        .filter(
            EventStatusHistory.event_id == event_id,
            EventStatusHistory.from_status == confirmed_status,
            EventStatusHistory.to_status == EventStatus.planning_event,
        )
        .one()
    )
    assert entry.changed_by == coordinator.id
    assert "new safety check is required" in entry.note
    submit = client.post(f"/events/{event_id}/confirm", headers=coordinator_headers)
    assert submit.status_code == 409
    assert "Main Hall" in submit.json()["detail"]


def _linked_requirement(db_session, event_id, coordinator):
    """An approved booking, and a requirement Technical Support reserved an
    item for -- linked the way the reserve endpoint links them, so its
    Reserved status is the derived one everybody sees."""
    booking, reservation, requirement = _two_arrangements(
        db_session, event_id, coordinator, coordinator
    )
    reservation.equipment.category = requirement.category
    db_session.add(
        RequirementReservationLink(
            requirement_id=requirement.id,
            event_id=event_id,
            equipment_id=reservation.equipment_id,
        )
    )
    db_session.commit()
    return booking, reservation, requirement


def _requirement_status(client, event_id, requirement_id, headers):
    response = client.get(f"/equipment-requirements/events/{event_id}", headers=headers)
    assert response.status_code == 200, response.text
    return next(item["status"] for item in response.json() if item["id"] == requirement_id)


def _one_day_later(db_session, event_id):
    event = db_session.get(Event, event_id)
    return {
        "proposed_start": (event.proposed_start + timedelta(days=1)).isoformat(),
        "proposed_end": (event.proposed_end + timedelta(days=1)).isoformat(),
    }


@pytest.mark.parametrize(
    "confirmed_status", [EventStatus.awaiting_safety_check, EventStatus.safety_check_passed]
)
@pytest.mark.parametrize("change", ["date_time", "equipment_requirement"])
def test_ac9_a_date_time_or_equipment_change_stops_the_requirement_counting_as_reserved(
    client, db_session, confirmed_status, change
):
    _, organiser_headers, coordinator, coordinator_headers, event_id = _assigned(
        client, db_session, status=confirmed_status
    )
    _, reservation, requirement = _linked_requirement(db_session, event_id, coordinator)
    assert _requirement_status(client, event_id, requirement.id, coordinator_headers) == "reserved"
    changes = (
        _one_day_later(db_session, event_id)
        if change == "date_time"
        else {"equipment_requirements": "Two projectors and a clicker"}
    )
    request = _change_request(client, event_id, organiser_headers, changes)

    response = client.post(
        f"/events/change-requests/{request['id']}/approve", headers=coordinator_headers, json={}
    )

    assert response.status_code == 200, response.text
    db_session.expire_all()
    assert db_session.get(Event, event_id).status == EventStatus.planning_event
    assert db_session.get(EquipmentRequest, reservation.id).status == EquipmentStatus.requested
    assert (
        _requirement_status(client, event_id, requirement.id, coordinator_headers) == "requested"
    )
    submit = client.post(f"/events/{event_id}/confirm", headers=coordinator_headers)
    assert submit.status_code == 409
    assert "Equipment requirement 'Projection' is not reserved" in submit.json()["detail"]


def test_ac9_once_staff_confirm_again_for_the_new_window_the_event_can_be_submitted(
    client, db_session
):
    _, organiser_headers, coordinator, coordinator_headers, event_id = _assigned(
        client, db_session, status=EventStatus.safety_check_passed
    )
    booking, reservation, requirement = _linked_requirement(db_session, event_id, coordinator)
    request = _change_request(
        client, event_id, organiser_headers, _one_day_later(db_session, event_id)
    )
    assert client.post(
        f"/events/change-requests/{request['id']}/approve", headers=coordinator_headers, json={}
    ).status_code == 200
    _, venue_headers = user(
        client, db_session, Role.VENUE_STAFF, "recheck-venue@example.com", "Venue Staff"
    )
    _, support_headers = user(
        client, db_session, Role.TECH_SUPPORT, "recheck-support@example.com", "Tech Support"
    )

    approved = client.post(f"/venue-bookings/{booking.id}/approve", headers=venue_headers)
    reserved = client.post(
        f"/equipment-requirements/{requirement.id}/reservations",
        headers=support_headers,
        json={"equipment_id": reservation.equipment_id},
    )

    assert approved.status_code == 200, approved.text
    assert reserved.status_code == 200, reserved.text
    assert (
        _requirement_status(client, event_id, requirement.id, coordinator_headers) == "reserved"
    )
    submit = client.post(f"/events/{event_id}/confirm", headers=coordinator_headers)
    assert submit.status_code == 200, submit.text
    assert submit.json()["status"] == EventStatus.awaiting_safety_check


def test_ac2_an_attendance_only_change_leaves_the_linked_requirement_reserved(
    client, db_session
):
    _, organiser_headers, coordinator, coordinator_headers, event_id = _assigned(
        client, db_session, status=EventStatus.safety_check_passed
    )
    _, reservation, requirement = _linked_requirement(db_session, event_id, coordinator)
    request = _change_request(client, event_id, organiser_headers, {"expected_attendance": 180})

    response = client.post(
        f"/events/change-requests/{request['id']}/approve", headers=coordinator_headers, json={}
    )

    assert response.status_code == 200, response.text
    db_session.expire_all()
    assert db_session.get(EquipmentRequest, reservation.id).status == EquipmentStatus.reserved
    assert (
        _requirement_status(client, event_id, requirement.id, coordinator_headers) == "reserved"
    )


@pytest.mark.parametrize(
    "terminal_status", [EventStatus.event_cancelled, EventStatus.event_completed]
)
def test_ac10_terminal_event_change_request_cannot_be_approved(
    client, db_session, terminal_status
):
    _, organiser_headers, event_id = _submitted(client, db_session)
    coordinator, coordinator_headers = user(
        client,
        db_session,
        Role.COORDINATOR,
        f"terminal-{terminal_status.value}@example.com",
        "Terminal Coordinator",
    )
    _assign(db_session, event_id, coordinator)
    request = _change_request(client, event_id, organiser_headers)
    event = db_session.get(Event, event_id)
    event.status = terminal_status
    original_description = event.description
    db_session.commit()

    response = client.post(
        f"/events/change-requests/{request['id']}/approve",
        headers=coordinator_headers,
        json={},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "This event can no longer be changed."
    assert db_session.get(Event, event_id).description == original_description
    assert db_session.get(Event, event_id).status == terminal_status
    assert db_session.get(EventChangeRequest, request["id"]).status == ChangeRequestStatus.pending


# --- Readable errors instead of crashes ----------------------------------------------


def test_a_stored_request_that_no_longer_validates_is_shown_and_refused_readably(
    client, db_session
):
    organiser, organiser_headers, coordinator, coordinator_headers, event_id = _assigned(
        client, db_session
    )
    broken = EventChangeRequest(
        event_id=event_id,
        requested_by=organiser.id,
        description="Saved before the rules tightened.",
        proposed_changes={"expected_attendance": 0, "event_contact_email": "nope"},
    )
    db_session.add(broken)
    db_session.commit()

    listed = client.get(f"/events/assigned/{event_id}", headers=coordinator_headers)
    assert listed.status_code == 200
    assert listed.json()["change_requests"][0]["id"] == broken.id

    response = client.post(
        f"/events/change-requests/{broken.id}/approve", headers=coordinator_headers, json={}
    )

    assert response.status_code == 422
    assert "no longer valid" in response.json()["detail"]
    db_session.expire_all()
    assert db_session.get(EventChangeRequest, broken.id).status == ChangeRequestStatus.pending

    # it can still be rejected, so it does not block the Event
    assert client.post(
        f"/events/change-requests/{broken.id}/reject", headers=coordinator_headers, json={}
    ).status_code == 200
