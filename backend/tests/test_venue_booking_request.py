"""Tests for the "Submit Venue Booking Request" story (SCRUM-39).

    As an Event Coordinator, I want to submit a Venue Booking request for one
    or more Venues, carrying the Event's timing and requirements, so that
    Venue Staff have what they need to decide on each Venue.

Test names carry the acceptance criterion they prove (SCRUM-39 AC1-AC6):
    AC1  no Venue selected: not submitted, an error is shown
    AC2  one or more Venues: a separate Venue Booking for each, in the queue
    AC3  the first booking moves an 'Event Approved' Event to 'Planning Event'
    AC4  Venue Staff see the Event, Venue, date/time, attendance and the needs
         entered for that Venue
    AC5  every booking is listed under its Event with its own status
    AC6  an Event not assigned to the Coordinator, or not 'Event Approved' or
         'Planning Event': refused, no booking created
"""

from app.core.roles import Role
from app.models.enums import BookingStatus, EventStatus
from app.models.events import Event, EventStatusHistory
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


def _submit_many(client, headers, event_id, venues):
    """Ask for several venues at once. `venues` is a list of dicts with a
    `venue_id` and, optionally, that venue's own needs."""
    return client.post(f"/venue-bookings/events/{event_id}", json={"venues": venues}, headers=headers)


class _FirstBooking:
    """A submit response read as one booking, for the many tests that ask for
    a single venue: `.json()` is that booking, not a list of one."""

    def __init__(self, response):
        self.status_code = response.status_code
        self._response = response

    def json(self):
        body = self._response.json()
        return body[0] if self.status_code == 201 else body


def _submit(client, headers, event_id, venue_id):
    return _FirstBooking(_submit_many(client, headers, event_id, [{"venue_id": venue_id}]))


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
    assert client.post(f"/venue-bookings/events/{event_id}", json={"venues": [{"venue_id": venue.id}]}).status_code == 401


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


def test_a_second_request_for_the_same_venue_is_refused(client, db_session):
    _, coord_h, _, event_id = _approved(client, db_session)
    venue = _venue(db_session)
    assert _submit(client, coord_h, event_id, venue.id).status_code == 201
    assert _submit(client, coord_h, event_id, venue.id).status_code == 409
    assert db_session.query(VenueBooking).count() == 1


def test_after_a_rejection_the_coordinator_may_request_another_venue(client, db_session):
    _, coord_h, _, event_id = _approved(client, db_session)
    first = _submit(client, coord_h, event_id, _venue(db_session).id).json()["id"]
    db_session.get(VenueBooking, first).status = BookingStatus.rejected
    db_session.commit()
    assert _submit(client, coord_h, event_id, _venue(db_session, "Hall B").id).status_code == 201
    listed = client.get(f"/venue-bookings/events/{event_id}", headers=coord_h).json()
    assert [b["venue"]["name"] for b in listed] == ["Hall B", "Marina Hall"]


# --- SCRUM-39 AC1: nothing selected -----------------------------------------


def test_scrum39_ac1_an_empty_selection_is_refused_and_nothing_changes(client, db_session):
    _, coord_h, _, event_id = _approved(client, db_session)
    res = _submit_many(client, coord_h, event_id, [])
    assert res.status_code == 422
    assert "Select a venue" in res.json()["detail"]
    assert db_session.query(VenueBooking).count() == 0
    assert db_session.get(Event, event_id).status == EventStatus.event_approved


# --- SCRUM-39 AC2: one booking per venue, each in the queue -----------------


