"""Unit cases for the Check Venue Suitability for an Event user story."""

from app.core.roles import Role
from app.models.enums import BookingStatus
from app.models.events import Event
from app.models.user import User
from app.models.venues import VenueBooking
from test_venue_search import _at, _coordinator, _venue


def _assigned_event(db_session, coordinator: User, **overrides) -> Event:
    event = Event(
        name=overrides.pop("name", "Accessibility Workshop"),
        organiser_id=coordinator.id,
        coordinator_id=coordinator.id,
        expected_attendance=overrides.pop("expected_attendance", 80),
        room_layout_preference=overrides.pop("room_layout_preference", "Theatre"),
        accessibility_needs=overrides.pop(
            "accessibility_needs", "Wheelchair access, Hearing loop"
        ),
        venue_requirements=overrides.pop("venue_requirements", "Projector; Stage"),
        **overrides,
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    return event


def test_suitability_marks_a_venue_suitable_when_every_requirement_is_met(
    client, db_session
):
    headers = _coordinator(client, db_session)
    coordinator = db_session.query(User).filter(User.email == "coord@example.com").one()
    venue = _venue(
        db_session,
        "Accessible Hall",
        capacity=100,
        supported_layouts=["Theatre"],
        accessibility_features=["Wheelchair access", "Hearing loop"],
        facilities=["Projector", "Stage"],
    )
    event = _assigned_event(db_session, coordinator)

    response = client.get(
        f"/venues/{venue.id}/suitability/{event.id}",
        headers=headers,
    )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["suitable"] is True
    assert {check["category"] for check in result["checks"]} == {
        "capacity",
        "layout",
        "accessibility",
        "facility",
    }
    assert all(check["met"] for check in result["checks"])


def test_suitability_reports_each_unmet_requirement(client, db_session):
    headers = _coordinator(client, db_session)
    coordinator = db_session.query(User).filter(User.email == "coord@example.com").one()
    venue = _venue(
        db_session,
        "Small Hall",
        capacity=40,
        supported_layouts=["Boardroom"],
        accessibility_features=[],
        facilities=["Projector"],
    )
    event = _assigned_event(db_session, coordinator)

    response = client.get(f"/venues/{venue.id}/suitability/{event.id}", headers=headers)

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["suitable"] is False
    unmet = {(check["category"], check["requirement"]) for check in result["checks"] if not check["met"]}
    assert unmet == {
        ("capacity", "80 people"),
        ("layout", "Theatre"),
        ("accessibility", "Wheelchair access"),
        ("accessibility", "Hearing loop"),
        ("facility", "Stage"),
    }
    assert any("Insufficient capacity" in check["message"] for check in result["checks"])
    assert any("Unsupported layout" in check["message"] for check in result["checks"])
    assert any("Missing facility" in check["message"] for check in result["checks"])


def test_suitability_does_not_claim_success_when_attendance_is_missing(client, db_session):
    headers = _coordinator(client, db_session)
    coordinator = db_session.query(User).filter(User.email == "coord@example.com").one()
    venue = _venue(db_session, "Hall")
    event = _assigned_event(db_session, coordinator, expected_attendance=None)

    response = client.get(f"/venues/{venue.id}/suitability/{event.id}", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["suitable"] is False
    assert response.json()["checks"][0]["met"] is False
    assert "attendance is recorded" in response.json()["checks"][0]["message"]


def test_suitability_only_exposes_events_assigned_to_the_coordinator(client, db_session):
    headers = _coordinator(client, db_session)
    coordinator = db_session.query(User).filter(User.email == "coord@example.com").one()
    other = User(
        name="Other Coordinator",
        email="other-coordinator@example.com",
        password_hash="x",
        role=Role.COORDINATOR.value,
    )
    db_session.add(other)
    db_session.flush()
    venue = _venue(db_session, "Hall")
    event = _assigned_event(db_session, other)

    response = client.get(f"/venues/{venue.id}/suitability/{event.id}", headers=headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "Event not found"


def test_suitability_rejects_non_coordinator_roles(client, db_session):
    venue = _venue(db_session, "Hall")
    password = "password123"
    client.post(
        "/auth/register",
        json={"name": "Venue Staff", "email": "suitability-staff@example.com", "password": password},
    )
    staff = db_session.query(User).filter(User.email == "suitability-staff@example.com").one()
    staff.role = Role.VENUE_STAFF.value
    db_session.commit()
    token = client.post(
        "/auth/login",
        json={"email": "suitability-staff@example.com", "password": password},
    ).json()["access_token"]

    response = client.get(
        f"/venues/{venue.id}/suitability/1",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_event_suitability_checks_each_venue_and_combines_capacity(client, db_session):
    headers = _coordinator(client, db_session)
    coordinator = db_session.query(User).filter(User.email == "coord@example.com").one()
    suitable_venue = _venue(
        db_session,
        "Large Theatre",
        capacity=100,
        supported_layouts=["Theatre"],
        accessibility_features=["Wheelchair access", "Hearing loop"],
        facilities=["Projector", "Stage"],
    )
    unsuitable_venue = _venue(
        db_session,
        "Small Boardroom",
        capacity=10,
        supported_layouts=["Boardroom"],
        accessibility_features=["Wheelchair access"],
        facilities=["Projector"],
    )
    event = _assigned_event(db_session, coordinator)
    db_session.add_all([
        VenueBooking(
            event_id=event.id,
            venue_id=venue.id,
            requested_by=coordinator.id,
            start_time=_at(10),
            end_time=_at(11),
            status=(
                BookingStatus.pending
                if venue is suitable_venue
                else BookingStatus.approved
            ),
        )
        for venue in (suitable_venue, unsuitable_venue)
    ])
    db_session.commit()

    response = client.get(f"/venues/events/{event.id}/suitability", headers=headers)

    assert response.status_code == 200, response.text
    result = response.json()
    assert [(venue["venue_name"], venue["suitable"]) for venue in result["venues"]] == [
        ("Large Theatre", True),
        ("Small Boardroom", False),
    ]
    assert [venue["expected_attendance"] for venue in result["venues"]] == [80, 80]
    assert any(
        check["category"] == "layout" and not check["met"]
        for check in result["venues"][1]["checks"]
    )
    assert result["combined_capacity"] == {
        "required_capacity": 80,
        "available_capacity": 110,
        "met": True,
        "message": "Combined capacity is 110; it must exceed 80 attendees.",
    }
    assert result["suitable"] is False


def test_event_suitability_uses_each_bookings_attendance_and_needs_independently(
    client, db_session
):
    headers = _coordinator(client, db_session)
    coordinator = db_session.query(User).filter(User.email == "coord@example.com").one()
    small_room = _venue(
        db_session,
        "Breakout Room",
        capacity=30,
        supported_layouts=["Classroom"],
        accessibility_features=["Step-free access"],
        facilities=["Whiteboard"],
    )
    large_room = _venue(
        db_session,
        "Main Hall",
        capacity=100,
        supported_layouts=["Theatre"],
        accessibility_features=["Wheelchair access", "Hearing loop"],
        facilities=["Projector", "Stage"],
    )
    event = _assigned_event(db_session, coordinator, expected_attendance=80)
    db_session.add_all(
        [
            VenueBooking(
                event_id=event.id,
                venue_id=small_room.id,
                requested_by=coordinator.id,
                start_time=_at(10),
                end_time=_at(11),
                status=BookingStatus.pending,
                expected_attendance=40,
                room_layout_preference="Classroom",
                accessibility_needs="Step-free access",
                facilities_needs="Whiteboard",
            ),
            VenueBooking(
                event_id=event.id,
                venue_id=large_room.id,
                requested_by=coordinator.id,
                start_time=_at(10),
                end_time=_at(11),
                status=BookingStatus.pending,
                expected_attendance=40,
            ),
        ]
    )
    db_session.commit()

    response = client.get(f"/venues/events/{event.id}/suitability", headers=headers)

    assert response.status_code == 200, response.text
    results = response.json()["venues"]
    assert [result["expected_attendance"] for result in results] == [40, 40]
    assert [result["venue_name"] for result in results] == ["Breakout Room", "Main Hall"]
    assert results[0]["suitable"] is False
    assert results[1]["suitable"] is True
    capacity_failure = next(
        check for check in results[0]["checks"] if check["category"] == "capacity"
    )
    assert capacity_failure["message"] == "Insufficient capacity: Capacity 30 < attendance 40."
    assert all(
        check["met"] for check in results[0]["checks"] if check["category"] != "capacity"
    )
    assert response.json()["combined_capacity"]["required_capacity"] == 80


def test_booking_suitability_endpoint_reloads_only_the_selected_bookings_current_data(
    client, db_session
):
    headers = _coordinator(client, db_session)
    coordinator = db_session.query(User).filter(User.email == "coord@example.com").one()
    first_venue = _venue(
        db_session, "First Room", capacity=50, supported_layouts=["Theatre"]
    )
    second_venue = _venue(
        db_session, "Second Room", capacity=100, supported_layouts=["Boardroom"]
    )
    event = _assigned_event(db_session, coordinator, expected_attendance=80)
    first = VenueBooking(
        event_id=event.id,
        venue_id=first_venue.id,
        requested_by=coordinator.id,
        start_time=_at(10),
        end_time=_at(11),
        status=BookingStatus.pending,
        expected_attendance=40,
        room_layout_preference="Theatre",
    )
    second = VenueBooking(
        event_id=event.id,
        venue_id=second_venue.id,
        requested_by=coordinator.id,
        start_time=_at(10),
        end_time=_at(11),
        status=BookingStatus.pending,
        expected_attendance=60,
        room_layout_preference="Boardroom",
    )
    db_session.add_all([first, second])
    db_session.commit()

    before_second = client.get(
        f"/venues/bookings/{second.id}/suitability", headers=headers
    ).json()
    first.expected_attendance = 70
    first.room_layout_preference = "Classroom"
    db_session.commit()

    updated_first = client.get(
        f"/venues/bookings/{first.id}/suitability", headers=headers
    )
    after_second = client.get(
        f"/venues/bookings/{second.id}/suitability", headers=headers
    ).json()

    assert updated_first.status_code == 200, updated_first.text
    assert updated_first.json()["booking_id"] == first.id
    assert updated_first.json()["expected_attendance"] == 70
    assert any(
        check["message"].startswith("Insufficient capacity")
        for check in updated_first.json()["checks"]
    )
    assert before_second == after_second


def test_booking_suitability_endpoint_hides_bookings_from_other_coordinators(
    client, db_session
):
    headers = _coordinator(client, db_session)
    coordinator = db_session.query(User).filter(User.email == "coord@example.com").one()
    other = User(
        name="Other Coordinator",
        email="other-booking-coordinator@example.com",
        password_hash="x",
        role=Role.COORDINATOR.value,
    )
    db_session.add(other)
    db_session.flush()
    venue = _venue(db_session, "Hall")
    event = _assigned_event(db_session, other)
    booking = VenueBooking(
        event_id=event.id,
        venue_id=venue.id,
        requested_by=coordinator.id,
        start_time=_at(10),
        end_time=_at(11),
        status=BookingStatus.approved,
    )
    db_session.add(booking)
    db_session.commit()

    response = client.get(f"/venues/bookings/{booking.id}/suitability", headers=headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "Active venue booking not found"
