"""US2 - Edit Event Details During Planning.

Each test is named after the acceptance criterion it proves:

  AC1   name, description, contact information, registration saved and shown
  AC2   a date, time, attendance, venue or equipment change identifies the
        affected Venue Bookings and Equipment Requirements for review
  AC3   an empty name, or an end before the start, is refused; Event unchanged
  AC4   an edit to an approved event in planning is logged with who and when
  AC5   a Cancelled or Completed Event cannot be edited
  AC6   an Event not assigned to me cannot be edited
  AC7   a major edit to an Awaiting Safety Check / Confirmed Event returns it
        to Planning Event
  AC8   attendance above a Venue's capacity shows the booking as not Suitable
  AC9   approving a major Change Request on such an Event returns it to
        Planning Event, and it cannot be submitted for a Safety Check until
        its arrangements are Approved and Reserved again
  AC10  a date, time or equipment Change Request un-reserves each affected
        Equipment Requirement until Technical Support confirm it again
"""

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


def _start_planning(client, db_session, status=EventStatus.planning_event):
    organiser, organiser_headers, coordinator, coordinator_headers, event_id = review_setup(
        client, db_session
    )
    event = db_session.get(Event, event_id)
    event.status = status
    db_session.commit()
    return organiser, organiser_headers, coordinator, coordinator_headers, event_id


def _arrangements(db_session, event_id, organiser, coordinator, *, capacity=300, linked=True):
    """An approved Venue Booking, a reserved item and the Coordinator's
    requirement it fulfils."""
    event = db_session.get(Event, event_id)
    venue = Venue(name="Main Hall", location="Building A", capacity=capacity)
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
        reviewed_by=coordinator.id,
        reviewed_at=datetime.now(timezone.utc),
    )
    reservation = EquipmentRequest(
        event_id=event_id,
        equipment_id=equipment.id,
        quantity_requested=1,
        status=EquipmentStatus.reserved,
        reviewed_by=coordinator.id,
        reviewed_at=datetime.now(timezone.utc),
    )
    requirement = CoordinatorEquipmentRequirement(
        event_id=event_id,
        category="Projection",
        quantity_needed=1,
        status=EquipmentStatus.reserved,
        created_by=coordinator.id,
    )
    db_session.add_all([booking, reservation, requirement])
    db_session.flush()
    if linked:
        db_session.add(
            RequirementReservationLink(
                requirement_id=requirement.id, event_id=event_id, equipment_id=equipment.id
            )
        )
    db_session.commit()
    return booking, reservation, requirement


def _edit(client, event_id, headers, payload):
    return client.patch(
        f"/events/assigned/{event_id}/planning", headers=headers, json=payload
    )


def _requirement_status(client, event_id, headers):
    response = client.get(f"/equipment-requirements/events/{event_id}", headers=headers)
    assert response.status_code == 200
    return response.json()[0]["status"]


# --- AC1 -------------------------------------------------------------------------


