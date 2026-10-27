"""Event cancellation and equipment release against real PostgreSQL."""

from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

from app.core.roles import Role
from app.domain.requirement_progress import RequirementReservationLinks, RequirementStatus
from app.models.enums import ACTIVE_ASSIGNMENT_STATUSES, BookingStatus, EquipmentStatus, EventStatus
from app.models.equipment import (
    CoordinatorEquipmentRequirement,
    Equipment,
    EquipmentRequest,
    RequirementReservationLink,
)
from app.models.events import Event, EventStatusHistory
from app.models.venues import Venue, VenueBooking
from tests.integration.test_coordinator_concurrency_postgres import THREADS, race

pytestmark = pytest.mark.integration

START = datetime(2026, 11, 2, 9, tzinfo=timezone.utc)
END = datetime(2026, 11, 2, 17, tzinfo=timezone.utc)


def _event(db, organiser, coordinator, *, status=EventStatus.planning_event, name="Conference"):
    event = Event(
        name=name,
        organiser_id=organiser.id,
        coordinator_id=coordinator.id,
        status=status,
        proposed_start=START,
        proposed_end=END,
        expected_attendance=120,
    )
    db.add(event)
    db.flush()
    return event


def test_cancel_event_persists_status_reason_releases_arrangements_and_frees_stock(
    client, make_user, db
):
    organiser, organiser_headers = make_user(Role.ORGANISER, "org@connectsphere.test", "Priya Menon")
    coordinator, coordinator_headers = make_user(
        Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan"
    )
    tech, tech_headers = make_user(Role.TECH_SUPPORT, "tech@connectsphere.test", "Tess Tech")
    venue_staff, _ = make_user(
        Role.VENUE_STAFF, "venue@connectsphere.test", "Vera Staff"
    )
    event = _event(db, organiser, coordinator)
    item = Equipment(name="Projector", category="Projection", total_quantity=8)
    venues = [
        Venue(name="Main Hall", location="Building A", capacity=250),
        Venue(name="Breakout Room", location="Building B", capacity=80),
    ]
    requirement = CoordinatorEquipmentRequirement(
        event_id=event.id,
        category="Projection",
        quantity_needed=5,
        status=EquipmentStatus.requested,
        created_by=coordinator.id,
    )
    db.add_all([item, *venues, requirement])
    db.flush()
    reserved_line = EquipmentRequest(
        event_id=event.id,
        equipment_id=item.id,
        quantity_requested=5,
        status=EquipmentStatus.reserved,
        reviewed_by=tech.id,
    )
    db.add(reserved_line)
    db.add(
        RequirementReservationLink(
            requirement_id=requirement.id,
            event_id=event.id,
            equipment_id=item.id,
        )
    )
    bookings = [
        VenueBooking(
            event_id=event.id,
            venue_id=venue.id,
            requested_by=coordinator.id,
            reviewed_by=venue_staff.id if booking_status is BookingStatus.approved else None,
            start_time=START,
            end_time=END,
            status=booking_status,
            expires_at=END if booking_status is BookingStatus.tentative_hold else None,
        )
        for venue, booking_status in zip(
            venues, (BookingStatus.approved, BookingStatus.tentative_hold), strict=True
        )
    ]
    db.add_all(bookings)
    db.commit()

    reason = "The keynote speaker is unavailable."
    response = client.post(
        f"/events/{event.id}/cancel",
        json={"reason": reason},
        headers=coordinator_headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == EventStatus.event_cancelled.value
    db.expire_all()
    assert db.get(Event, event.id).status is EventStatus.event_cancelled
    db.refresh(reserved_line)
    assert reserved_line.status is EquipmentStatus.cancelled
    assert reason in reserved_line.notes
    for booking in bookings:
        db.refresh(booking)
        assert booking.status is BookingStatus.released

    [history] = db.query(EventStatusHistory).filter_by(event_id=event.id, changed_by=coordinator.id).all()
    assert history.from_status == EventStatus.planning_event.value
    assert history.to_status == EventStatus.event_cancelled.value
    assert history.note == reason
    assert history.changed_by == coordinator.id
    assert history.created_at is not None

    progress = RequirementReservationLinks(db).progress_for(requirement)
    assert progress.status is RequirementStatus.AVAILABLE
    assert progress.was_reserved == 5
    assert progress.reserved == 0

    activity = client.get(f"/events/{event.id}/activity", headers=organiser_headers)
    assert activity.status_code == 200
    cancellation = next(
        row for row in activity.json() if row["from_status"] == EventStatus.planning_event.value
    )
    assert cancellation["note"] == reason
    assert cancellation["changed_by_name"] == coordinator.name
    assert cancellation["created_at"]

    catalogue = client.get("/equipment", headers=tech_headers)
    assert catalogue.status_code == 200
    projector = next(row for row in catalogue.json()["items"] if row["id"] == item.id)
    assert projector["available_quantity"] == 8

    replacement = _event(
        db, organiser, coordinator, status=EventStatus.event_approved, name="Replacement Event"
    )
    replacement_line = EquipmentRequest(
        event_id=replacement.id,
        equipment_id=item.id,
        quantity_requested=5,
        status=EquipmentStatus.requested,
    )
    db.add(replacement_line)
    db.commit()
    reservation = client.post(
        "/equipment-reservations",
        json={"event_id": replacement.id, "equipment_id": item.id},
        headers=tech_headers,
    )
    assert reservation.status_code == 200, reservation.text
    assert reservation.json()["quantity"] == 5


def test_event_completed_releases_reserved_stock_on_postgres(client, make_user, db):
    organiser, _ = make_user(Role.ORGANISER, "org@connectsphere.test", "Priya Menon")
    coordinator, _ = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")
    tech, tech_headers = make_user(Role.TECH_SUPPORT, "tech@connectsphere.test", "Tess Tech")
    item = Equipment(name="Microphone", category="Audio", total_quantity=6)
    db.add(item)
    db.flush()
    event = _event(db, organiser, coordinator, status=EventStatus.event_completed)
    event.proposed_start = datetime.now(timezone.utc) + timedelta(days=1)
    event.proposed_end = event.proposed_start + timedelta(hours=8)
    db.add(
        EquipmentRequest(
            event_id=event.id,
            equipment_id=item.id,
            quantity_requested=4,
            status=EquipmentStatus.reserved,
            reviewed_by=tech.id,
        )
    )
    db.commit()

    catalogue = client.get("/equipment", headers=tech_headers)
    assert catalogue.status_code == 200
    microphone = next(row for row in catalogue.json()["items"] if row["id"] == item.id)
    assert microphone["available_quantity"] == 6


def test_every_active_assigned_status_can_be_cancelled_on_postgres(client, make_user, db):
    organiser, _ = make_user(Role.ORGANISER, "org@connectsphere.test", "Priya Menon")
    coordinator, coordinator_headers = make_user(
        Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan"
    )

    for active_status in ACTIVE_ASSIGNMENT_STATUSES:
        event = _event(db, organiser, coordinator, status=active_status, name=active_status.value)
        db.commit()

        response = client.post(
            f"/events/{event.id}/cancel",
            json={"reason": "The event will not proceed."},
            headers=coordinator_headers,
        )

        assert response.status_code == 200, f"{active_status.value}: {response.text}"
        assert response.json()["status"] == EventStatus.event_cancelled.value


@pytest.mark.parametrize(
    ("status", "expected_code"),
    [
        (EventStatus.event_completed, 409),
        (EventStatus.event_rejected, 409),
        (EventStatus.event_cancelled, 409),
        (EventStatus.planning_event, 422),
    ],
)
def test_cancellation_refusals_leave_postgres_event_and_history_unchanged(
    client, make_user, db, status, expected_code
):
    organiser, _ = make_user(Role.ORGANISER, "org@connectsphere.test", "Priya Menon")
    coordinator, coordinator_headers = make_user(
        Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan"
    )
    event = _event(db, organiser, coordinator, status=status)
    db.commit()

    body = {"reason": "   "} if expected_code == 422 else {"reason": "The event will not proceed."}
    response = client.post(
        f"/events/{event.id}/cancel",
        json=body,
        headers=coordinator_headers,
    )

    assert response.status_code == expected_code
    db.expire_all()
    assert db.get(Event, event.id).status is status
    assert (
        db.query(EventStatusHistory)
        .filter_by(event_id=event.id, to_status=EventStatus.event_cancelled.value)
        .count()
        == 0
    )


def test_another_coordinator_cannot_cancel_an_assigned_postgres_event(client, make_user, db):
    organiser, _ = make_user(Role.ORGANISER, "org@connectsphere.test", "Priya Menon")
    coordinator, _ = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")
    _, other_headers = make_user(Role.COORDINATOR, "lee@connectsphere.test", "Lee Wong")
    event = _event(db, organiser, coordinator)
    db.commit()

    response = client.post(
        f"/events/{event.id}/cancel",
        json={"reason": "The event will not proceed."},
        headers=other_headers,
    )

    assert response.status_code == 403
    db.expire_all()
    assert db.get(Event, event.id).status is EventStatus.planning_event
    assert db.query(EventStatusHistory).filter_by(event_id=event.id).count() == 0


def test_concurrent_event_cancellation_commits_only_one_transition(
    make_client, make_user, db
):
    organiser, _ = make_user(Role.ORGANISER, "org@connectsphere.test", "Priya Menon")
    coordinator, coordinator_headers = make_user(
        Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan"
    )
    event = _event(db, organiser, coordinator)
    db.commit()
    event_id = event.id

    responses = race(
        make_client,
        THREADS,
        lambda c: c.post(
            f"/events/{event_id}/cancel",
            json={"reason": "The event will not proceed."},
            headers=coordinator_headers,
        ),
    )

    assert sorted(response.status_code for response in responses) == [200] + [409] * (THREADS - 1)
    db.expire_all()
    assert db.get(Event, event_id).status is EventStatus.event_cancelled
    assert (
        db.query(EventStatusHistory)
        .filter_by(event_id=event_id, to_status=EventStatus.event_cancelled.value)
        .count()
        == 1
    )


def test_cancellation_racing_equipment_reservation_cannot_leave_reserved_stock(
    make_client, make_user, db
):
    organiser, _ = make_user(Role.ORGANISER, "org@connectsphere.test", "Priya Menon")
    coordinator, coordinator_headers = make_user(
        Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan"
    )
    _, tech_headers = make_user(Role.TECH_SUPPORT, "tech@connectsphere.test", "Tess Tech")
    event = _event(db, organiser, coordinator)
    item = Equipment(name="Projector", category="Projection", total_quantity=8)
    db.add(item)
    db.flush()
    line = EquipmentRequest(
        event_id=event.id,
        equipment_id=item.id,
        quantity_requested=5,
        status=EquipmentStatus.requested,
    )
    db.add(line)
    db.commit()
    event_id, equipment_id = event.id, item.id

    barrier = threading.Barrier(2)
    clients = [make_client(), make_client()]

    def cancel(client):
        barrier.wait()
        return client.post(
            f"/events/{event_id}/cancel",
            json={"reason": "The event will not proceed."},
            headers=coordinator_headers,
        )

    def reserve(client):
        barrier.wait()
        return client.post(
            "/equipment-reservations",
            json={"event_id": event_id, "equipment_id": equipment_id},
            headers=tech_headers,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        cancel_future = pool.submit(cancel, clients[0])
        reserve_future = pool.submit(reserve, clients[1])
        cancellation, reservation = cancel_future.result(), reserve_future.result()

    assert cancellation.status_code == 200, cancellation.text
    assert reservation.status_code in (200, 409), reservation.text
    db.expire_all()
    assert db.get(Event, event_id).status is EventStatus.event_cancelled
    assert db.get(EquipmentRequest, line.id).status is not EquipmentStatus.reserved
    assert (
        db.query(EventStatusHistory)
        .filter_by(event_id=event_id, to_status=EventStatus.event_cancelled.value)
        .count()
        == 1
    )


def test_cancellation_racing_venue_approval_cannot_leave_a_live_booking(
    make_client, make_user, db
):
    organiser, _ = make_user(Role.ORGANISER, "org@connectsphere.test", "Priya Menon")
    coordinator, coordinator_headers = make_user(
        Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan"
    )
    _, venue_headers = make_user(Role.VENUE_STAFF, "venue@connectsphere.test", "Vera Staff")
    event = _event(db, organiser, coordinator)
    venue = Venue(name="Main Hall", location="Building A", capacity=250)
    db.add(venue)
    db.flush()
    booking = VenueBooking(
        event_id=event.id,
        venue_id=venue.id,
        requested_by=coordinator.id,
        start_time=START,
        end_time=END,
        status=BookingStatus.pending,
    )
    db.add(booking)
    db.commit()
    event_id, booking_id = event.id, booking.id

    barrier = threading.Barrier(2)
    clients = [make_client(), make_client()]

    def cancel(client):
        barrier.wait()
        return client.post(
            f"/events/{event_id}/cancel",
            json={"reason": "The event will not proceed."},
            headers=coordinator_headers,
        )

    def approve(client):
        barrier.wait()
        return client.post(f"/venue-bookings/{booking_id}/approve", headers=venue_headers)

    with ThreadPoolExecutor(max_workers=2) as pool:
        cancel_future = pool.submit(cancel, clients[0])
        approve_future = pool.submit(approve, clients[1])
        cancellation, approval = cancel_future.result(), approve_future.result()

    assert cancellation.status_code == 200, cancellation.text
    assert approval.status_code in (200, 409), approval.text
    db.expire_all()
    assert db.get(Event, event_id).status is EventStatus.event_cancelled
    assert db.get(VenueBooking, booking_id).status is BookingStatus.released
