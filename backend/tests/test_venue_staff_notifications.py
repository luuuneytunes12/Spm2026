"""Tests for Venue Staff's notifications about bookings and Events at their venues.

Every Venue Staff member manages every venue (confirmed with the customer),
so "a Venue I manage" is any venue, and "one I do not manage" reduces to:
nobody who is not Venue Staff is told.

    AC1  A booking request is submitted, including one raised to replace a
         booking whose Venue became unavailable: I get a notification.
    AC2  It identifies the Event name, the requested Venue and the date/time.
    AC3  Nobody outside Venue Staff gets the booking request notification.
    AC4  An Event with an Approved booking changes its date, time or expected
         attendance: I get a notification naming the Event, the Venue and
         what changed.
    AC5  An Event change with no Approved booking, or a request, reaches
         nobody outside Venue Staff -- and an Event with no Approved booking
         sends Venue Staff nothing.
    AC6  An Event does not clear its Safety Check and returns to Planning
         Event: I get a notification.

Test names carry the acceptance criterion they prove.
"""

from datetime import datetime, timezone

import pytest

from app.core.roles import Role
from app.models.enums import BookingStatus, EventStatus, NotificationType
from app.models.events import Event
from app.models.notifications import Notification
from app.models.user import User
from app.services.submission_notice import EventNotice
from app.services.venue_staff_notices import (
    ApprovedEventChangedNotice,
    BookingRequestedNotice,
    SafetyReturnedNotice,
    VenueStaffNotice,
)
from tests.event_review_test_helpers import review_setup, user
from tests.test_safety_officer_notifications import _confirm, _ready
from tests.test_venue_booking_request import _submit_many, _venue
from tests.test_venue_replacement import _flagged_world, _replace

REQUESTED = NotificationType.venue_booking_requested.value
CHANGED = NotificationType.approved_event_changed.value
RETURNED = NotificationType.safety_returned_to_planning.value


def _inbox(client, headers, type):
    """`type` notifications, oldest first."""
    return [n["message"] for n in client.get("/notifications", headers=headers).json() if n["type"] == type][::-1]


def _recipients(db_session, type):
    db_session.expire_all()
    return {n.user_id for n in db_session.query(Notification).filter_by(type=type)}


def _venue_staff_ids(db_session):
    return {u.id for u in db_session.query(User).filter_by(role=Role.VENUE_STAFF.value)}


def _world(client, db_session):
    """An approved Event, its Coordinator and two Venue Staff members; the
    setup's own notices are cleared so each test reads only what it caused."""
    organiser, org_h, coordinator, coord_h, event_id = review_setup(client, db_session)
    db_session.get(Event, event_id).status = EventStatus.event_approved
    db_session.commit()
    vera, vera_h = user(client, db_session, Role.VENUE_STAFF, "vera@example.com", "Vera Staff")
    vic, vic_h = user(client, db_session, Role.VENUE_STAFF, "vic@example.com", "Vic Staff")
    db_session.query(Notification).delete()
    db_session.commit()
    return {
        "event_id": event_id, "org_h": org_h, "coord_h": coord_h, "coordinator": coordinator,
        "organiser": organiser, "vera_h": vera_h, "vic_h": vic_h,
    }


def _request(client, db_session, w, *names):
    venues = [_venue(db_session, name) for name in names]
    res = _submit_many(client, w["coord_h"], w["event_id"], [{"venue_id": v.id} for v in venues])
    assert res.status_code == 201, res.text
    return {b["venue"]["name"]: b["id"] for b in res.json()}


def _approved(client, db_session, w, *names):
    """Bookings requested and approved; notices so far cleared."""
    ids = _request(client, db_session, w, *names)
    for booking_id in ids.values():
        assert client.post(f"/venue-bookings/{booking_id}/approve", headers=w["vera_h"]).status_code == 200
    db_session.query(Notification).delete()
    db_session.commit()
    return ids


