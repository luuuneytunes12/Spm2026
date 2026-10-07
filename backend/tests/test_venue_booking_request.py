"""Tests for the "Submit Venue Booking Request" story (SCRUM-39).

    As an Event Coordinator, I want to submit a venue booking request
    carrying the event's timing and requirements, so that Venue Staff have
    what they need to decide on it.

Test names carry the acceptance criterion they prove (AC1-AC3).
"""

from app.core.roles import Role
from app.models.enums import BookingStatus, EventStatus
from app.models.events import Event
from app.models.venues import Venue, VenueBooking
from tests.event_review_test_helpers import review_setup, user
import pytest

# These tests start from an event that already has a Coordinator; assignment is
# now the Lead's job, so submit alone no longer provides one (see conftest).
pytestmark = pytest.mark.usefixtures("coordinator_auto_assign")


def _venue(db_session, name="Marina Hall", **overrides) -> Venue:
    venue = Venue(
        name=name,
        location="10 Bayfront Ave",
        capacity=250,
        supported_layouts=["Theatre"],
        facilities=["Projector"],
        accessibility_features=["Wheelchair access"],
        **overrides,
    )
    db_session.add(venue)
    db_session.commit()
    return venue


def _approved(client, db_session):
    """An approved event assigned to a coordinator, plus a venue-staff user."""
    organiser, org_h, coordinator, coord_h, event_id = review_setup(client, db_session)
    event = db_session.get(Event, event_id)
    event.room_layout_preference = "Theatre"
    event.status = EventStatus.event_approved
    db_session.commit()
    _, staff_h = user(client, db_session, Role.VENUE_STAFF, "staff@example.com", "Venue Staff")
    return coordinator, coord_h, staff_h, event_id


def _submit(client, headers, event_id, venue_id):
    return client.post(f"/venue-bookings/events/{event_id}", json={"venue_id": venue_id}, headers=headers)


# --- AC1: no venue selected -> not submitted, error shown -------------------


def test_scrum39_ac1_no_venue_selected_is_refused_and_nothing_is_saved(client, db_session):
    _, coord_h, staff_h, event_id = _approved(client, db_session)
    res = client.post(f"/venue-bookings/events/{event_id}", json={}, headers=coord_h)
    assert res.status_code == 422
    assert "Select a venue" in res.json()["detail"]
    assert db_session.query(VenueBooking).count() == 0
    assert client.get("/venue-bookings/queue", headers=staff_h).json() == []


def test_scrum39_ac1_an_unknown_or_inactive_venue_is_refused(client, db_session):
    _, coord_h, _, event_id = _approved(client, db_session)
    inactive = _venue(db_session, "Closed Hall", is_active=False)
    assert _submit(client, coord_h, event_id, 9999).status_code == 422
    assert _submit(client, coord_h, event_id, inactive.id).status_code == 422
    assert db_session.query(VenueBooking).count() == 0


# --- AC2: appears in the Venue Staff review queue ---------------------------


def test_scrum39_ac2_a_submitted_request_appears_in_the_venue_staff_queue(client, db_session):
    _, coord_h, staff_h, event_id = _approved(client, db_session)
    venue = _venue(db_session)
    res = _submit(client, coord_h, event_id, venue.id)
    assert res.status_code == 201
    assert res.json()["status"] == BookingStatus.pending

    queue = client.get("/venue-bookings/queue", headers=staff_h).json()
    assert [b["id"] for b in queue] == [res.json()["id"]]


def test_scrum39_ac2_a_decided_request_leaves_the_queue(client, db_session):
    _, coord_h, staff_h, event_id = _approved(client, db_session)
    res = _submit(client, coord_h, event_id, _venue(db_session).id)
    booking = db_session.get(VenueBooking, res.json()["id"])
    booking.status = BookingStatus.approved
    db_session.commit()
    assert client.get("/venue-bookings/queue", headers=staff_h).json() == []


# --- AC3: the request carries everything Venue Staff need -------------------


