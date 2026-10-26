from datetime import datetime, timezone

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


def test_unassigned_change_request_is_visible_to_lead_then_only_lead_and_assignee(
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

    refused = client.post(
        f"/events/change-requests/{request['id']}/approve",
        headers=unrelated_headers,
        json={},
    )
    assert refused.status_code == 403
    assert db_session.get(EventChangeRequest, request["id"]).status == ChangeRequestStatus.pending


@pytest.mark.parametrize(
    ("decision", "expected_status", "notification_type"),
    [
        ("approve", ChangeRequestStatus.approved, "event_change_approved"),
        ("reject", ChangeRequestStatus.rejected, "event_change_rejected"),
    ],
)
def test_decision_notifies_organiser_and_is_activity_logged_once(
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

    repeated = client.post(
        f"/events/change-requests/{request['id']}/{'reject' if decision == 'approve' else 'approve'}",
        headers=coordinator_headers,
        json={},
    )
    assert repeated.status_code == 409
    assert db_session.get(EventChangeRequest, request["id"]).status == expected_status
    assert (
        db_session.query(Notification)
        .filter_by(user_id=organiser.id, event_id=event_id)
        .count()
        == 1
    )


def test_major_change_preview_rechecks_each_venue_and_setup_turnaround_conflicts(
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


def test_unaffected_venue_booking_stays_approved_for_equipment_only_change(
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
    event = db_session.get(Event, event_id)
    event.status = EventStatus.planning_event
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


def test_attendance_change_reopens_venue_only_and_preserves_equipment_reservations(
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
    event = db_session.get(Event, event_id)
    event.status = EventStatus.safety_check_passed
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


@pytest.mark.parametrize(
    "terminal_status", [EventStatus.event_cancelled, EventStatus.event_completed]
)
def test_terminal_event_change_request_cannot_be_approved(
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
    assert db_session.get(Event, event_id).description == original_description
    assert db_session.get(EventChangeRequest, request["id"]).status == ChangeRequestStatus.pending
