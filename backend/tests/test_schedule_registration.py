"""Tests for the "Schedule Registration for a Confirmed Event" story (SCRUM-66).

    As an Event Coordinator, I want to schedule registration for a confirmed
    Event and set its open and close dates, so that Attendees can register
    before the Event.

Test names carry the acceptance criterion they prove (SCRUM-66 AC1-AC6):
    AC1  'Safety Check Passed (Event Confirmed)': the dates are saved and shown
    AC2  not confirmed: blocked, and the Coordinator is told the Safety Officer
         must approve it first
    AC3  confirmed, but a Venue Booking is no longer Approved or an Equipment
         Requirement no longer Reserved: blocked, every outstanding item listed
    AC4  close before open, or after the Event's start: blocked, fields flagged
    AC5  scheduled: an Attendee can register between the open and close dates
    AC6  an Event not assigned to the Coordinator: denied, nothing saved
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.roles import Role
from app.models.enums import BookingStatus, EquipmentStatus, EventStatus
from app.models.equipment import CoordinatorEquipmentRequirement, Equipment, EquipmentRequest
from app.models.events import Event
from app.models.venues import Venue, VenueBooking
from tests.event_review_test_helpers import user

NOW = datetime.now(timezone.utc)


def _iso(delta_days: float) -> str:
    return (NOW + timedelta(days=delta_days)).isoformat()


def _setup(client, db_session, *, status=EventStatus.safety_check_passed):
    """A confirmed event 30 days away, with an approved venue and a reserved
    projector, assigned to Sam; plus an Attendee."""
    organiser, _ = user(client, db_session, Role.ORGANISER, "org@example.com", "Olivia Organiser")
    sam, sam_h = user(client, db_session, Role.COORDINATOR, "sam@example.com", "Sam Tan")
    _, attendee_h = user(client, db_session, Role.ATTENDEE, "amy@example.com", "Amy Attendee")
    start = NOW + timedelta(days=30)
    event = Event(
        organiser_id=organiser.id,
        coordinator_id=sam.id,
        name="Partner Summit",
        proposed_start=start,
        proposed_end=start + timedelta(hours=8),
        registration_enabled=False,
        status=status,
    )
    db_session.add(event)
    db_session.flush()
    venue = Venue(name="Hall A", location="Block A", capacity=300)
    item = Equipment(name="Projector", category="Projection", total_quantity=10)
    db_session.add_all([venue, item])
    db_session.flush()
    booking = VenueBooking(
        event_id=event.id,
        venue_id=venue.id,
        requested_by=sam.id,
        start_time=event.proposed_start,
        end_time=event.proposed_end,
        status=BookingStatus.approved,
    )
    line = EquipmentRequest(
        event_id=event.id, equipment_id=item.id, quantity_requested=2, status=EquipmentStatus.reserved
    )
    db_session.add_all([booking, line])
    db_session.commit()
    return {"event": event, "sam": sam, "sam_h": sam_h, "attendee_h": attendee_h, "booking": booking, "line": line}


def _put(client, headers, event_id, *, enabled=True, opens=None, closes=None):
    return client.put(
        f"/events/assigned/{event_id}/registration",
        json={"registration_enabled": enabled, "registration_opens_at": opens, "registration_closes_at": closes},
        headers=headers,
    )


def _enable(client, s, opens=1, closes=10):
    return _put(client, s["sam_h"], s["event"].id, opens=_iso(opens), closes=_iso(closes))


def _saved(db_session, s):
    db_session.expire_all()
    return db_session.get(Event, s["event"].id)


def _flagged(res) -> set[str]:
    return {item["loc"][-1] for item in res.json()["detail"]}


# --- AC1: dates saved and shown ---------------------------------------------


def test_scrum66_ac1_enabling_on_a_confirmed_event_saves_the_dates_and_shows_them(client, db_session):
    s = _setup(client, db_session)

    res = _enable(client, s, opens=2, closes=20)

    assert res.status_code == 200
    body = res.json()
    assert body["registration_enabled"] is True
    assert body["registration_opens_at"] and body["registration_closes_at"]
    shown = client.get(f"/events/assigned/{s['event'].id}", headers=s["sam_h"]).json()
    assert shown["registration_opens_at"] == body["registration_opens_at"]
    assert shown["registration_closes_at"] == body["registration_closes_at"]
    saved = _saved(db_session, s)
    assert saved.registration_enabled is True
    assert saved.registration_opens_at is not None


def test_scrum66_ac1_a_cancelled_equipment_line_does_not_stop_registration(client, db_session):
    s = _setup(client, db_session)
    s["line"].status = EquipmentStatus.cancelled
    db_session.commit()

    assert _enable(client, s).status_code == 200


# --- AC2: not confirmed, so the Safety Officer must approve first -----------


@pytest.mark.parametrize(
    "status",
    [
        EventStatus.draft,
        EventStatus.submitted_awaiting_coordinator,
        EventStatus.under_review,
        EventStatus.awaiting_organiser_reply,
        EventStatus.event_approved,
        EventStatus.planning_event,
        EventStatus.awaiting_safety_check,
        EventStatus.event_completed,
        EventStatus.event_rejected,
        EventStatus.event_cancelled,
    ],
)
def test_scrum66_ac2_an_unconfirmed_event_is_blocked_and_the_safety_officer_is_named(client, db_session, status):
    s = _setup(client, db_session, status=status)

    res = _enable(client, s)

    assert res.status_code == 409
    assert "Safety Officer must approve" in res.json()["detail"]
    saved = _saved(db_session, s)
    assert saved.registration_enabled is False
    assert saved.registration_opens_at is None


# --- AC3: confirmed, but the arrangements have fallen through ---------------


def test_scrum66_ac3_a_venue_booking_that_is_no_longer_approved_blocks_it_and_is_listed(client, db_session):
    s = _setup(client, db_session)
    s["booking"].status = BookingStatus.pending
    db_session.commit()

    res = _enable(client, s)

    assert res.status_code == 409
    assert "Hall A" in res.json()["detail"]
    assert "pending" in res.json()["detail"]
    assert _saved(db_session, s).registration_enabled is False


def test_scrum66_ac3_an_equipment_line_that_is_no_longer_reserved_blocks_it_and_is_listed(client, db_session):
    s = _setup(client, db_session)
    s["line"].status = EquipmentStatus.requested
    db_session.commit()

    res = _enable(client, s)

    assert res.status_code == 409
    assert "Projector" in res.json()["detail"]
    assert "requested" in res.json()["detail"]
    assert _saved(db_session, s).registration_enabled is False


def test_scrum66_ac3_a_coordinator_equipment_requirement_that_is_not_reserved_blocks_it(client, db_session):
    s = _setup(client, db_session)
    db_session.add(
        CoordinatorEquipmentRequirement(
            event_id=s["event"].id, category="Audio", quantity_needed=3, created_by=s["sam"].id
        )
    )
    db_session.commit()

    res = _enable(client, s)

    assert res.status_code == 409
    assert "Audio" in res.json()["detail"]


def test_scrum66_ac3_every_outstanding_item_is_listed(client, db_session):
    s = _setup(client, db_session)
    s["booking"].status = BookingStatus.pending
    s["line"].status = EquipmentStatus.reviewing
    db_session.commit()

    detail = _enable(client, s).json()["detail"]

    for item in ("Hall A", "pending", "Projector", "reviewing"):
        assert item in detail


def test_scrum66_ac3_a_confirmed_event_with_no_venue_at_all_is_blocked(client, db_session):
    s = _setup(client, db_session)
    db_session.delete(s["booking"])
    db_session.commit()

    res = _enable(client, s)

    assert res.status_code == 409
    assert "The event has no venue" in res.json()["detail"]


def test_scrum66_ac3_switching_registration_off_is_never_blocked_by_the_arrangements(client, db_session):
    s = _setup(client, db_session)
    assert _enable(client, s).status_code == 200
    s["booking"].status = BookingStatus.cancelled
    db_session.commit()

    res = _put(client, s["sam_h"], s["event"].id, enabled=False)

    assert res.status_code == 200
    assert _saved(db_session, s).registration_enabled is False


# --- AC4: dates must make sense ---------------------------------------------


def test_scrum66_ac4_close_before_open_is_blocked_and_both_fields_flagged(client, db_session):
    s = _setup(client, db_session)

    res = _enable(client, s, opens=10, closes=2)

    assert res.status_code == 422
    assert _flagged(res) == {"registration_opens_at", "registration_closes_at"}
    assert _saved(db_session, s).registration_enabled is False


def test_scrum66_ac4_close_after_the_event_starts_is_blocked_and_the_close_field_flagged(client, db_session):
    s = _setup(client, db_session)  # the event starts in 30 days

    res = _enable(client, s, opens=1, closes=31)

    assert res.status_code == 422
    assert _flagged(res) == {"registration_closes_at"}
    assert "after the event starts" in res.json()["detail"][0]["msg"]
    saved = _saved(db_session, s)
    assert saved.registration_enabled is False
    assert saved.registration_closes_at is None


def test_scrum66_ac4_closing_exactly_when_the_event_starts_is_allowed(client, db_session):
    s = _setup(client, db_session)

    res = _put(
        client,
        s["sam_h"],
        s["event"].id,
        opens=_iso(1),
        closes=s["event"].proposed_start.replace(tzinfo=timezone.utc).isoformat(),
    )

    assert res.status_code == 200


def test_scrum66_ac4_a_close_before_the_open_and_after_the_start_flags_both_problems(client, db_session):
    s = _setup(client, db_session)

    res = _enable(client, s, opens=40, closes=35)

    assert res.status_code == 422
    messages = [item["msg"] for item in res.json()["detail"]]
    assert any("cannot close before it opens" in m for m in messages)
    assert any("after the event starts" in m for m in messages)


# --- AC5: Attendees can register between the dates --------------------------


def test_scrum66_ac5_an_attendee_can_register_between_the_open_and_close_dates(client, db_session):
    s = _setup(client, db_session)
    assert _enable(client, s, opens=-1, closes=10).status_code == 200

    offered = client.get("/registrations/events", headers=s["attendee_h"]).json()
    res = client.post(f"/registrations/events/{s['event'].id}", headers=s["attendee_h"])

    assert [e["id"] for e in offered] == [s["event"].id]
    assert res.status_code == 200


def test_scrum66_ac5_an_attendee_cannot_register_before_it_opens_or_after_it_closes(client, db_session):
    s = _setup(client, db_session)
    assert _enable(client, s, opens=5, closes=10).status_code == 200
    assert client.post(f"/registrations/events/{s['event'].id}", headers=s["attendee_h"]).status_code == 409

    assert _enable(client, s, opens=-10, closes=-1).status_code == 200
    assert client.post(f"/registrations/events/{s['event'].id}", headers=s["attendee_h"]).status_code == 409


# --- AC6: not the assigned Coordinator --------------------------------------


def test_scrum66_ac6_an_event_assigned_to_someone_else_is_denied_and_nothing_is_saved(client, db_session):
    s = _setup(client, db_session)
    _, other_h = user(client, db_session, Role.COORDINATOR, "priya@example.com", "Priya Nair")

    res = _put(client, other_h, s["event"].id, opens=_iso(1), closes=_iso(10))

    assert res.status_code == 404  # "not yours" reads the same as "does not exist"
    saved = _saved(db_session, s)
    assert saved.registration_enabled is False
    assert saved.registration_opens_at is None


@pytest.mark.parametrize("role", [Role.ORGANISER, Role.VENUE_STAFF, Role.TECH_SUPPORT, Role.SAFETY_OFFICER, Role.ATTENDEE])
def test_scrum66_ac6_only_a_coordinator_can_enable_registration(client, db_session, role):
    s = _setup(client, db_session)
    _, headers = user(client, db_session, role, f"{role.value}@example.com", "Someone Else")

    assert _put(client, headers, s["event"].id, opens=_iso(1), closes=_iso(10)).status_code == 403
    assert _put(client, {}, s["event"].id, opens=_iso(1), closes=_iso(10)).status_code == 401
    assert _saved(db_session, s).registration_enabled is False
