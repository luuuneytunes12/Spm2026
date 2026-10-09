"""Tests for the "Submit Event for Safety Check" story (SCRUM-65).

    As an Event Coordinator, I want to submit my Event for the Safety Check
    once its Venues and Equipment are ready, so that it can be approved
    before preparation starts.

Test names carry the acceptance criterion they prove (SCRUM-65 AC1-AC6):
    AC1  'Event Approved' / 'Planning Event', at least one Venue Booking that is
         not Cancelled, all of those Approved, and every Equipment Requirement
         Reserved: the status becomes 'Awaiting Safety Check'
    AC2  no Venue Booking, or every one Cancelled: blocked, told it has no Venue
    AC3  a Venue Booking that is not Approved, or an Equipment Requirement that
         is not Reserved: blocked, every outstanding item listed with its status
    AC4  an Event that is not 'Event Approved' or 'Planning Event': refused
    AC5  an Event not assigned to the Coordinator: denied, status unchanged
    AC6  the change is in the Activity Log with the Coordinator's name and time
"""

import pytest

from app.core.roles import Role
from app.models.enums import BookingStatus, EquipmentStatus, EventStatus
from app.models.equipment import CoordinatorEquipmentRequirement, Equipment, EquipmentRequest
from app.models.events import Event, EventStatusHistory
from app.models.venues import Venue, VenueBooking
from tests.event_review_test_helpers import submitted_event, user


def _setup(client, db_session):
    """An 'Event Approved' event assigned to Sam, with nothing arranged yet."""
    _, org_h = user(client, db_session, Role.ORGANISER, "org@example.com", "Olivia Organiser")
    sam, sam_h = user(client, db_session, Role.COORDINATOR, "sam@example.com", "Sam Tan")
    event_id = submitted_event(client, org_h)
    event = db_session.get(Event, event_id)
    event.coordinator_id = sam.id
    event.status = EventStatus.event_approved
    db_session.commit()
    return {"sam": sam, "sam_h": sam_h, "event_id": event_id, "org_h": org_h}


def _booking(db_session, s, name="Hall A", status=BookingStatus.approved):
    venue = Venue(name=name, location="Block A", capacity=300)
    db_session.add(venue)
    db_session.flush()
    event = db_session.get(Event, s["event_id"])
    booking = VenueBooking(
        event_id=event.id,
        venue_id=venue.id,
        requested_by=s["sam"].id,
        start_time=event.proposed_start,
        end_time=event.proposed_end,
        status=status,
    )
    db_session.add(booking)
    db_session.commit()
    return booking


def _line(db_session, s, name="Projector", status=EquipmentStatus.reserved):
    item = Equipment(name=name, category="Projection", total_quantity=10)
    db_session.add(item)
    db_session.flush()
    line = EquipmentRequest(
        event_id=s["event_id"], equipment_id=item.id, quantity_requested=2, status=status
    )
    db_session.add(line)
    db_session.commit()
    return line


def _status(db_session, s):
    db_session.expire_all()
    return db_session.get(Event, s["event_id"]).status


def _submit(client, s, headers=None):
    return client.post(f"/events/{s['event_id']}/confirm", headers=headers or s["sam_h"])


# --- AC1: ready, so it goes to the Safety Officer ---------------------------


@pytest.mark.parametrize("start", [EventStatus.event_approved, EventStatus.planning_event])
def test_scrum65_ac1_a_ready_event_becomes_awaiting_safety_check(client, db_session, start):
    s = _setup(client, db_session)
    db_session.get(Event, s["event_id"]).status = start
    _booking(db_session, s)
    _line(db_session, s)

    res = _submit(client, s)

    assert res.status_code == 200
    assert res.json()["status"] == EventStatus.awaiting_safety_check
    assert _status(db_session, s) == EventStatus.awaiting_safety_check


def test_scrum65_ac1_several_approved_bookings_pass(client, db_session):
    s = _setup(client, db_session)
    _booking(db_session, s, "Hall A")
    _booking(db_session, s, "Hall B")
    _line(db_session, s)

    assert _submit(client, s).status_code == 200


def test_scrum65_ac1_a_cancelled_booking_next_to_an_approved_one_does_not_block(client, db_session):
    s = _setup(client, db_session)
    _booking(db_session, s, "Hall A")
    _booking(db_session, s, "Hall B", BookingStatus.cancelled)

    assert _submit(client, s).status_code == 200


def test_scrum65_ac1_an_event_with_no_equipment_needs_none_reserved(client, db_session):
    s = _setup(client, db_session)
    _booking(db_session, s)

    assert _submit(client, s).status_code == 200


# --- AC2: no venue ----------------------------------------------------------


def test_scrum65_ac2_an_event_with_no_venue_booking_is_blocked_and_told_it_has_no_venue(client, db_session):
    s = _setup(client, db_session)
    _line(db_session, s)

    res = _submit(client, s)

    assert res.status_code == 409
    assert "no venue" in res.json()["detail"]
    assert _status(db_session, s) == EventStatus.event_approved


def test_scrum65_ac2_an_event_whose_bookings_are_all_cancelled_is_blocked_and_told_it_has_no_venue(client, db_session):
    s = _setup(client, db_session)
    _booking(db_session, s, "Hall A", BookingStatus.cancelled)
    _booking(db_session, s, "Hall B", BookingStatus.cancelled)

    res = _submit(client, s)

    assert res.status_code == 409
    assert "no venue" in res.json()["detail"]
    assert _status(db_session, s) == EventStatus.event_approved