def _edit(client, w, **body):
    res = client.patch(f"/events/assigned/{w['event_id']}/planning", json=body, headers=w["coord_h"])
    assert res.status_code == 200, res.text
    return res.json()


# --- AC1 / AC2: a request -> every Venue Staff member, Event, Venue, time ---


def test_ac1_ac2_a_booking_request_names_the_event_the_venue_and_the_time(client, db_session):
    w = _world(client, db_session)

    _request(client, db_session, w, "Marina Hall")

    expected = [
        "New venue booking request for 'Regional Partner Conference': Marina Hall, 2 Nov 2026, 09:00-17:00 UTC."
    ]
    assert _inbox(client, w["vera_h"], REQUESTED) == expected
    assert _inbox(client, w["vic_h"], REQUESTED) == expected


def test_ac1_several_venues_in_one_request_give_one_notice_each(client, db_session):
    w = _world(client, db_session)

    _request(client, db_session, w, "Marina Hall", "Harbour Room")

    messages = _inbox(client, w["vera_h"], REQUESTED)
    assert len(messages) == 2
    assert "Marina Hall" in messages[0] and "Harbour Room" in messages[1]


@pytest.mark.usefixtures("coordinator_auto_assign")
def test_ac1_ac2_a_replacement_request_names_the_venue_it_replaces(client, db_session):
    rw, original, other = _flagged_world(client, db_session)
    db_session.query(Notification).delete()
    db_session.commit()

    res = _replace(client, rw, original, other)

    assert res.status_code == 201, res.text
    [message] = _inbox(client, rw["staff_h"], REQUESTED)
    assert message.startswith("New venue booking request for ")
    assert "Other Hall, 2 Nov 2030, 10:00-12:00 UTC." in message
    assert message.endswith("It replaces Marina Hall, which became unavailable.")


def test_ac1_a_refused_request_tells_nobody(client, db_session):
    w = _world(client, db_session)
    venue = _venue(db_session, "Marina Hall")
    _submit_many(client, w["coord_h"], w["event_id"], [{"venue_id": venue.id}])

    again = _submit_many(client, w["coord_h"], w["event_id"], [{"venue_id": venue.id}])  # already live

    assert again.status_code == 409
    assert len(_inbox(client, w["vera_h"], REQUESTED)) == 1


def test_ac1_the_request_is_still_made(client, db_session):
    """Frozen: the request still lands, pending, in the queue."""
    w = _world(client, db_session)
    ids = _request(client, db_session, w, "Marina Hall")
    queue = client.get("/venue-bookings/queue", headers=w["vera_h"]).json()
    assert [b["id"] for b in queue] == list(ids.values())
    assert queue[0]["status"] == BookingStatus.pending.value


# --- AC3: nobody outside Venue Staff ----------------------------------------


def test_ac3_only_venue_staff_get_the_request_notice(client, db_session):
    w = _world(client, db_session)
    user(client, db_session, Role.TECH_SUPPORT, "tess@example.com", "Tess Tech")

    _request(client, db_session, w, "Marina Hall")

    assert _recipients(db_session, REQUESTED) == _venue_staff_ids(db_session)


# --- AC4: an Approved booking's Event changes -> Event, Venue, what changed -


def test_ac4_a_new_date_names_the_event_the_venue_and_the_old_and_new_time(client, db_session):
    w = _world(client, db_session)
    _approved(client, db_session, w, "Marina Hall")

    _edit(client, w, proposed_start="2026-11-03T09:00:00Z", proposed_end="2026-11-03T17:00:00Z")

    assert _inbox(client, w["vera_h"], CHANGED) == [
        "'Regional Partner Conference', approved at Marina Hall, has changed: "
        "it now runs 3 Nov 2026, 09:00-17:00 UTC (was 2 Nov 2026, 09:00-17:00 UTC)."
    ]


