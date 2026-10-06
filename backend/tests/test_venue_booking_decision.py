"""Tests for the "Approve or Reject Venue Booking Request" story.

    As a Venue Staff member, I want to approve or reject a submitted booking
    request, so that the Event Coordinator receives a clear decision on the
    venue.

Test names carry the acceptance criterion they prove (AC1-AC5).
"""

from datetime import datetime

import pytest

from app.core.roles import Role
from app.models.enums import BookingStatus, EventStatus
from app.models.events import Event
from app.models.venues import VenueBooking, VenueUnavailability
from tests.event_review_test_helpers import review_setup, submitted_event, user
from tests.test_venue_booking_request import _submit, _venue

# These tests start from an event that already has a Coordinator; assignment is
# now the Lead's job, so submit alone no longer provides one (see conftest).
pytestmark = pytest.mark.usefixtures("coordinator_auto_assign")


def _setup(client, db_session):
    """An approved event with a pending booking request, and everyone's headers."""
    _, org_h, coordinator, coord_h, event_id = review_setup(client, db_session)
    db_session.get(Event, event_id).status = EventStatus.event_approved
    db_session.commit()
    staff, staff_h = user(client, db_session, Role.VENUE_STAFF, "staff@example.com", "Vera Staff")
    venue = _venue(db_session)
    booking_id = _submit(client, coord_h, event_id, venue.id).json()["id"]
    return {
        "org_h": org_h,
        "coord_h": coord_h,
        "staff": staff,
        "staff_h": staff_h,
        "event_id": event_id,
        "venue": venue,
        "booking_id": booking_id,
    }


def _approve(client, headers, booking_id):
    return client.post(f"/venue-bookings/{booking_id}/approve", headers=headers)


def _reject(client, headers, booking_id, **body):
    return client.post(f"/venue-bookings/{booking_id}/reject", json=body, headers=headers)


def _queue_ids(client, headers):
    return [b["id"] for b in client.get("/venue-bookings/queue", headers=headers).json()]


def _as_coordinator(client, s):
    """The event's requests as its Coordinator reads them, newest first."""
    return client.get(f"/venue-bookings/events/{s['event_id']}", headers=s["coord_h"]).json()


# --- AC1: pending requests appear in a queue for review ---------------------


def test_ac1_a_new_request_is_in_the_queue_until_it_is_decided(client, db_session):
    s = _setup(client, db_session)
    assert _queue_ids(client, s["staff_h"]) == [s["booking_id"]]

    assert _approve(client, s["staff_h"], s["booking_id"]).status_code == 200
    assert _queue_ids(client, s["staff_h"]) == []


def test_ac1_a_rejected_request_leaves_the_queue(client, db_session):
    s = _setup(client, db_session)
    assert _reject(client, s["staff_h"], s["booking_id"], reason="Hall closed.").status_code == 200
    assert _queue_ids(client, s["staff_h"]) == []


# --- AC2: Venue Staff can either approve or reject --------------------------


def test_ac2_venue_staff_can_approve_and_the_decision_records_who_and_when(client, db_session):
    s = _setup(client, db_session)
    res = _approve(client, s["staff_h"], s["booking_id"])
    assert res.status_code == 200
    assert res.json()["status"] == BookingStatus.approved

    booking = db_session.get(VenueBooking, s["booking_id"])
    assert booking.status == BookingStatus.approved
    assert booking.reviewed_by == s["staff"].id
    assert booking.reviewed_at is not None


def test_ac2_venue_staff_can_reject_and_the_decision_records_who_and_when(client, db_session):
    s = _setup(client, db_session)
    res = _reject(client, s["staff_h"], s["booking_id"], reason="Hall closed.")
    assert res.status_code == 200
    assert res.json()["status"] == BookingStatus.rejected

    booking = db_session.get(VenueBooking, s["booking_id"])
    assert booking.status == BookingStatus.rejected
    assert booking.reviewed_by == s["staff"].id
    assert booking.reviewed_at is not None


# --- AC3: a reason, an alternative, or both -- visible to the Coordinator ---


