"""Tests for "Track My Event Status as Organiser" (SCRUM-30), AC1-AC6.

The Organiser sees each of their Events' status on the list and the event
page, one of the eleven names of dod.md 11a, sees it change, sees every change
with its time, and -- while the Event is being planned -- how each Venue
Booking, equipment line and the Safety Check is doing. Another Organiser's
Event is refused.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.roles import Role
from app.models.enums import BookingStatus, EquipmentStatus, EventStatus
from app.models.events import Event, EventStatusHistory
from app.models.venues import VenueBooking
from tests.event_review_test_helpers import review_setup, user
from tests.test_venue_booking_request import _venue

pytestmark = pytest.mark.usefixtures("coordinator_auto_assign")

DOD_STATUS_NAMES = [
    "Draft",
    "Submitted – Awaiting Coordinator",
    "Under Review",
    "Awaiting Organiser Reply",
    "Event Approved",
    "Planning Event",
    "Awaiting Safety Check",
    "Safety Check Passed (Event Confirmed)",
    "Event Completed",
    "Event Rejected",
    "Event Cancelled",
]


def _planning(client, db_session):
    _, org_h, coordinator, coord_h, event_id = review_setup(client, db_session)
    event = db_session.get(Event, event_id)
    event.status = EventStatus.planning_event
    db_session.commit()
    return org_h, coordinator, event_id


def _booking(db_session, event_id, venue, status, **fields):
    now = datetime.now(timezone.utc)
    booking = VenueBooking(
        event_id=event_id,
        venue_id=venue.id,
        requested_by=db_session.get(Event, event_id).coordinator_id,
        start_time=now + timedelta(days=30),
        end_time=now + timedelta(days=30, hours=8),
        status=status,
        **fields,
    )
    db_session.add(booking)
    db_session.commit()
    return booking


def _progress(client, headers, event_id):
    return client.get(f"/events/{event_id}/progress", headers=headers)


# --- AC1: the status is on the list and on the event page --------------------


def test_ac1_the_list_and_the_event_page_both_show_the_current_status(client, db_session):
    _, org_h, _, _, event_id = review_setup(client, db_session)
    listed = client.get("/events", headers=org_h).json()
    assert [(e["id"], e["status"]) for e in listed] == [(event_id, "under_review")]
    assert client.get(f"/events/{event_id}", headers=org_h).json()["status"] == "under_review"


# --- AC2: only the eleven DoD statuses --------------------------------------


def test_ac2_the_status_names_are_exactly_the_eleven_of_the_dod():
    from app.models.enums import EventStatus as S

    assert [s.value for s in S] == [
        "draft",
        "submitted_awaiting_coordinator",
        "under_review",
        "awaiting_organiser_reply",
        "event_approved",
        "planning_event",
        "awaiting_safety_check",
        "safety_check_passed",
        "event_completed",
        "event_rejected",
        "event_cancelled",
    ]
    assert len(DOD_STATUS_NAMES) == 11


# --- AC3: a change shows the next time the Organiser looks -------------------


def test_ac3_a_status_change_is_shown_on_the_next_view(client, db_session):
    _, org_h, _, coord_h, event_id = review_setup(client, db_session)
    assert client.get(f"/events/{event_id}", headers=org_h).json()["status"] == "under_review"
    assert client.post(f"/events/{event_id}/approve", headers=coord_h).status_code == 200
    assert client.get(f"/events/{event_id}", headers=org_h).json()["status"] == "event_approved"
    assert [e["status"] for e in client.get("/events", headers=org_h).json()] == ["event_approved"]
    assert _progress(client, org_h, event_id).json()["status"] == "event_approved"


# --- AC4: each change with its time -----------------------------------------


def test_ac4_every_status_change_is_listed_with_its_time_newest_first(client, db_session):
    _, org_h, _, coord_h, event_id = review_setup(client, db_session)
    client.post(f"/events/{event_id}/approve", headers=coord_h)
    log = client.get(f"/events/{event_id}/activity", headers=org_h).json()
    changes = [(e["from_status"], e["to_status"]) for e in log]
    assert ("under_review", "event_approved") in changes
    assert ("submitted_awaiting_coordinator", "under_review") in changes
    assert changes.index(("under_review", "event_approved")) < changes.index(
        ("submitted_awaiting_coordinator", "under_review")
    )
    assert all(e["created_at"] for e in log)
    assert [e["created_at"] for e in log] == sorted((e["created_at"] for e in log), reverse=True)


# --- AC5: planning progress -------------------------------------------------


def test_ac5_each_venue_booking_shows_its_status_and_a_lost_venue_needs_a_replacement(client, db_session):
    org_h, _, event_id = _planning(client, db_session)
    ok = _booking(db_session, event_id, _venue(db_session, "Marina Hall"), BookingStatus.approved)
    lost = _booking(db_session, event_id, _venue(db_session, "Harbour Hall"), BookingStatus.hold_expired)
    swap = _booking(
        db_session,
        event_id,
        _venue(db_session, "Garden Hall"),
        BookingStatus.pending,
        replaces_booking_id=lost.id,
    )
    rows = {b["id"]: b for b in _progress(client, org_h, event_id).json()["venue_bookings"]}
    assert rows[ok.id]["status"] == "approved" and rows[ok.id]["needs_replacement"] is False
    assert rows[lost.id]["status"] == "hold_expired" and rows[lost.id]["needs_replacement"] is True
    assert rows[swap.id]["status"] == "pending"
    assert rows[swap.id]["replaces_venue_name"] == "Harbour Hall"
    assert rows[ok.id]["venue_name"] == "Marina Hall"


def test_ac5_equipment_lines_show_their_progress(client, db_session):
    from app.models.equipment import Equipment, EquipmentRequest

    org_h, _, event_id = _planning(client, db_session)
    item = Equipment(name="Projector", category="AV", total_quantity=5)
    db_session.add(item)
    db_session.commit()
    db_session.add(
        EquipmentRequest(event_id=event_id, equipment_id=item.id, quantity_requested=2, status=EquipmentStatus.reserved)
    )
    db_session.commit()
    [line] = _progress(client, org_h, event_id).json()["equipment"]
    assert (line["equipment_name"], line["quantity_requested"], line["status"]) == ("Projector", 2, "reserved")


def test_ac5_the_safety_check_stage_follows_the_event(client, db_session):
    org_h, _, event_id = _planning(client, db_session)
    stage = lambda: _progress(client, org_h, event_id).json()["safety_check"]["stage"]  # noqa: E731
    assert stage() == "Not requested"
    for status, expected in (
        (EventStatus.awaiting_safety_check, "Awaiting Safety Officer"),
        (EventStatus.safety_check_passed, "Passed"),
    ):
        db_session.get(Event, event_id).status = status
        db_session.commit()
        assert stage() == expected


def test_ac5_a_safety_check_send_back_shows_the_reason(client, db_session):
    org_h, _, event_id = _planning(client, db_session)
    officer, _ = user(client, db_session, Role.SAFETY_OFFICER, "officer@example.com", "Sam Safety")
    db_session.add(
        EventStatusHistory(
            event_id=event_id,
            changed_by=officer.id,
            from_status=EventStatus.awaiting_safety_check,
            to_status=EventStatus.planning_event,
            note="Safety changes requested: Fire exits are blocked.",
        )
    )
    db_session.commit()
    progress = _progress(client, org_h, event_id).json()["safety_check"]
    assert progress["stage"] == "Sent back"
    assert progress["sent_back"]["reason"] == "Fire exits are blocked."
    assert progress["sent_back"]["result"] == "Changes Requested"
    assert progress["sent_back"]["decided_by_name"] == "Sam Safety"


def test_ac5_with_nothing_arranged_yet_the_lists_are_empty(client, db_session):
    org_h, _, event_id = _planning(client, db_session)
    body = _progress(client, org_h, event_id).json()
    assert body["venue_bookings"] == [] and body["equipment"] == []
    assert body["safety_check"] == {"stage": "Not requested", "sent_back": None}


# --- AC6: another Organiser's Event is refused ------------------------------


def test_ac6_another_organisers_event_is_refused_everywhere_and_unchanged(client, db_session):
    _, _, event_id = _planning(client, db_session)
    _, other_h = user(client, db_session, Role.ORGANISER, "other@example.com", "Other Organiser")
    for path in ("", "/activity", "/progress", "/change-requests"):
        assert client.get(f"/events/{event_id}{path}", headers=other_h).status_code == 404, path
    assert client.get("/events", headers=other_h).json() == []
    assert db_session.get(Event, event_id).status == EventStatus.planning_event


def test_ac6_progress_needs_a_login_and_hides_other_events_bookings(client, db_session):
    org_h, _, event_id = _planning(client, db_session)
    assert client.get(f"/events/{event_id}/progress").status_code == 401
    _booking(db_session, event_id, _venue(db_session, "Private Hall"), BookingStatus.approved)
    _, other_h = user(client, db_session, Role.ORGANISER, "other@example.com", "Other Organiser")
    assert "Private Hall" not in _progress(client, other_h, event_id).text
    assert _progress(client, org_h, event_id).json()["venue_bookings"][0]["venue_name"] == "Private Hall"
