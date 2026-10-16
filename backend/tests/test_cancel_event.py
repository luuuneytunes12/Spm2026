"""Tests for cancelling an Event assigned to the signed-in Coordinator."""

import pytest

from app.core.roles import Role
from app.models.enums import BookingStatus, EquipmentStatus, EventStatus
from app.models.equipment import (
    CoordinatorEquipmentRequirement,
    Equipment,
    EquipmentRequest,
    RequirementReservationLink,
)
from app.models.events import Event, EventStatusHistory
from app.models.venues import VenueBooking
from app.domain.requirement_progress import RequirementReservationLinks, RequirementStatus
from event_review_test_helpers import review_setup, user
from tests.test_venue_booking_request import _venue

pytestmark = pytest.mark.usefixtures("coordinator_auto_assign")


def test_cancellation_requires_a_non_blank_reason_and_keeps_event_unchanged(client, db_session):
    _, _, _, coordinator_headers, event_id = review_setup(client, db_session)

    for payload in ({}, {"reason": "   "}):
        response = client.post(f"/events/{event_id}/cancel", json=payload, headers=coordinator_headers)
        assert response.status_code == 422
        assert db_session.get(Event, event_id).status == EventStatus.under_review


@pytest.mark.parametrize(
    "terminal_status",
    [
        EventStatus.event_completed,
        EventStatus.event_rejected,
        EventStatus.event_cancelled,
    ],
)
def test_terminal_event_cannot_be_cancelled(client, db_session, terminal_status):
    _, _, _, coordinator_headers, event_id = review_setup(client, db_session)
    event = db_session.get(Event, event_id)
    event.status = terminal_status
    db_session.commit()

    response = client.post(
        f"/events/{event_id}/cancel",
        json={"reason": "No longer proceeding."},
        headers=coordinator_headers,
    )

    assert response.status_code == 409
    assert "cannot be cancelled" in response.json()["detail"]
    assert db_session.get(Event, event_id).status is terminal_status


def test_only_the_assigned_coordinator_can_cancel(client, db_session):
    _, _, _, _, event_id = review_setup(client, db_session)
    _, other_headers = user(
        client,
        db_session,
        Role.COORDINATOR,
        "other-coordinator@example.com",
        "Other Coordinator",
    )

    response = client.post(
        f"/events/{event_id}/cancel",
        json={"reason": "The event will not proceed."},
        headers=other_headers,
    )

    assert response.status_code == 403
    assert "Only the assigned Event Coordinator" in response.json()["detail"]
    assert db_session.get(Event, event_id).status == EventStatus.under_review


def test_cancellation_refuses_an_unassigned_event(client, db_session):
    _, _, _, coordinator_headers, event_id = review_setup(client, db_session)
    event = db_session.get(Event, event_id)
    event.coordinator_id = None
    db_session.commit()

    response = client.post(
        f"/events/{event_id}/cancel",
        json={"reason": "The event will not proceed."},
        headers=coordinator_headers,
    )

    assert response.status_code == 409
    assert "must be assigned" in response.json()["detail"]
    assert db_session.get(Event, event_id).status == EventStatus.under_review


def test_cancellation_records_reason_actor_and_time_and_releases_event_reservations(
    client, db_session
):
    organiser, organiser_headers, coordinator, coordinator_headers, event_id = review_setup(
        client, db_session
    )
    event = db_session.get(Event, event_id)
    event.status = EventStatus.planning_event

    item = Equipment(name="Projector", category="Projection", total_quantity=10)
    other_item = Equipment(name="Microphone", category="Audio", total_quantity=4)
    db_session.add_all((item, other_item))
    db_session.flush()
    reserved_line = EquipmentRequest(
        event_id=event_id,
        equipment_id=item.id,
        quantity_requested=3,
        status=EquipmentStatus.reserved,
    )
    requested_line = EquipmentRequest(
        event_id=event_id,
        equipment_id=other_item.id,
        quantity_requested=1,
        status=EquipmentStatus.requested,
    )
    requirement = CoordinatorEquipmentRequirement(
        event_id=event_id,
        category="Projection",
        quantity_needed=3,
        status=EquipmentStatus.requested,
        created_by=coordinator.id,
    )
    db_session.add_all((reserved_line, requested_line, requirement))
    db_session.flush()
    db_session.add(
        RequirementReservationLink(
            requirement_id=requirement.id,
            event_id=event_id,
            equipment_id=item.id,
        )
    )

    hall = _venue(db_session, "Main Hall")
    room = _venue(db_session, "Breakout Room")
    bookings = [
        VenueBooking(
            event_id=event_id,
            venue_id=venue.id,
            requested_by=coordinator.id,
            start_time=event.proposed_start,
            end_time=event.proposed_end,
            status=booking_status,
            expires_at=event.proposed_end if booking_status is BookingStatus.tentative_hold else None,
        )
        for venue, booking_status in (
            (hall, BookingStatus.approved),
            (room, BookingStatus.tentative_hold),
        )
    ]
    db_session.add_all(bookings)
    db_session.commit()

    reason = "The keynote speaker is unavailable."
    response = client.post(
        f"/events/{event_id}/cancel",
        json={"reason": reason},
        headers=coordinator_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == EventStatus.event_cancelled.value
    db_session.refresh(reserved_line)
    db_session.refresh(requested_line)
    assert reserved_line.status is EquipmentStatus.cancelled
    assert reason in reserved_line.notes
    assert requested_line.status is EquipmentStatus.requested
    progress = RequirementReservationLinks(db_session).progress_for(requirement)
    assert progress.status is RequirementStatus.AVAILABLE
    assert progress.was_reserved == 3
    assert progress.reserved == 0
    for booking in bookings:
        db_session.refresh(booking)
        assert booking.status is BookingStatus.cancelled

    history = (
        db_session.query(EventStatusHistory)
        .filter_by(event_id=event_id, to_status=EventStatus.event_cancelled.value)
        .one()
    )
    assert history.from_status == EventStatus.planning_event.value
    assert history.note == reason
    assert history.changed_by == coordinator.id

    activity = client.get(f"/events/{event_id}/activity", headers=organiser_headers)
    assert activity.status_code == 200
    cancellation = next(
        entry for entry in activity.json() if entry["to_status"] == EventStatus.event_cancelled.value
    )
    assert cancellation["note"] == reason
    assert cancellation["changed_by_name"] == coordinator.name
    assert cancellation["created_at"]

    _, tech_headers = user(
        client, db_session, Role.TECH_SUPPORT, "tech@example.com", "Tess Tech"
    )
    catalogue = client.get("/equipment", headers=tech_headers)
    assert catalogue.status_code == 200
    projector = next(row for row in catalogue.json()["items"] if row["id"] == item.id)
    assert projector["available_quantity"] == 10

    next_event = Event(
        name="Replacement Conference",
        organiser_id=organiser.id,
        status=EventStatus.event_approved,
        proposed_start=event.proposed_start,
        proposed_end=event.proposed_end,
    )
    db_session.add(next_event)
    db_session.flush()
    db_session.add(
        EquipmentRequest(
            event_id=next_event.id,
            equipment_id=item.id,
            quantity_requested=3,
            status=EquipmentStatus.requested,
        )
    )
    db_session.commit()
    reservation = client.post(
        "/equipment-reservations",
        json={"event_id": next_event.id, "equipment_id": item.id},
        headers=tech_headers,
    )
    assert reservation.status_code == 200
    assert reservation.json()["quantity"] == 3