@pytest.mark.parametrize(
    ("body", "reason", "alternative"),
    [
        ({"reason": "Hall closed for repairs."}, "Hall closed for repairs.", None),
        ({"suggested_alternative": "Try Hall B."}, None, "Try Hall B."),
        (
            {"reason": "Hall closed for repairs.", "suggested_alternative": "Try Hall B."},
            "Hall closed for repairs.",
            "Try Hall B.",
        ),
    ],
    ids=["reason", "alternative", "both"],
)
def test_ac3_a_rejection_records_a_reason_an_alternative_or_both_for_the_coordinator(
    client, db_session, body, reason, alternative
):
    s = _setup(client, db_session)
    assert _reject(client, s["staff_h"], s["booking_id"], **body).status_code == 200

    [seen] = _as_coordinator(client, s)
    assert seen["status"] == BookingStatus.rejected
    assert seen["decision_notes"] == reason
    assert seen["suggested_alternative"] == alternative


@pytest.mark.parametrize(
    "body",
    [{}, {"reason": "   ", "suggested_alternative": ""}, {"reason": None}],
    ids=["empty", "blank", "null"],
)
def test_ac3_a_rejection_with_neither_is_refused_and_the_request_stays_pending(client, db_session, body):
    s = _setup(client, db_session)
    res = _reject(client, s["staff_h"], s["booking_id"], **body)
    assert res.status_code == 422
    assert "reason, an alternative, or both" in res.json()["detail"]

    booking = db_session.get(VenueBooking, s["booking_id"])
    assert booking.status == BookingStatus.pending
    assert booking.reviewed_by is None
    assert _queue_ids(client, s["staff_h"]) == [s["booking_id"]]


def test_ac3_an_overlong_reason_is_refused_and_nothing_is_saved(client, db_session):
    s = _setup(client, db_session)
    assert _reject(client, s["staff_h"], s["booking_id"], reason="x" * 2001).status_code == 422
    assert db_session.get(VenueBooking, s["booking_id"]).status == BookingStatus.pending


# --- AC4: the outcome is visible to the Event Coordinator -------------------


def test_ac4_the_coordinator_sees_an_approval_with_who_decided_and_when(client, db_session):
    s = _setup(client, db_session)
    assert _as_coordinator(client, s)[0]["reviewed_by"] is None  # nothing to show yet

    _approve(client, s["staff_h"], s["booking_id"])

    [seen] = _as_coordinator(client, s)
    assert seen["status"] == BookingStatus.approved
    assert seen["reviewed_by"]["name"] == "Vera Staff"
    assert seen["reviewed_at"] is not None
    assert seen["decision_notes"] is None


def test_ac4_the_coordinator_sees_a_rejection_with_who_decided_and_when(client, db_session):
    s = _setup(client, db_session)
    _reject(client, s["staff_h"], s["booking_id"], reason="Hall closed.")

    [seen] = _as_coordinator(client, s)
    assert seen["status"] == BookingStatus.rejected
    assert seen["reviewed_by"]["name"] == "Vera Staff"
    assert seen["reviewed_at"] is not None


def test_ac4_the_outcome_is_not_visible_to_another_coordinator(client, db_session):
    s = _setup(client, db_session)
    _reject(client, s["staff_h"], s["booking_id"], reason="Hall closed.")
    _, other_h = user(client, db_session, Role.COORDINATOR, "c2@example.com", "Other Coordinator")
    assert client.get(f"/venue-bookings/events/{s['event_id']}", headers=other_h).status_code == 404
    assert client.get(f"/venue-bookings/{s['booking_id']}", headers=other_h).status_code == 403


# --- AC5: a rejected request can be resubmitted and reviewed again ----------


def test_ac5_a_rejected_request_can_be_resubmitted_and_reviewed_again_without_limit(client, db_session):
    s = _setup(client, db_session)
    booking_id = s["booking_id"]

    for round_ in range(1, 6):
        assert _reject(client, s["staff_h"], booking_id, reason=f"Not this time ({round_}).").status_code == 200
        resubmitted = _submit(client, s["coord_h"], s["event_id"], s["venue"].id)
        assert resubmitted.status_code == 201
        booking_id = resubmitted.json()["id"]
        assert _queue_ids(client, s["staff_h"]) == [booking_id]  # back in the queue

    assert _approve(client, s["staff_h"], booking_id).status_code == 200
    history = _as_coordinator(client, s)
    assert [b["status"] for b in history] == ["approved"] + ["rejected"] * 5
    assert history[1]["decision_notes"] == "Not this time (5)."  # earlier decisions are kept


# --- Access control ----------------------------------------------------------