def test_scrum39_ac2_several_venues_make_a_separate_booking_each_under_the_same_event(client, db_session):
    _, coord_h, staff_h, event_id = _approved(client, db_session)
    venues = [_venue(db_session, name) for name in ("Hall A", "Hall B", "Hall C")]

    res = _submit_many(client, coord_h, event_id, [{"venue_id": v.id} for v in venues])

    assert res.status_code == 201
    created = res.json()
    assert [b["venue"]["name"] for b in created] == ["Hall A", "Hall B", "Hall C"]
    assert {b["event"]["id"] for b in created} == {event_id}
    assert len({b["id"] for b in created}) == 3
    assert {b["status"] for b in created} == {BookingStatus.pending}
    queue = client.get("/venue-bookings/queue", headers=staff_h).json()
    assert sorted(b["id"] for b in queue) == sorted(b["id"] for b in created)


def test_scrum39_ac2_an_event_in_planning_can_still_request_more_venues(client, db_session):
    _, coord_h, _, event_id = _approved(client, db_session)
    assert _submit(client, coord_h, event_id, _venue(db_session, "Hall A").id).status_code == 201
    assert db_session.get(Event, event_id).status == EventStatus.planning_event

    assert _submit(client, coord_h, event_id, _venue(db_session, "Hall B").id).status_code == 201
    assert db_session.query(VenueBooking).count() == 2


def test_scrum39_ac2_one_bad_venue_in_the_selection_creates_none(client, db_session):
    _, coord_h, _, event_id = _approved(client, db_session)
    good = _venue(db_session, "Hall A")
    closed = _venue(db_session, "Closed Hall", is_active=False)

    res = _submit_many(client, coord_h, event_id, [{"venue_id": good.id}, {"venue_id": closed.id}])

    assert res.status_code == 422
    assert db_session.query(VenueBooking).count() == 0
    assert db_session.get(Event, event_id).status == EventStatus.event_approved


def test_scrum39_ac2_the_same_venue_twice_in_one_selection_is_refused(client, db_session):
    _, coord_h, _, event_id = _approved(client, db_session)
    venue = _venue(db_session)
    res = _submit_many(client, coord_h, event_id, [{"venue_id": venue.id}, {"venue_id": venue.id}])
    assert res.status_code == 422
    assert db_session.query(VenueBooking).count() == 0


# --- SCRUM-39 AC3: the first booking moves the event to Planning Event ------


def test_scrum39_ac3_the_first_booking_moves_an_approved_event_to_planning_event(client, db_session):
    coordinator, coord_h, _, event_id = _approved(client, db_session)
    venues = [_venue(db_session, "Hall A"), _venue(db_session, "Hall B")]

    assert _submit_many(client, coord_h, event_id, [{"venue_id": v.id} for v in venues]).status_code == 201

    assert db_session.get(Event, event_id).status == EventStatus.planning_event
    moves = (
        db_session.query(EventStatusHistory)
        .filter(EventStatusHistory.event_id == event_id, EventStatusHistory.to_status == EventStatus.planning_event)
        .all()
    )
    assert len(moves) == 1  # one move for the whole selection, not one per venue
    assert moves[0].changed_by == coordinator.id
    assert moves[0].from_status == EventStatus.event_approved
    assert moves[0].created_at is not None


def test_scrum39_ac3_a_refused_request_does_not_move_the_event(client, db_session):
    _, coord_h, _, event_id = _approved(client, db_session)
    assert _submit_many(client, coord_h, event_id, [{"venue_id": 9999}]).status_code == 422
    assert db_session.get(Event, event_id).status == EventStatus.event_approved
    assert db_session.query(EventStatusHistory).filter(
        EventStatusHistory.event_id == event_id, EventStatusHistory.to_status == EventStatus.planning_event
    ).count() == 0


# --- SCRUM-39 AC4: Venue Staff see the needs entered for that venue ---------


