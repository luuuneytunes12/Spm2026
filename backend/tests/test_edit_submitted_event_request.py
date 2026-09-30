"""Acceptance tests for requesting changes to a submitted event."""

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
from app.models.equipment import Equipment, EquipmentRequest
from app.models.events import Event, EventChangeRequest
from app.models.venues import Venue, VenueBooking
from event_review_test_helpers import COMPLETE, review_setup, user


def test_change_request_is_pending_and_does_not_mutate_event(client, db_session):
    _, organiser_headers, _, coordinator_headers, event_id = review_setup(client, db_session)

    response = client.post(
        f"/events/{event_id}/change-requests",
        json={
            "description": "The expected attendance has increased.",
            "proposed_changes": {"expected_attendance": 160},
        },
        headers=organiser_headers,
    )

    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    assert response.json()["proposed_changes"] == {"expected_attendance": 160}
    assert response.json()["important_change"] is True
    assert db_session.get(Event, event_id).expected_attendance == COMPLETE["expected_attendance"]
    assert db_session.query(EventChangeRequest).one().status == ChangeRequestStatus.pending
    assigned_summary = client.get("/events/assigned", headers=coordinator_headers).json()[0]
    assert assigned_summary["has_pending_change_request"] is True


def test_organiser_cannot_submit_another_request_while_one_is_pending(client, db_session):
    _, organiser_headers, _, _, event_id = review_setup(client, db_session)
    first = {
        "description": "Increase attendance",
        "proposed_changes": {"expected_attendance": 160},
    }
    assert client.post(
        f"/events/{event_id}/change-requests", json=first, headers=organiser_headers
    ).status_code == 201

    second = client.post(
        f"/events/{event_id}/change-requests",
        json={"description": "Change the venue", "proposed_changes": {"venue_requirements": "Auditorium"}},
        headers=organiser_headers,
    )

    assert second.status_code == 409
    assert db_session.query(EventChangeRequest).count() == 1
    summary = client.get("/events", headers=organiser_headers).json()[0]
    assert summary["has_pending_change_request"] is True


def test_coordinator_must_decide_pending_change_before_event(client, db_session):
    _, organiser_headers, _, coordinator_headers, event_id = review_setup(client, db_session)
    client.post(
        f"/events/{event_id}/change-requests",
        json={"description": "Correct a typo", "proposed_changes": {"name": "Corrected title"}},
        headers=organiser_headers,
    )

    response = client.post(f"/events/{event_id}/approve", headers=coordinator_headers)

    assert response.status_code == 409
    assert db_session.get(Event, event_id).status == EventStatus.under_review