# --- AC3: arrangements not ready, every outstanding item listed -------------


@pytest.mark.parametrize("booking_status", [BookingStatus.pending, BookingStatus.rejected])
def test_scrum65_ac3_a_booking_that_is_not_approved_blocks_it_and_names_its_status(
    client, db_session, booking_status
):
    s = _setup(client, db_session)
    _booking(db_session, s, "Hall A")
    _booking(db_session, s, "Hall B", booking_status)

    res = _submit(client, s)

    assert res.status_code == 409
    detail = res.json()["detail"]
    assert "Hall B" in detail
    assert booking_status.value in detail
    assert "Hall A" not in detail  # the approved one is not outstanding
    assert "no venue" not in detail  # it does have one
    assert _status(db_session, s) == EventStatus.event_approved


def test_scrum65_ac3_an_unreserved_equipment_requirement_blocks_it_and_names_its_status(client, db_session):
    s = _setup(client, db_session)
    _booking(db_session, s)
    _line(db_session, s, "Projector", EquipmentStatus.requested)

    res = _submit(client, s)

    assert res.status_code == 409
    assert "Projector" in res.json()["detail"]
    assert "requested" in res.json()["detail"]
    assert _status(db_session, s) == EventStatus.event_approved


def test_scrum65_ac3_a_coordinator_equipment_requirement_must_be_reserved_too(client, db_session):
    s = _setup(client, db_session)
    _booking(db_session, s)
    db_session.add(
        CoordinatorEquipmentRequirement(
            event_id=s["event_id"], category="Audio", quantity_needed=3, created_by=s["sam"].id
        )
    )
    db_session.commit()

    res = _submit(client, s)

    assert res.status_code == 409
    assert "Audio" in res.json()["detail"]
    assert "requested" in res.json()["detail"]


def test_scrum65_ac3_every_outstanding_item_is_listed_not_just_the_first(client, db_session):
    s = _setup(client, db_session)
    _booking(db_session, s, "Hall A", BookingStatus.pending)
    _line(db_session, s, "Projector", EquipmentStatus.requested)
    _line(db_session, s, "Microphone", EquipmentStatus.reviewing)

    detail = _submit(client, s).json()["detail"]

    for item in ("Hall A", "pending", "Projector", "requested", "Microphone", "reviewing"):
        assert item in detail
    assert _status(db_session, s) == EventStatus.event_approved


# --- AC4: wrong status ------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    [
        EventStatus.draft,
        EventStatus.under_review,
        EventStatus.awaiting_safety_check,
        EventStatus.safety_check_passed,
    ],
)
def test_scrum65_ac4_an_event_that_is_not_approved_or_in_planning_is_refused(client, db_session, status):
    s = _setup(client, db_session)
    _booking(db_session, s)
    db_session.get(Event, s["event_id"]).status = status
    db_session.commit()

    res = _submit(client, s)

    assert res.status_code == 409
    assert _status(db_session, s) == status


def test_scrum65_ac4_submitting_twice_does_not_log_the_change_twice(client, db_session):
    s = _setup(client, db_session)
    _booking(db_session, s)

    assert _submit(client, s).status_code == 200
    assert _submit(client, s).status_code == 409
    assert (
        db_session.query(EventStatusHistory)
        .filter(EventStatusHistory.to_status == EventStatus.awaiting_safety_check)
        .count()
        == 1
    )


# --- AC5: not assigned to this Coordinator ----------------------------------


def test_scrum65_ac5_an_event_assigned_to_someone_else_is_denied_and_unchanged(client, db_session):
    s = _setup(client, db_session)
    _booking(db_session, s)
    _, other_h = user(client, db_session, Role.COORDINATOR, "priya@example.com", "Priya Nair")

    res = _submit(client, s, other_h)

    assert res.status_code == 404  # "not yours" reads the same as "does not exist"
    assert _status(db_session, s) == EventStatus.event_approved


def test_scrum65_ac5_a_user_who_is_not_a_coordinator_is_denied(client, db_session):
    s = _setup(client, db_session)
    _booking(db_session, s)
    _, org_h = user(client, db_session, Role.ORGANISER, "other@example.com", "Another Organiser")

    assert _submit(client, s, org_h).status_code == 403
    assert client.post(f"/events/{s['event_id']}/confirm").status_code == 401
    assert _status(db_session, s) == EventStatus.event_approved


# --- AC6: the Activity Log --------------------------------------------------


def test_scrum65_ac6_the_activity_log_shows_the_change_with_the_coordinators_name_and_time(client, db_session):
    s = _setup(client, db_session)
    _booking(db_session, s)
    _submit(client, s)

    log = client.get(f"/events/assigned/{s['event_id']}", headers=s["sam_h"]).json()["activity"]

    entry = next(e for e in log if e["to_status"] == EventStatus.awaiting_safety_check)
    assert entry["changed_by_name"] == "Sam Tan"
    assert entry["created_at"]
    assert entry["from_status"] == EventStatus.event_approved


def test_scrum65_ac6_a_blocked_submit_adds_nothing_to_the_log(client, db_session):
    s = _setup(client, db_session)
    before = db_session.query(EventStatusHistory).count()

    assert _submit(client, s).status_code == 409

    assert db_session.query(EventStatusHistory).count() == before