def test_scrum39_ac4_each_booking_carries_the_needs_entered_for_its_venue(client, db_session):
    _, coord_h, staff_h, event_id = _approved(client, db_session)
    hall_a, hall_b = _venue(db_session, "Hall A"), _venue(db_session, "Hall B")

    created = _submit_many(
        client,
        coord_h,
        event_id,
        [
            {
                "venue_id": hall_a.id,
                "room_layout_preference": "Banquet",
                "accessibility_needs": "Ramp at the side door",
                "facilities_needs": "Two microphones",
            },
            {"venue_id": hall_b.id},
        ],
    ).json()

    a = client.get(f"/venue-bookings/{created[0]['id']}", headers=staff_h).json()
    assert a["event"]["id"] == event_id
    assert a["venue"]["name"] == "Hall A"
    assert a["start_time"].startswith("2026-11-02T09:00")
    assert a["end_time"].startswith("2026-11-02T17:00")
    assert a["expected_attendance"] == 120
    assert a["room_layout_preference"] == "Banquet"
    assert a["accessibility_needs"] == "Ramp at the side door"
    assert a["facilities_needs"] == "Two microphones"

    # Nothing entered for Hall B: it shows the Event's own needs.
    b = client.get(f"/venue-bookings/{created[1]['id']}", headers=staff_h).json()
    assert b["room_layout_preference"] == "Theatre"
    assert b["accessibility_needs"] == "Step-free access"
    assert b["facilities_needs"] == "Main hall"


def test_scrum39_ac4_blank_needs_count_as_not_entered(client, db_session):
    _, coord_h, staff_h, event_id = _approved(client, db_session)
    venue = _venue(db_session)
    created = _submit_many(
        client, coord_h, event_id, [{"venue_id": venue.id, "room_layout_preference": "   "}]
    ).json()
    body = client.get(f"/venue-bookings/{created[0]['id']}", headers=staff_h).json()
    assert body["room_layout_preference"] == "Theatre"


# --- SCRUM-39 AC5: every booking is listed under its event ------------------


def test_scrum39_ac5_every_booking_is_listed_under_the_event_with_its_own_status(client, db_session):
    _, coord_h, _, event_id = _approved(client, db_session)
    hall_a, hall_b = _venue(db_session, "Hall A"), _venue(db_session, "Hall B")
    created = _submit_many(client, coord_h, event_id, [{"venue_id": hall_a.id}, {"venue_id": hall_b.id}]).json()
    db_session.get(VenueBooking, created[0]["id"]).status = BookingStatus.approved
    db_session.commit()

    listed = client.get(f"/venue-bookings/events/{event_id}", headers=coord_h).json()

    assert {b["venue"]["name"]: b["status"] for b in listed} == {
        "Hall A": BookingStatus.approved,
        "Hall B": BookingStatus.pending,
    }


# --- SCRUM-39 AC6: refused, and nothing created ------------------------------


@pytest.mark.parametrize(
    "status",
    [
        EventStatus.draft,
        EventStatus.submitted_awaiting_coordinator,
        EventStatus.under_review,
        EventStatus.awaiting_organiser_reply,
        EventStatus.awaiting_safety_check,
        EventStatus.safety_check_passed,
        EventStatus.event_completed,
        EventStatus.event_rejected,
        EventStatus.event_cancelled,
    ],
)
def test_scrum39_ac6_an_event_that_is_not_approved_or_in_planning_is_refused(client, db_session, status):
    _, coord_h, _, event_id = _approved(client, db_session)
    db_session.get(Event, event_id).status = status
    db_session.commit()

    res = _submit(client, coord_h, event_id, _venue(db_session).id)

    assert res.status_code == 409
    assert db_session.query(VenueBooking).count() == 0
    assert db_session.get(Event, event_id).status == status


def test_scrum39_ac6_an_event_assigned_to_someone_else_is_refused_and_not_moved(client, db_session):
    _, _, _, event_id = _approved(client, db_session)
    _, other_h = user(client, db_session, Role.COORDINATOR, "c3@example.com", "Third Coordinator")

    res = _submit_many(client, other_h, event_id, [{"venue_id": _venue(db_session).id}])

    assert res.status_code == 404
    assert db_session.query(VenueBooking).count() == 0
    assert db_session.get(Event, event_id).status == EventStatus.event_approved