def test_ac4_a_new_attendance_names_the_old_and_new_figure(client, db_session):
    w = _world(client, db_session)
    _approved(client, db_session, w, "Marina Hall")

    _edit(client, w, expected_attendance=150)

    [message] = _inbox(client, w["vic_h"], CHANGED)
    assert message.endswith("has changed: expected attendance is now 150 (was 120).")


def test_ac4_date_and_attendance_in_one_save_give_one_notice_with_both(client, db_session):
    w = _world(client, db_session)
    _approved(client, db_session, w, "Marina Hall")

    _edit(client, w, proposed_end="2026-11-02T19:00:00Z", expected_attendance=150)

    [message] = _inbox(client, w["vera_h"], CHANGED)
    assert "it now runs 2 Nov 2026, 09:00-19:00 UTC" in message
    assert "expected attendance is now 150 (was 120)" in message


def test_ac4_every_approved_venue_is_named(client, db_session):
    w = _world(client, db_session)
    _approved(client, db_session, w, "Marina Hall", "Harbour Room")

    _edit(client, w, expected_attendance=150)

    [message] = _inbox(client, w["vera_h"], CHANGED)
    assert "approved at Marina Hall and Harbour Room" in message


def test_ac4_an_approved_change_request_tells_venue_staff_too(client, db_session):
    w = _world(client, db_session)
    _approved(client, db_session, w, "Marina Hall")
    requested = client.post(
        f"/events/{w['event_id']}/change-requests",
        json={"description": "More people", "proposed_changes": {"expected_attendance": 200}},
        headers=w["org_h"],
    )
    assert requested.status_code == 201, requested.text

    approved = client.post(
        f"/events/change-requests/{requested.json()['id']}/approve", json={}, headers=w["coord_h"]
    )

    assert approved.status_code == 200, approved.text
    [message] = _inbox(client, w["vera_h"], CHANGED)
    assert message.endswith("expected attendance is now 200 (was 120).")


def test_ac4_a_change_to_other_details_sends_nothing(client, db_session):
    w = _world(client, db_session)
    _approved(client, db_session, w, "Marina Hall")

    _edit(client, w, description="A longer description.")

    assert _inbox(client, w["vera_h"], CHANGED) == []


def test_ac4_the_bookings_are_still_reopened_for_review(client, db_session):
    """Frozen: a new date still sends the Approved booking back for review."""
    w = _world(client, db_session)
    _approved(client, db_session, w, "Marina Hall")

    body = _edit(client, w, proposed_start="2026-11-03T09:00:00Z", proposed_end="2026-11-03T17:00:00Z")

    assert body["affected_venue_bookings"] == ["Marina Hall"]


# --- AC5: no Approved booking -> nothing; never anyone outside Venue Staff --


def test_ac5_an_event_with_only_a_pending_booking_sends_nothing(client, db_session):
    w = _world(client, db_session)
    _request(client, db_session, w, "Marina Hall")

    _edit(client, w, expected_attendance=150)

    assert _inbox(client, w["vera_h"], CHANGED) == []


def test_ac5_an_event_with_only_a_rejected_booking_sends_nothing(client, db_session):
    w = _world(client, db_session)
    ids = _request(client, db_session, w, "Marina Hall")
    client.post(f"/venue-bookings/{ids['Marina Hall']}/reject", json={"reason": "Full"}, headers=w["vera_h"])

    _edit(client, w, expected_attendance=150)

    assert _inbox(client, w["vera_h"], CHANGED) == []


def test_ac5_another_events_change_does_not_mention_this_venue(client, db_session):
    w = _world(client, db_session)
    _approved(client, db_session, w, "Marina Hall")
    other = Event(
        name="Unrelated Event", organiser_id=w["organiser"].id, coordinator_id=w["coordinator"].id,
        status=EventStatus.planning_event, expected_attendance=10,
        proposed_start=datetime(2026, 12, 1, 9, tzinfo=timezone.utc),
        proposed_end=datetime(2026, 12, 1, 17, tzinfo=timezone.utc),
    )
    db_session.add(other)
    db_session.commit()

    res = client.patch(f"/events/assigned/{other.id}/planning", json={"expected_attendance": 20}, headers=w["coord_h"])

    assert res.status_code == 200, res.text
    assert _inbox(client, w["vera_h"], CHANGED) == []


