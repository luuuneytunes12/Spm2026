from datetime import datetime, timezone

import pytest

from app.core.roles import Role
from app.models.enums import (
    BookingStatus,
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
from app.models.events import Event, EventStatusHistory
from app.models.venues import Venue, VenueBooking
from event_review_test_helpers import review_setup, user


def _start_planning(client, db_session):
    organiser, organiser_headers, coordinator, coordinator_headers, event_id = review_setup(
        client, db_session
    )
    event = db_session.get(Event, event_id)
    event.status = EventStatus.planning_event
    db_session.commit()
    return organiser, organiser_headers, coordinator, coordinator_headers, event_id


def test_assigned_coordinator_can_edit_planning_details_and_activity_is_recorded(
    client, db_session
):
    _, _, coordinator, coordinator_headers, event_id = _start_planning(client, db_session)

    response = client.patch(
        f"/events/assigned/{event_id}/planning",
        headers=coordinator_headers,
        json={
            "name": "Updated conference",
            "description": "Updated briefing details",
            "event_contact_name": "Event Contact",
            "event_contact_email": "contact@example.com",
            "registration_enabled": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Updated conference"
    assert response.json()["event_contact_name"] == "Event Contact"
    assert response.json()["event_contact_email"] == "contact@example.com"
    assert response.json()["registration_enabled"] is True
    event = db_session.get(Event, event_id)
    assert event.description == "Updated briefing details"
    activity = client.get(f"/events/{event_id}/activity", headers=coordinator_headers).json()
    assert activity[0]["changed_by_name"] == coordinator.name
    assert "description" in activity[0]["note"]


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "   "},
        {
            "proposed_start": "2026-11-02T17:00:00Z",
            "proposed_end": "2026-11-02T09:00:00Z",
        },
        {"expected_attendance": None},
    ],
)
def test_invalid_planning_edit_is_refused_without_mutating_event(
    client, db_session, payload
):
    _, _, _, coordinator_headers, event_id = _start_planning(client, db_session)
    original = db_session.get(Event, event_id)
    original_name = original.name
    original_start = original.proposed_start
    original_history_count = db_session.query(EventStatusHistory).count()

    response = client.patch(
        f"/events/assigned/{event_id}/planning",
        headers=coordinator_headers,
        json=payload,
    )

    assert response.status_code == 422
    event = db_session.get(Event, event_id)
    assert event.name == original_name
    assert event.proposed_start == original_start
    assert db_session.query(EventStatusHistory).count() == original_history_count


def test_only_assigned_coordinator_can_edit_event(client, db_session):
    _, _, _, _, event_id = _start_planning(client, db_session)
    _, other_coordinator_headers = user(
        client,
        db_session,
        role=Role.COORDINATOR,
        email="other-coordinator@example.com",
        name="Other Coordinator",
    )

    response = client.patch(
        f"/events/assigned/{event_id}/planning",
        headers=other_coordinator_headers,
        json={"description": "Unauthorised"},
    )

    assert response.status_code == 404
    assert db_session.get(Event, event_id).description is None


@pytest.mark.parametrize("terminal_status", [EventStatus.event_cancelled, EventStatus.event_completed])
def test_terminal_event_cannot_be_edited(client, db_session, terminal_status):
    _, _, _, coordinator_headers, event_id = _start_planning(client, db_session)
    db_session.get(Event, event_id).status = terminal_status
    db_session.commit()
    original_description = db_session.get(Event, event_id).description

    response = client.patch(
        f"/events/assigned/{event_id}/planning",
        headers=coordinator_headers,
        json={"description": "Must not save"},
    )

    assert response.status_code == 409
    assert db_session.get(Event, event_id).description == original_description