def test_only_venue_staff_can_decide(client, db_session):
    s = _setup(client, db_session)
    for headers, expected in ((s["coord_h"], 403), (s["org_h"], 403), (None, 401)):
        assert _approve(client, headers, s["booking_id"]).status_code == expected
        assert _reject(client, headers, s["booking_id"], reason="No.").status_code == expected
    assert db_session.get(VenueBooking, s["booking_id"]).status == BookingStatus.pending


def test_deciding_on_an_unknown_request_is_not_found(client, db_session):
    s = _setup(client, db_session)
    assert _approve(client, s["staff_h"], 9999).status_code == 404
    assert _reject(client, s["staff_h"], 9999, reason="No.").status_code == 404


# --- State: a decision is final ---------------------------------------------


def test_an_approved_request_cannot_be_decided_again(client, db_session):
    s = _setup(client, db_session)
    _approve(client, s["staff_h"], s["booking_id"])
    _, other_h = user(client, db_session, Role.VENUE_STAFF, "staff2@example.com", "Second Staff")

    assert _approve(client, other_h, s["booking_id"]).status_code == 409
    res = _reject(client, other_h, s["booking_id"], reason="Changed my mind.")
    assert res.status_code == 409
    assert "already been approved" in res.json()["detail"]

    booking = db_session.get(VenueBooking, s["booking_id"])
    assert booking.status == BookingStatus.approved
    assert booking.reviewed_by == s["staff"].id  # the first decision stands
    assert booking.decision_notes is None


def test_a_rejected_request_cannot_be_decided_again(client, db_session):
    s = _setup(client, db_session)
    _reject(client, s["staff_h"], s["booking_id"], reason="Hall closed.")

    assert _approve(client, s["staff_h"], s["booking_id"]).status_code == 409
    assert _reject(client, s["staff_h"], s["booking_id"], reason="Another reason.").status_code == 409

    booking = db_session.get(VenueBooking, s["booking_id"])
    assert booking.status == BookingStatus.rejected
    assert booking.decision_notes == "Hall closed."


# --- Conflicts: approval must not double-book the venue ---------------------


def _second_request_for_the_same_venue(client, db_session, s, **event_times):
    """Another approved event asking for the same venue; returns its booking id."""
    event_id = submitted_event(client, s["org_h"])
    event = db_session.get(Event, event_id)
    event.status = EventStatus.event_approved
    for field, value in event_times.items():
        setattr(event, field, value)
    db_session.commit()
    return _submit(client, s["coord_h"], event_id, s["venue"].id).json()["id"]


def test_a_venue_already_confirmed_for_an_overlapping_event_cannot_be_approved_again(client, db_session):
    s = _setup(client, db_session)
    second = _second_request_for_the_same_venue(client, db_session, s)
    assert _approve(client, s["staff_h"], s["booking_id"]).status_code == 200

    res = _approve(client, s["staff_h"], second)
    assert res.status_code == 409
    assert "already booked" in res.json()["detail"]
    assert db_session.get(VenueBooking, second).status == BookingStatus.pending
    assert _queue_ids(client, s["staff_h"]) == [second]  # still there to be rejected


def test_a_back_to_back_booking_of_the_same_venue_can_be_approved(client, db_session):
    s = _setup(client, db_session)
    second = _second_request_for_the_same_venue(
        client,
        db_session,
        s,
        proposed_start=datetime(2026, 11, 2, 17, 0),
        proposed_end=datetime(2026, 11, 2, 20, 0),
    )
    assert _approve(client, s["staff_h"], s["booking_id"]).status_code == 200
    assert _approve(client, s["staff_h"], second).status_code == 200


def test_a_venue_blocked_out_for_that_time_cannot_be_approved(client, db_session):
    s = _setup(client, db_session)
    db_session.add(
        VenueUnavailability(
            venue_id=s["venue"].id,
            start_time=datetime(2026, 11, 2, 12, 0),
            end_time=datetime(2026, 11, 2, 13, 0),
            reason="Maintenance",
            created_by=s["staff"].id,
        )
    )
    db_session.commit()

    res = _approve(client, s["staff_h"], s["booking_id"])
    assert res.status_code == 409
    assert "unavailable" in res.json()["detail"]
    assert db_session.get(VenueBooking, s["booking_id"]).status == BookingStatus.pending