def test_scrum39_ac3_the_request_carries_venue_timing_attendance_layout_and_needs(client, db_session):
    coordinator, coord_h, staff_h, event_id = _approved(client, db_session)
    venue = _venue(db_session)
    booking_id = _submit(client, coord_h, event_id, venue.id).json()["id"]

    body = client.get(f"/venue-bookings/{booking_id}", headers=staff_h).json()
    assert body["venue"]["name"] == "Marina Hall"
    assert body["start_time"].startswith("2026-11-02T09:00")
    assert body["end_time"].startswith("2026-11-02T17:00")
    assert body["expected_attendance"] == 120
    assert body["room_layout_preference"] == "Theatre"
    assert body["accessibility_needs"] == "Step-free access"
    assert body["venue_requirements"] == "Main hall"
    assert body["requested_by"]["name"] == coordinator.name
    assert body["created_at"]


# --- Access control ----------------------------------------------------------


def test_only_a_coordinator_can_submit(client, db_session):
    _, _, staff_h, event_id = _approved(client, db_session)
    venue = _venue(db_session)
    _, org_h = user(client, db_session, Role.ORGANISER, "o2@example.com", "Other Organiser")
    assert _submit(client, staff_h, event_id, venue.id).status_code == 403
    assert _submit(client, org_h, event_id, venue.id).status_code == 403
    assert client.post(f"/venue-bookings/events/{event_id}", json={"venue_id": venue.id}).status_code == 401


def test_a_coordinator_cannot_book_for_an_event_assigned_to_someone_else(client, db_session):
    _, _, _, event_id = _approved(client, db_session)
    venue = _venue(db_session)
    _, other_h = user(client, db_session, Role.COORDINATOR, "c2@example.com", "Other Coordinator")
    assert _submit(client, other_h, event_id, venue.id).status_code == 404
    assert client.get(f"/venue-bookings/events/{event_id}", headers=other_h).status_code == 404
    assert db_session.query(VenueBooking).count() == 0


def test_the_queue_and_detail_are_for_venue_staff_only(client, db_session):
    _, coord_h, staff_h, event_id = _approved(client, db_session)
    booking_id = _submit(client, coord_h, event_id, _venue(db_session).id).json()["id"]
    assert client.get("/venue-bookings/queue", headers=coord_h).status_code == 403
    assert client.get(f"/venue-bookings/{booking_id}", headers=coord_h).status_code == 403
    assert client.get("/venue-bookings/queue").status_code == 401
    assert client.get("/venue-bookings/9999", headers=staff_h).status_code == 404


# --- State and duplicates ----------------------------------------------------


def test_a_venue_cannot_be_requested_before_the_event_is_approved(client, db_session):
    _, coord_h, _, event_id = _approved(client, db_session)
    db_session.get(Event, event_id).status = EventStatus.under_review
    db_session.commit()
    res = _submit(client, coord_h, event_id, _venue(db_session).id)
    assert res.status_code == 409
    assert db_session.query(VenueBooking).count() == 0


def test_an_event_can_request_multiple_venues_but_not_duplicate_a_live_venue(
    client, db_session
):
    _, coord_h, _, event_id = _approved(client, db_session)
    venue = _venue(db_session)
    other_venue = _venue(db_session, "Hall B")
    assert _submit(client, coord_h, event_id, venue.id).status_code == 201
    assert _submit(client, coord_h, event_id, other_venue.id).status_code == 201
    assert _submit(client, coord_h, event_id, venue.id).status_code == 409
    assert db_session.query(VenueBooking).count() == 2


def test_after_a_rejection_the_coordinator_may_request_another_venue(client, db_session):
    _, coord_h, _, event_id = _approved(client, db_session)
    first = _submit(client, coord_h, event_id, _venue(db_session).id).json()["id"]
    db_session.get(VenueBooking, first).status = BookingStatus.rejected
    db_session.commit()
    assert _submit(client, coord_h, event_id, _venue(db_session, "Hall B").id).status_code == 201
    listed = client.get(f"/venue-bookings/events/{event_id}", headers=coord_h).json()
    assert [b["venue"]["name"] for b in listed] == ["Hall B", "Marina Hall"]