def test_ac5_only_venue_staff_get_the_change_notice(client, db_session):
    w = _world(client, db_session)
    _approved(client, db_session, w, "Marina Hall")

    _edit(client, w, expected_attendance=150)

    assert _recipients(db_session, CHANGED) == _venue_staff_ids(db_session)


# --- AC6: back to Planning after the Safety Check -> told -------------------


def _awaiting_safety(client, db_session):
    s = _ready(client, db_session)
    other_staff, other_h = user(client, db_session, Role.VENUE_STAFF, "other@example.com", "Otto Staff")
    assert _confirm(client, s).status_code == 200
    db_session.query(Notification).delete()
    db_session.commit()
    return {**s, "other_h": other_h}


@pytest.mark.parametrize(
    "action, body",
    [("reject", {"reason": "No fire exits"}), ("request-changes", {"reason": "No fire exits"})],
)
def test_ac6_a_failed_safety_check_tells_venue_staff_it_is_back_in_planning(client, db_session, action, body):
    s = _awaiting_safety(client, db_session)
    if action == "request-changes":
        line_id = client.get(f"/safety-checks/{s['event_id']}", headers=s["officer_h"]).json()["equipment"][0]["id"]
        body = {**body, "equipment_request_ids": [line_id]}

    res = client.post(f"/safety-checks/{s['event_id']}/{action}", json=body, headers=s["officer_h"])

    assert res.status_code == 200, res.text
    assert _inbox(client, s["other_h"], RETURNED) == [
        "'Regional Partner Conference' did not clear its Safety Check and is back in Planning Event. "
        "Reason: No fire exits"
    ]


def test_ac6_venue_staff_the_decision_already_reached_are_not_told_twice(client, db_session):
    s = _awaiting_safety(client, db_session)

    client.post(f"/safety-checks/{s['event_id']}/reject", json={"reason": "No fire exits"}, headers=s["officer_h"])

    told = client.get("/notifications", headers=s["staff_h"]).json()
    assert [n["type"] for n in told] == [NotificationType.safety_check_rejected.value]


def test_ac6_a_passed_safety_check_sends_nothing(client, db_session):
    s = _awaiting_safety(client, db_session)

    assert client.post(f"/safety-checks/{s['event_id']}/approve", headers=s["officer_h"]).status_code == 200

    assert _inbox(client, s["other_h"], RETURNED) == []


def test_ac6_only_venue_staff_get_the_back_in_planning_notice(client, db_session):
    s = _awaiting_safety(client, db_session)

    client.post(f"/safety-checks/{s['event_id']}/reject", json={"reason": "No fire exits"}, headers=s["officer_h"])

    assert _recipients(db_session, RETURNED) <= _venue_staff_ids(db_session)


# --- the classes --------------------------------------------------------------


def test_venue_staff_notices_extend_the_base_notice_with_their_own_types():
    for cls in (BookingRequestedNotice, ApprovedEventChangedNotice, SafetyReturnedNotice):
        assert issubclass(cls, VenueStaffNotice) and issubclass(cls, EventNotice)
    assert len({BookingRequestedNotice.type, ApprovedEventChangedNotice.type, SafetyReturnedNotice.type}) == 3


def test_a_change_with_no_approved_venue_or_nothing_changed_is_never_sent(db_session):
    event = Event(id=1, name="X")
    ApprovedEventChangedNotice((), ["it now runs later"]).send(db_session, event)
    ApprovedEventChangedNotice(("Marina Hall",), []).send(db_session, event)
    assert db_session.query(Notification).count() == 0