def test_coordinator_approval_applies_proposed_values(client, db_session):
    _, organiser_headers, _, coordinator_headers, event_id = review_setup(client, db_session)
    requested = client.post(
        f"/events/{event_id}/change-requests",
        json={"description": "Correct the title", "proposed_changes": {"name": "Corrected title"}},
        headers=organiser_headers,
    ).json()

    response = client.post(
        f"/events/change-requests/{requested['id']}/approve",
        json={},
        headers=coordinator_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert db_session.get(Event, event_id).name == "Corrected title"


def test_important_change_shows_existing_bookings_and_reservations(client, db_session):
    _, organiser_headers, organiser, _, event_id = review_setup(client, db_session)
    venue = Venue(name="Main Hall", location="Building A", capacity=300)
    equipment = Equipment(
        name="Projector", total_quantity=4, operational_status=EquipmentOperationalStatus.available
    )
    db_session.add_all([venue, equipment])
    db_session.commit()
    db_session.add_all(
        [
            VenueBooking(
                event_id=event_id,
                venue_id=venue.id,
                requested_by=organiser.id,
                start_time=datetime(2026, 11, 2, 9, tzinfo=timezone.utc),
                end_time=datetime(2026, 11, 2, 17, tzinfo=timezone.utc),
                status=BookingStatus.approved,
            ),
            EquipmentRequest(
                event_id=event_id,
                equipment_id=equipment.id,
                quantity_requested=2,
                status=EquipmentStatus.reserved,
            ),
        ]
    )
    db_session.commit()

    response = client.post(
        f"/events/{event_id}/change-requests",
        json={"description": "Attendance changed", "proposed_changes": {"expected_attendance": 180}},
        headers=organiser_headers,
    )

    body = response.json()
    assert body["important_change"] is True
    assert body["venue_bookings_to_reconsider"][0]["venue_name"] == "Main Hall"
    assert body["equipment_reservations_to_reconsider"][0]["equipment_name"] == "Projector"


def test_coordinator_approval_applies_equipment_proposal(client, db_session):
    _, organiser_headers, _, coordinator_headers, event_id = review_setup(client, db_session)
    equipment = Equipment(name="Projector", total_quantity=4)
    db_session.add(equipment)
    db_session.commit()
    requested = client.post(
        f"/events/{event_id}/change-requests",
        json={
            "description": "Add projection equipment",
            "proposed_changes": {
                "equipment_items": [{"equipment_id": equipment.id, "quantity_requested": 2}]
            },
        },
        headers=organiser_headers,
    ).json()

    response = client.post(
        f"/events/change-requests/{requested['id']}/approve", json={}, headers=coordinator_headers
    )

    assert response.status_code == 200
    line = db_session.query(EquipmentRequest).filter_by(event_id=event_id).one()
    assert line.equipment_id == equipment.id
    assert line.quantity_requested == 2


@pytest.mark.parametrize(
    "terminal_status", [EventStatus.rejected, EventStatus.completed, EventStatus.cancelled]
)
def test_terminal_event_cannot_receive_change_request(client, db_session, terminal_status):
    _, organiser_headers, _, _, event_id = review_setup(client, db_session)
    event = db_session.get(Event, event_id)
    event.status = terminal_status
    db_session.commit()

    response = client.post(
        f"/events/{event_id}/change-requests",
        json={"description": "Change", "proposed_changes": {"name": "New name"}},
        headers=organiser_headers,
    )

    assert response.status_code == 409
    assert db_session.query(EventChangeRequest).count() == 0


def test_coordinator_rejection_keeps_values_and_exposes_reason(client, db_session):
    _, organiser_headers, _, coordinator_headers, event_id = review_setup(client, db_session)
    requested = client.post(
        f"/events/{event_id}/change-requests",
        json={"description": "Move the date", "proposed_changes": {"expected_attendance": 200}},
        headers=organiser_headers,
    ).json()

    response = client.post(
        f"/events/change-requests/{requested['id']}/reject",
        json={"review_notes": "The venue capacity cannot support that number."},
        headers=coordinator_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert response.json()["review_notes"] == "The venue capacity cannot support that number."
    assert db_session.get(Event, event_id).expected_attendance == COMPLETE["expected_attendance"]
    organiser_result = client.get(
        f"/events/{event_id}/change-requests", headers=organiser_headers
    ).json()[0]
    assert organiser_result["review_notes"] == "The venue capacity cannot support that number."


def test_non_owner_cannot_request_event_changes(client, db_session):
    _, organiser_headers, _, _, event_id = review_setup(client, db_session)
    _, other_headers = user(client, db_session, Role.ORGANISER, "other@example.com", "Other")

    response = client.post(
        f"/events/{event_id}/change-requests",
        json={"description": "Change", "proposed_changes": {"name": "Not mine"}},
        headers=other_headers,
    )

    assert response.status_code == 404
    assert db_session.query(EventChangeRequest).count() == 0


def test_partial_date_change_cannot_conflict_with_existing_date(client, db_session):
    _, organiser_headers, _, _, event_id = review_setup(client, db_session)

    response = client.post(
        f"/events/{event_id}/change-requests",
        json={
            "description": "Move the start later",
            "proposed_changes": {"proposed_start": "2026-11-02T18:00:00Z"},
        },
        headers=organiser_headers,
    )

    assert response.status_code == 422
    assert db_session.query(EventChangeRequest).count() == 0


@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_decided_request_cannot_be_edited(client, db_session, decision):
    _, organiser_headers, _, coordinator_headers, event_id = review_setup(client, db_session)
    payload = {"reason": "The requested venue is unavailable."} if decision == "reject" else None
    assert (
        client.post(f"/events/{event_id}/{decision}", json=payload, headers=coordinator_headers).status_code
        == 200
    )

    response = client.post(
        f"/events/{event_id}/change-requests",
        json={"description": "Change", "proposed_changes": {"name": "Changed after decision"}},
        headers=organiser_headers,
    )

    assert response.status_code == 409
    assert db_session.get(Event, event_id).name == COMPLETE["name"]
    expected_status = EventStatus.approved if decision == "approve" else EventStatus.rejected
    assert db_session.get(Event, event_id).status == expected_status