def test_ac1_ac4_assigned_coordinator_can_edit_planning_details_and_activity_is_recorded(
    client, db_session
):
    _, _, coordinator, coordinator_headers, event_id = _start_planning(client, db_session)

    response = _edit(
        client,
        event_id,
        coordinator_headers,
        {
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
    assert activity[0]["created_at"]
    assert "description" in activity[0]["note"]

    shown = client.get(f"/events/assigned/{event_id}", headers=coordinator_headers).json()
    assert shown["name"] == "Updated conference"
    assert shown["event_contact_email"] == "contact@example.com"


def test_ac1_an_invalid_contact_email_is_refused_naming_the_field(client, db_session):
    _, _, _, coordinator_headers, event_id = _start_planning(client, db_session)

    response = _edit(
        client,
        event_id,
        coordinator_headers,
        {"name": "Must not save", "event_contact_email": "not-an-email"},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == "event_contact_email"
    assert db_session.get(Event, event_id).name != "Must not save"


def test_ac1_event_contacts_are_nullable_when_not_provided(client, db_session):
    _, _, _, coordinator_headers, event_id = _start_planning(client, db_session)

    response = client.get(f"/events/assigned/{event_id}", headers=coordinator_headers)

    assert response.status_code == 200
    assert response.json()["event_contact_name"] is None
    assert response.json()["event_contact_email"] is None


# --- AC2 -------------------------------------------------------------------------


def test_ac2_a_date_or_time_change_identifies_bookings_and_equipment_for_review(
    client, db_session
):
    organiser, _, coordinator, coordinator_headers, event_id = _start_planning(
        client, db_session
    )
    booking, reservation, _ = _arrangements(db_session, event_id, organiser, coordinator)

    response = _edit(
        client,
        event_id,
        coordinator_headers,
        {
            "proposed_start": "2026-11-03T09:00:00Z",
            "proposed_end": "2026-11-03T17:00:00Z",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["affected_venue_bookings"] == ["Main Hall"]
    assert response.json()["affected_equipment_requirements"] == [
        "Projector",
        "Projection requirement",
    ]
    db_session.refresh(booking)
    db_session.refresh(reservation)
    assert booking.status == BookingStatus.pending
    assert booking.start_time.isoformat().startswith("2026-11-03T09:00")
    assert reservation.status == EquipmentStatus.requested
    assert _requirement_status(client, event_id, coordinator_headers) == "requested"


def test_ac2_an_equipment_change_identifies_only_equipment(client, db_session):
    organiser, _, coordinator, coordinator_headers, event_id = _start_planning(
        client, db_session
    )
    booking, reservation, _ = _arrangements(db_session, event_id, organiser, coordinator)

    response = _edit(
        client, event_id, coordinator_headers, {"equipment_requirements": "Two projectors"}
    )

    assert response.status_code == 200
    assert response.json()["affected_venue_bookings"] == []
    assert "Projection requirement" in response.json()["affected_equipment_requirements"]
    db_session.refresh(booking)
    db_session.refresh(reservation)
    assert booking.status == BookingStatus.approved
    assert reservation.status == EquipmentStatus.requested


def test_ac2_a_venue_requirement_change_identifies_only_the_venue_booking(client, db_session):
    organiser, _, coordinator, coordinator_headers, event_id = _start_planning(
        client, db_session
    )
    booking, reservation, _ = _arrangements(db_session, event_id, organiser, coordinator)

    response = _edit(
        client, event_id, coordinator_headers, {"venue_requirements": "Stage and green room"}
    )

    assert response.status_code == 200
    assert response.json()["affected_venue_bookings"] == ["Main Hall"]
    assert response.json()["affected_equipment_requirements"] == []
    db_session.refresh(reservation)
    assert reservation.status == EquipmentStatus.reserved


def test_ac2_frozen_literal_a_name_only_edit_leaves_arrangements_alone(client, db_session):
    organiser, _, coordinator, coordinator_headers, event_id = _start_planning(
        client, db_session
    )
    booking, reservation, _ = _arrangements(db_session, event_id, organiser, coordinator)

    response = _edit(client, event_id, coordinator_headers, {"name": "Renamed"})

    assert response.status_code == 200
    assert response.json()["affected_venue_bookings"] == []
    assert response.json()["affected_equipment_requirements"] == []
    db_session.refresh(booking)
    db_session.refresh(reservation)
    assert booking.status == BookingStatus.approved
    assert reservation.status == EquipmentStatus.reserved


# --- AC3 -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"name": "   "}, "Event name cannot be empty."),
        ({"name": None}, "Event name cannot be empty."),
        (
            {
                "proposed_start": "2026-11-02T17:00:00Z",
                "proposed_end": "2026-11-02T09:00:00Z",
            },
            "proposed_end must be after proposed_start",
        ),
        (
            {"proposed_end": "2026-11-02T08:00:00Z"},
            "The event must have an end time after its start time.",
        ),
        ({"expected_attendance": None}, "Expected attendance must be at least 1."),
    ],
)
def test_ac3_invalid_planning_edit_is_refused_without_mutating_event(
    client, db_session, payload, message
):
    _, _, _, coordinator_headers, event_id = _start_planning(client, db_session)
    original = db_session.get(Event, event_id)
    original_name = original.name
    original_start = original.proposed_start
    original_end = original.proposed_end
    original_history_count = db_session.query(EventStatusHistory).count()

    response = _edit(client, event_id, coordinator_headers, payload)

    assert response.status_code == 422
    assert message in response.text
    db_session.expire_all()
    event = db_session.get(Event, event_id)
    assert event.name == original_name
    assert event.proposed_start == original_start
    assert event.proposed_end == original_end
    assert db_session.query(EventStatusHistory).count() == original_history_count


# --- AC4 -------------------------------------------------------------------------


def test_ac4_an_edit_to_an_event_approved_event_is_logged_with_identity_and_timestamp(
    client, db_session
):
    _, _, coordinator, coordinator_headers, event_id = _start_planning(
        client, db_session, status=EventStatus.event_approved
    )

    response = _edit(client, event_id, coordinator_headers, {"description": "Agenda added"})

    assert response.status_code == 200
    assert response.json()["status"] == EventStatus.event_approved
    entry = (
        db_session.query(EventStatusHistory)
        .filter(
            EventStatusHistory.event_id == event_id,
            EventStatusHistory.note.startswith("Event details updated"),
        )
        .one()
    )
    assert entry.changed_by == coordinator.id
    assert entry.created_at is not None
    assert entry.note == "Event details updated: description."


def test_ac4_saving_without_changes_adds_no_log_entry(client, db_session):
    _, _, _, coordinator_headers, event_id = _start_planning(client, db_session)
    event = db_session.get(Event, event_id)
    before = db_session.query(EventStatusHistory).filter_by(event_id=event_id).count()

    response = _edit(client, event_id, coordinator_headers, {"name": event.name})

    assert response.status_code == 200
    assert db_session.query(EventStatusHistory).filter_by(event_id=event_id).count() == before


# --- AC5 -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("terminal_status", "label"),
    [
        (EventStatus.event_cancelled, "Event Cancelled"),
        (EventStatus.event_completed, "Event Completed"),
    ],
)
def test_ac5_terminal_event_cannot_be_edited(client, db_session, terminal_status, label):
    _, _, _, coordinator_headers, event_id = _start_planning(client, db_session)
    db_session.get(Event, event_id).status = terminal_status
    db_session.commit()
    original_description = db_session.get(Event, event_id).description
    before = db_session.query(EventStatusHistory).filter_by(event_id=event_id).count()

    response = _edit(client, event_id, coordinator_headers, {"description": "Must not save"})

    assert response.status_code == 409
    assert response.json()["detail"] == (
        f"Event details cannot be edited while the Event is '{label}'."
    )
    db_session.expire_all()
    assert db_session.get(Event, event_id).description == original_description
    assert db_session.get(Event, event_id).status == terminal_status
    assert db_session.query(EventStatusHistory).filter_by(event_id=event_id).count() == before


@pytest.mark.parametrize(
    "status", [EventStatus.under_review, EventStatus.event_rejected]
)
def test_ac5_frozen_literal_an_event_not_yet_approved_or_rejected_is_not_edited_here(
    client, db_session, status
):
    _, _, _, coordinator_headers, event_id = _start_planning(client, db_session, status=status)

    response = _edit(client, event_id, coordinator_headers, {"description": "Must not save"})

    assert response.status_code == 409


# --- AC6 -------------------------------------------------------------------------


def test_ac6_only_assigned_coordinator_can_edit_event(client, db_session):
    _, _, _, _, event_id = _start_planning(client, db_session)
    _, other_coordinator_headers = user(
        client,
        db_session,
        role=Role.COORDINATOR,
        email="other-coordinator@example.com",
        name="Other Coordinator",
    )

    response = _edit(client, event_id, other_coordinator_headers, {"description": "Unauthorised"})

    assert response.status_code == 404
    assert db_session.get(Event, event_id).description is None


@pytest.mark.parametrize("role", [Role.COORDINATOR_LEAD, Role.ORGANISER, Role.VENUE_STAFF])
def test_ac6_other_roles_cannot_edit_event(client, db_session, role):
    _, _, _, _, event_id = _start_planning(client, db_session)
    _, headers = user(client, db_session, role, f"other-{role.value}@example.com", "Other")

    response = _edit(client, event_id, headers, {"description": "Unauthorised"})

    assert response.status_code == 403
    assert db_session.get(Event, event_id).description is None


# --- AC7 / AC8 --------------------------------------------------------------------


@pytest.mark.parametrize(
    "confirmed_status", [EventStatus.awaiting_safety_check, EventStatus.safety_check_passed]
)
@pytest.mark.parametrize(
    "payload",
    [
        {"proposed_start": "2026-11-02T10:00:00Z"},
        {"expected_attendance": 90},
        {"venue_requirements": "Breakout rooms"},
        {"equipment_requirements": "Extra microphones"},
    ],
)
def test_ac7_a_major_edit_returns_the_event_to_planning_and_is_logged(
    client, db_session, confirmed_status, payload
):
    _, _, coordinator, coordinator_headers, event_id = _start_planning(
        client, db_session, status=confirmed_status
    )

    response = _edit(client, event_id, coordinator_headers, payload)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == EventStatus.planning_event
    entry = (
        db_session.query(EventStatusHistory)
        .filter(
            EventStatusHistory.event_id == event_id,
            EventStatusHistory.to_status == EventStatus.planning_event,
        )
        .one()
    )
    assert entry.from_status == confirmed_status
    assert entry.changed_by == coordinator.id


def test_ac7_frozen_literal_a_minor_edit_keeps_a_confirmed_event_confirmed(client, db_session):
    _, _, _, coordinator_headers, event_id = _start_planning(
        client, db_session, status=EventStatus.safety_check_passed
    )

    response = _edit(client, event_id, coordinator_headers, {"description": "New agenda"})

    assert response.status_code == 200
    assert response.json()["status"] == EventStatus.safety_check_passed


def test_ac7_ac8_major_change_reopens_arrangements_and_flags_capacity_shortfall(
    client, db_session
):
    organiser, _, coordinator, coordinator_headers, event_id = _start_planning(
        client, db_session, status=EventStatus.safety_check_passed
    )
    booking, reservation, _ = _arrangements(
        db_session, event_id, organiser, coordinator, capacity=100, linked=False
    )
    booking.expected_attendance = 80
    db_session.commit()

    response = _edit(client, event_id, coordinator_headers, {"expected_attendance": 150})

    assert response.status_code == 200
    assert response.json()["status"] == EventStatus.planning_event
    assert response.json()["affected_venue_bookings"] == ["Main Hall"]
    assert response.json()["affected_equipment_requirements"] == []
    db_session.refresh(booking)
    db_session.refresh(reservation)
    assert booking.status == BookingStatus.pending
    assert booking.expected_attendance is None
    assert reservation.status == EquipmentStatus.reserved

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


def test_ac8_in_planning_attendance_above_capacity_is_not_suitable_with_the_reason(
    client, db_session
):
    organiser, _, coordinator, coordinator_headers, event_id = _start_planning(
        client, db_session
    )
    _arrangements(db_session, event_id, organiser, coordinator, capacity=100)

    assert _edit(
        client, event_id, coordinator_headers, {"expected_attendance": 101}
    ).status_code == 200

    venue = client.get(
        f"/venues/events/{event_id}/suitability", headers=coordinator_headers
    ).json()["venues"][0]
    capacity_check = next(c for c in venue["checks"] if c["category"] == "capacity")
    assert capacity_check["met"] is False
    assert "100" in capacity_check["message"] and "101" in capacity_check["message"]


def test_ac8_frozen_literal_attendance_within_capacity_stays_suitable(client, db_session):
    organiser, _, coordinator, coordinator_headers, event_id = _start_planning(
        client, db_session
    )
    _arrangements(db_session, event_id, organiser, coordinator, capacity=100)

    assert _edit(
        client, event_id, coordinator_headers, {"expected_attendance": 100}
    ).status_code == 200

    venue = client.get(
        f"/venues/events/{event_id}/suitability", headers=coordinator_headers
    ).json()["venues"][0]
    capacity_check = next(c for c in venue["checks"] if c["category"] == "capacity")
    assert capacity_check["met"] is True


# --- AC9 / AC10 -------------------------------------------------------------------


@pytest.mark.parametrize(
    "confirmed_status", [EventStatus.awaiting_safety_check, EventStatus.safety_check_passed]
)
def test_ac9_ac10_major_change_request_approval_returns_confirmed_event_to_planning(
    client, db_session, confirmed_status
):
    organiser, organiser_headers, coordinator, coordinator_headers, event_id = _start_planning(
        client, db_session, status=confirmed_status
    )
    _, reserved, _ = _arrangements(db_session, event_id, organiser, coordinator)
    assert _requirement_status(client, event_id, coordinator_headers) == "reserved"

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
    assert _requirement_status(client, event_id, coordinator_headers) == "requested"

    # AC9: cannot go for a Safety Check until approved and reserved again
    submit = client.post(f"/events/{event_id}/confirm", headers=coordinator_headers)
    assert submit.status_code == 409
    assert "Outstanding" in submit.json()["detail"]
    assert "Main Hall" in submit.json()["detail"]
    assert "Projector" in submit.json()["detail"]
    assert db_session.get(Event, event_id).status == EventStatus.planning_event


def test_ac10_an_equipment_only_change_request_un_reserves_the_requirement(
    client, db_session
):
    organiser, organiser_headers, coordinator, coordinator_headers, event_id = _start_planning(
        client, db_session, status=EventStatus.safety_check_passed
    )
    booking, reserved, _ = _arrangements(db_session, event_id, organiser, coordinator)
    request = client.post(
        f"/events/{event_id}/change-requests",
        headers=organiser_headers,
        json={
            "description": "We need a different projector setup.",
            "proposed_changes": {"equipment_requirements": "Rear projection"},
        },
    ).json()

    assert client.post(
        f"/events/change-requests/{request['id']}/approve",
        headers=coordinator_headers,
        json={},
    ).status_code == 200

    db_session.refresh(reserved)
    db_session.refresh(booking)
    assert reserved.status == EquipmentStatus.requested
    assert _requirement_status(client, event_id, coordinator_headers) == "requested"
    assert booking.status == BookingStatus.approved


def test_ac10_frozen_literal_a_description_change_request_leaves_equipment_reserved(
    client, db_session
):
    organiser, organiser_headers, coordinator, coordinator_headers, event_id = _start_planning(
        client, db_session, status=EventStatus.safety_check_passed
    )
    _, reserved, _ = _arrangements(db_session, event_id, organiser, coordinator)
    request = client.post(
        f"/events/{event_id}/change-requests",
        headers=organiser_headers,
        json={
            "description": "Typo in the description.",
            "proposed_changes": {"description": "Fixed description"},
        },
    ).json()

    assert client.post(
        f"/events/change-requests/{request['id']}/approve",
        headers=coordinator_headers,
        json={},
    ).status_code == 200

    db_session.refresh(reserved)
    assert reserved.status == EquipmentStatus.reserved
    assert _requirement_status(client, event_id, coordinator_headers) == "reserved"
    assert db_session.get(Event, event_id).status == EventStatus.safety_check_passed