def test_major_change_reopens_arrangements_and_flags_capacity_shortfall(
    client, db_session
):
    organiser, _, coordinator, coordinator_headers, event_id = _start_planning(
        client, db_session
    )
    event = db_session.get(Event, event_id)
    event.status = EventStatus.safety_check_passed
    venue = Venue(name="Small Hall", location="Building A", capacity=100)
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
        expected_attendance=80,
        status=BookingStatus.approved,
        reviewed_by=coordinator.id,
        reviewed_at=datetime.now(timezone.utc),
    )
    equipment_request = EquipmentRequest(
        event_id=event_id,
        equipment_id=equipment.id,
        quantity_requested=1,
        status=EquipmentStatus.reserved,
        reviewed_by=coordinator.id,
        reviewed_at=datetime.now(timezone.utc),
    )
    requirement = CoordinatorEquipmentRequirement(
        event_id=event_id,
        category="Audio",
        quantity_needed=1,
        status=EquipmentStatus.reserved,
        created_by=coordinator.id,
    )
    db_session.add_all([booking, equipment_request, requirement])
    db_session.commit()

    response = client.patch(
        f"/events/assigned/{event_id}/planning",
        headers=coordinator_headers,
        json={"expected_attendance": 150},
    )

    assert response.status_code == 200
    assert response.json()["status"] == EventStatus.planning_event
    assert response.json()["affected_venue_bookings"] == ["Small Hall"]
    assert response.json()["affected_equipment_requirements"] == []
    db_session.refresh(booking)
    db_session.refresh(equipment_request)
    assert booking.status == BookingStatus.pending
    assert booking.expected_attendance is None
    assert equipment_request.status == EquipmentStatus.reserved

    suitability = client.get(
        f"/venues/events/{event_id}/suitability", headers=coordinator_headers
    )
    assert suitability.status_code == 200
    capacity_check = next(
        check
        for check in suitability.json()["venues"][0]["checks"]
        if check["category"] == "capacity"
    )
    assert capacity_check["met"] is False
    assert "Insufficient capacity" in capacity_check["message"]


def test_major_change_request_approval_returns_confirmed_event_to_planning(
    client, db_session
):
    _, organiser_headers, coordinator, coordinator_headers, event_id = _start_planning(
        client, db_session
    )
    event = db_session.get(Event, event_id)
    event.status = EventStatus.safety_check_passed
    equipment = Equipment(
        name="Projector",
        total_quantity=2,
        operational_status=EquipmentOperationalStatus.available,
    )
    db_session.add(equipment)
    db_session.flush()
    reserved = EquipmentRequest(
        event_id=event_id,
        equipment_id=equipment.id,
        quantity_requested=1,
        status=EquipmentStatus.reserved,
    )
    db_session.add(reserved)
    requirement = CoordinatorEquipmentRequirement(
        event_id=event_id,
        category="Projection",
        quantity_needed=1,
        status=EquipmentStatus.reserved,
        created_by=coordinator.id,
    )
    db_session.add(requirement)
    db_session.commit()
    db_session.add(
        RequirementReservationLink(
            requirement_id=requirement.id,
            event_id=event_id,
            equipment_id=equipment.id,
        )
    )
    db_session.commit()

    change_request_response = client.post(
        f"/events/{event_id}/change-requests",
        headers=organiser_headers,
        json={
            "description": "Move the event to a new time and recheck equipment.",
            "proposed_changes": {
                "proposed_start": "2026-11-03T09:00:00Z",
                "proposed_end": "2026-11-03T17:00:00Z",
            },
        },
    )
    assert change_request_response.status_code == 201, change_request_response.text
    change_request = change_request_response.json()
    response = client.post(
        f"/events/change-requests/{change_request['id']}/approve",
        headers=coordinator_headers,
        json={},
    )

    assert response.status_code == 200
    assert db_session.get(Event, event_id).status == EventStatus.planning_event
    db_session.refresh(reserved)
    assert reserved.status == EquipmentStatus.requested
    requirements = client.get(
        f"/equipment-requirements/events/{event_id}", headers=coordinator_headers
    )
    assert requirements.status_code == 200
    assert requirements.json()[0]["status"] == "requested"


def test_event_contacts_are_nullable_when_not_provided(client, db_session):
    _, _, _, coordinator_headers, event_id = _start_planning(client, db_session)

    response = client.get(f"/events/assigned/{event_id}", headers=coordinator_headers)

    assert response.status_code == 200
    assert response.json()["event_contact_name"] is None
    assert response.json()["event_contact_email"] is None
