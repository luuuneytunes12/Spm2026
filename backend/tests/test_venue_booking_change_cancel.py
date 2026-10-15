"""Tests for the "Change or Cancel One Venue Booking" story (SCRUM-96).

    As an Event Coordinator, I want to change or cancel one Venue Booking of
    an Event without touching the others, so that one room change does not
    undo the whole Event.

Acceptance criteria:

    AC1  When I cancel one of an Event's Venue Bookings, only that booking
         becomes "Cancelled" and the others stay unchanged.
    AC2  When I change the Venue (or the layout, accessibility or facilities
         I need from it) of one, only that booking returns to "Pending" for
         Venue Staff review, and does not count as approved until it is
         "Approved" again.
    AC3  When I choose to cancel all of an Event's Venue Bookings, the
         bookings to be cancelled are listed first and I must confirm again.
    AC4  When a Venue Booking is changed or cancelled, the Venue Staff are
         notified and the change is recorded in the Activity Log.

Test names carry the criterion they prove. The contract under test, all for
the Event's own Event Coordinator:

    PATCH  /venue-bookings/{booking_id}                  change one
    POST   /venue-bookings/{booking_id}/cancel           cancel one
    GET    /venue-bookings/events/{event_id}/cancellable the list to confirm
    POST   /venue-bookings/events/{event_id}/cancel-all  cancel the listed ones

A booking has no time of its own: it is the Event's. So "change" is the venue
and what is needed of it, never a time. (A booking's time following the
event's is a separate piece of work.)

The Activity Log is the Event's status history, written with the same status
before and after because the Event's status does not change (DoD 11a: a change
to one Venue Booking does not change the Event status by itself).
"""

import itertools
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.core.roles import Role
from app.core.security import create_access_token
from app.domain.event_readiness import outstanding_arrangements
from app.models.enums import PLANNING_STATUSES, BookingStatus, EventStatus, NotificationType
from app.models.events import Event, EventStatusHistory
from app.models.notifications import Notification
from app.models.user import User
from app.models.venues import Venue, VenueBooking

START = datetime(2026, 11, 2, 9, tzinfo=timezone.utc)
END = datetime(2026, 11, 2, 17, tzinfo=timezone.utc)

# Where a booking may be changed or cancelled: while the event is being
# planned. Once it goes to the Safety Officer the arrangement is judged as it
# stands, and only a send-back returns it here.
OUT_OF_WINDOW = [s for s in EventStatus if s not in PLANNING_STATUSES]
LIVE = [BookingStatus.pending, BookingStatus.tentative_hold, BookingStatus.approved]
SETTLED = [BookingStatus.rejected, BookingStatus.cancelled]
NEEDS = ["room_layout_preference", "accessibility_needs", "facilities_needs"]

_n = itertools.count()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _person(db, role, name):
    """A user of `role`, and their headers -- made directly, with the token
    /auth/login would have issued."""
    user = User(
        name=name, email=f"user{next(_n)}@example.com", password_hash="x", role=role.value
    )
    db.add(user)
    db.commit()
    return user, {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}


def _venue(db, name, **overrides):
    venue = Venue(
        name=name,
        location="10 Bayfront Ave",
        capacity=250,
        supported_layouts=["Theatre"],
        facilities=["Projector"],
        accessibility_features=["Wheelchair access"],
        **overrides,
    )
    db.add(venue)
    db.commit()
    return venue


def _event(db, organiser, coordinator, name="Regional Partner Conference", **overrides):
    event = Event(
        name=name,
        organiser_id=organiser.id,
        coordinator_id=coordinator.id if coordinator else None,
        status=overrides.pop("status", EventStatus.planning_event),
        proposed_start=START,
        proposed_end=END,
        expected_attendance=120,
        **overrides,
    )
    db.add(event)
    db.commit()
    return event


@pytest.fixture()
def world(client, db_session):
    """An event being planned with its Coordinator, two Venue Staff, the
    people who must NOT be told or allowed in, and four venues."""
    db = db_session
    organiser, organiser_h = _person(db, Role.ORGANISER, "Olivia Organiser")
    coordinator, coordinator_h = _person(db, Role.COORDINATOR, "Sam Coordinator")
    other, other_h = _person(db, Role.COORDINATOR, "Oscar Other")
    staff, staff_h = _person(db, Role.VENUE_STAFF, "Vera Staff")
    staff2, staff2_h = _person(db, Role.VENUE_STAFF, "Victor Staff")
    tech, tech_h = _person(db, Role.TECH_SUPPORT, "Tess Tech")
    attendee, attendee_h = _person(db, Role.ATTENDEE, "Alex Attendee")
    return SimpleNamespace(
        organiser=organiser, organiser_h=organiser_h,
        coordinator=coordinator, h=coordinator_h,
        other=other, other_h=other_h,
        staff=staff, staff_h=staff_h, staff2=staff2, staff2_h=staff2_h,
        tech=tech, tech_h=tech_h, attendee=attendee, attendee_h=attendee_h,
        marina=_venue(db, "Marina Hall"),
        garden=_venue(db, "Garden Hall"),
        sky=_venue(db, "Sky Room"),
        closed=_venue(db, "Closed Hall", is_active=False),
        event=_event(db, organiser, coordinator),
    )


def _booking(db, w, venue, status=BookingStatus.pending, event=None, **overrides):
    """One of an event's venue bookings, in any state. Its time is the
    event's, as the real request sets it."""
    event = event or w.event
    fields = dict(
        event_id=event.id,
        venue_id=venue.id,
        requested_by=w.coordinator.id,
        start_time=event.proposed_start,
        end_time=event.proposed_end,
        status=status,
    )
    if status is BookingStatus.approved:
        fields.update(reviewed_by=w.staff.id, reviewed_at=datetime.now(timezone.utc))
    if status is BookingStatus.tentative_hold:
        fields.update(
            reviewed_by=w.staff.id,
            reviewed_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
    if status is BookingStatus.rejected:
        fields.update(
            reviewed_by=w.staff.id, reviewed_at=datetime.now(timezone.utc), decision_notes="Closed."
        )
    fields.update(overrides)
    booking = VenueBooking(**fields)
    db.add(booking)
    db.commit()
    return booking


def _three(db, w):
    """An approved, a pending and a held booking: three venues, one event."""
    return (
        _booking(db, w, w.marina, BookingStatus.approved),
        _booking(db, w, w.garden, BookingStatus.pending),
        _booking(db, w, w.sky, BookingStatus.tentative_hold),
    )


_FIELDS = (
    "status", "venue_id", "room_layout_preference", "accessibility_needs", "facilities_needs",
    "start_time", "end_time", "reviewed_by", "reviewed_at", "decision_notes",
    "suggested_alternative", "expires_at", "safety_recheck_reason", "conflict_flagged_at",
)


def _snap(db, booking):
    """Everything about a booking, as the database holds it now."""
    db.expire_all()
    row = db.get(VenueBooking, booking.id)
    return {f: getattr(row, f) for f in _FIELDS}


def _status(db, booking):
    return _snap(db, booking)["status"]


def _log(db, event):
    db.expire_all()
    return list(
        db.query(EventStatusHistory).filter_by(event_id=event.id).order_by(EventStatusHistory.id)
    )


def _told(db, user):
    db.expire_all()
    return db.query(Notification).filter(Notification.user_id == user.id).all()


def _change(client, headers, booking_id, **body):
    return client.patch(f"/venue-bookings/{booking_id}", json=body, headers=headers)


def _cancel(client, headers, booking_id, **body):
    return client.post(f"/venue-bookings/{booking_id}/cancel", json=body, headers=headers)


def _preview(client, headers, event_id):
    return client.get(f"/venue-bookings/events/{event_id}/cancellable", headers=headers)


def _cancel_all(client, headers, event_id, ids, **body):
    return client.post(
        f"/venue-bookings/events/{event_id}/cancel-all",
        json={"booking_ids": list(ids), **body},
        headers=headers,
    )


def _nothing_happened(db, w, before_log, before_told):
    """No log line and no notification for anyone: what a refused action
    leaves behind."""
    assert len(_log(db, w.event)) == before_log
    assert sum(len(_told(db, u)) for u in (w.staff, w.staff2, w.coordinator, w.other)) == before_told


# ---------------------------------------------------------------------------
# AC1 -- cancel one booking
# ---------------------------------------------------------------------------


def test_scrum96_ac1_cancelling_one_booking_cancels_only_that_booking(client, db_session, world):
    w = world
    approved, pending, held = _three(db_session, w)
    others_before = {b.id: _snap(db_session, b) for b in (approved, held)}

    res = _cancel(client, w.h, pending.id)

    assert res.status_code == 200, res.text
    assert res.json()["status"] == "cancelled"
    assert _status(db_session, pending) is BookingStatus.cancelled
    for booking in (approved, held):
        assert _snap(db_session, booking) == others_before[booking.id]


@pytest.mark.parametrize("status", LIVE)
def test_scrum96_ac1_a_pending_held_or_approved_booking_can_be_cancelled(
    client, db_session, world, status
):
    w = world
    booking = _booking(db_session, w, w.marina, status)

    res = _cancel(client, w.h, booking.id)

    assert res.status_code == 200, res.text
    assert _status(db_session, booking) is BookingStatus.cancelled


def test_scrum96_ac1_the_event_is_not_cancelled_or_moved_on(client, db_session, world):
    """DoD 11a: a change to one Venue Booking does not change the Event
    status by itself. The event is still being planned."""
    w = world
    booking = _booking(db_session, w, w.marina, BookingStatus.approved)

    assert _cancel(client, w.h, booking.id).status_code == 200

    db_session.refresh(w.event)
    assert w.event.status is EventStatus.planning_event


def test_scrum96_ac1_a_cancelled_booking_no_longer_holds_the_venue(client, db_session, world):
    """Cancelling frees the venue: another event's request for the same time,
    refused while this booking was approved, can now be approved."""
    w = world
    mine = _booking(db_session, w, w.marina, BookingStatus.approved)
    rival_event = _event(db_session, w.organiser, w.other, name="Rival Summit")
    rival = _booking(
        db_session, w, w.marina, BookingStatus.pending, event=rival_event, requested_by=w.other.id
    )
    assert client.post(f"/venue-bookings/{rival.id}/approve", headers=w.staff_h).status_code == 409

    assert _cancel(client, w.h, mine.id).status_code == 200

    assert client.post(f"/venue-bookings/{rival.id}/approve", headers=w.staff_h).status_code == 200


def test_scrum96_ac1_a_conflict_flag_on_the_cancelled_booking_is_cleared(client, db_session, world):
    w = world
    flagged = _booking(
        db_session, w, w.marina, BookingStatus.approved,
        conflict_flagged_at=datetime.now(timezone.utc),
    )

    assert _cancel(client, w.h, flagged.id).status_code == 200

    assert _snap(db_session, flagged)["conflict_flagged_at"] is None


def test_scrum96_ac1_a_cancelled_booking_is_withdrawn_from_the_events_arrangements(
    client, db_session, world
):
    """The readiness check ignores a cancelled booking: with no other, the
    event has no venue; with another, only that one is waited for."""
    w = world
    approved = _booking(db_session, w, w.marina, BookingStatus.approved)
    pending = _booking(db_session, w, w.garden, BookingStatus.pending)

    assert _cancel(client, w.h, approved.id).status_code == 200
    db_session.refresh(w.event)
    left = outstanding_arrangements(db_session, w.event)
    assert any("Garden Hall" in line for line in left)
    assert not any("Marina Hall" in line for line in left)

    assert _cancel(client, w.h, pending.id).status_code == 200
    db_session.refresh(w.event)
    assert any("no venue" in line.lower() for line in outstanding_arrangements(db_session, w.event))


def test_scrum96_ac1_the_reason_is_optional_and_is_kept_in_the_log_and_the_notice(
    client, db_session, world
):
    """The reason is the Coordinator's, so it is NOT written into
    decision_notes, which is Venue Staff's: the booking would read as if they
    had given it."""
    w = world
    booking = _booking(db_session, w, w.marina, BookingStatus.approved)

    res = _cancel(client, w.h, booking.id, reason="The Organiser moved the panel to the garden")

    assert res.status_code == 200
    assert _snap(db_session, booking)["decision_notes"] is None
    assert "moved the panel to the garden" in _log(db_session, w.event)[-1].note
    assert "moved the panel to the garden" in _told(db_session, w.staff)[0].message


def test_scrum96_ac1_a_booking_can_be_cancelled_without_a_reason(client, db_session, world):
    w = world
    booking = _booking(db_session, w, w.marina, BookingStatus.pending)

    assert _cancel(client, w.h, booking.id).status_code == 200
    assert _cancel(client, w.h, _booking(db_session, w, w.garden).id, reason="  ").status_code == 200


@pytest.mark.parametrize("status", SETTLED)
def test_scrum96_ac1_a_rejected_or_cancelled_booking_cannot_be_cancelled(
    client, db_session, world, status
):
    w = world
    booking = _booking(db_session, w, w.marina, status)
    before, log, told = _snap(db_session, booking), len(_log(db_session, w.event)), 0

    res = _cancel(client, w.h, booking.id)

    assert res.status_code == 409
    assert _snap(db_session, booking) == before
    _nothing_happened(db_session, w, log, told)


def test_scrum96_ac1_cancelling_twice_is_refused_and_does_nothing_more(client, db_session, world):
    """The repeat: a double-click, or a second tab. One cancellation, one log
    line, one notice per Venue Staff."""
    w = world
    booking = _booking(db_session, w, w.marina, BookingStatus.approved)
    assert _cancel(client, w.h, booking.id).status_code == 200
    log, told = len(_log(db_session, w.event)), len(_told(db_session, w.staff))

    assert _cancel(client, w.h, booking.id).status_code == 409

    assert len(_log(db_session, w.event)) == log
    assert len(_told(db_session, w.staff)) == told == 1


@pytest.mark.parametrize("status", OUT_OF_WINDOW)
def test_scrum96_ac1_a_booking_cannot_be_cancelled_outside_planning(
    client, db_session, world, status
):
    """Once the event is with the Safety Officer (or finished) its venues are
    judged as they stand. A send-back returns the event to planning, and the
    booking can be cancelled again."""
    w = world
    booking = _booking(db_session, w, w.marina, BookingStatus.approved)
    w.event.status = status
    db_session.commit()
    before = _snap(db_session, booking)

    res = _cancel(client, w.h, booking.id)

    assert res.status_code == 409
    assert _snap(db_session, booking) == before
    _nothing_happened(db_session, w, 0, 0)


# ---------------------------------------------------------------------------
# AC2 -- change one booking
# ---------------------------------------------------------------------------


def test_scrum96_ac2_changing_the_venue_returns_only_that_booking_to_pending(
    client, db_session, world
):
    w = world
    approved, pending, held = _three(db_session, w)
    # a fourth venue to move to
    spare = _venue(db_session, "Spare Hall")
    others_before = {b.id: _snap(db_session, b) for b in (pending, held)}

    res = _change(client, w.h, approved.id, venue_id=spare.id)

    assert res.status_code == 200, res.text
    assert res.json()["status"] == "pending"
    assert res.json()["venue"]["id"] == spare.id
    row = _snap(db_session, approved)
    assert row["status"] is BookingStatus.pending and row["venue_id"] == spare.id
    for booking in (pending, held):
        assert _snap(db_session, booking) == others_before[booking.id]


@pytest.mark.parametrize("need", NEEDS)
def test_scrum96_ac2_changing_what_is_needed_of_the_venue_returns_it_to_pending(
    client, db_session, world, need
):
    w = world
    booking = _booking(db_session, w, w.marina, BookingStatus.approved)
    other = _booking(db_session, w, w.garden, BookingStatus.approved)
    other_before = _snap(db_session, other)

    res = _change(client, w.h, booking.id, **{need: "Classroom, with a lectern"})

    assert res.status_code == 200, res.text
    row = _snap(db_session, booking)
    assert row["status"] is BookingStatus.pending
    assert row[need] == "Classroom, with a lectern"
    assert _snap(db_session, other) == other_before


def test_scrum96_ac2_approval_is_no_longer_there_once_it_goes_back(client, db_session, world):
    """Nothing of the old decision is left to read as if it still applied."""
    w = world
    booking = _booking(
        db_session, w, w.marina, BookingStatus.approved,
        decision_notes="Approved with a note", suggested_alternative="Garden Hall",
        safety_recheck_reason="Check the exits", conflict_flagged_at=datetime.now(timezone.utc),
    )

    assert _change(client, w.h, booking.id, venue_id=w.sky.id).status_code == 200

    row = _snap(db_session, booking)
    assert row["reviewed_by"] is None and row["reviewed_at"] is None
    assert row["decision_notes"] is None and row["suggested_alternative"] is None
    assert row["safety_recheck_reason"] is None and row["conflict_flagged_at"] is None
    assert row["expires_at"] is None


def test_scrum96_ac2_a_pending_booking_stays_pending_with_the_change_applied(
    client, db_session, world
):
    w = world
    booking = _booking(db_session, w, w.marina, BookingStatus.pending)

    assert _change(client, w.h, booking.id, venue_id=w.sky.id).status_code == 200

    assert _snap(db_session, booking)["venue_id"] == w.sky.id
    queue = client.get("/venue-bookings/queue", headers=w.staff_h).json()
    assert [b["id"] for b in queue] == [booking.id]
    assert queue[0]["venue"]["id"] == w.sky.id


def test_scrum96_ac2_a_held_booking_goes_to_pending_and_the_hold_is_dropped(
    client, db_session, world
):
    """The hold was on the old venue. It is a pending request for the new one."""
    w = world
    booking = _booking(db_session, w, w.marina, BookingStatus.tentative_hold)

    assert _change(client, w.h, booking.id, venue_id=w.sky.id).status_code == 200

    row = _snap(db_session, booking)
    assert row["status"] is BookingStatus.pending and row["expires_at"] is None


def test_scrum96_ac2_it_does_not_count_as_approved_until_it_is_approved_again(
    client, db_session, world
):
    w = world
    mine = _booking(db_session, w, w.marina, BookingStatus.approved)
    rival_event = _event(db_session, w.organiser, w.other, name="Rival Summit")
    rival = _booking(
        db_session, w, w.marina, BookingStatus.pending, event=rival_event, requested_by=w.other.id
    )

    # while it is approved it holds Marina Hall against the rival
    assert client.post(f"/venue-bookings/{rival.id}/approve", headers=w.staff_h).status_code == 409

    assert _change(client, w.h, mine.id, room_layout_preference="Classroom").status_code == 200

    # (a) not approved: the event is waiting on it
    db_session.refresh(w.event)
    lines = outstanding_arrangements(db_session, w.event)
    assert any("Marina Hall" in line and "pending" in line for line in lines)
    # (b) and it no longer holds the venue
    assert client.post(f"/venue-bookings/{rival.id}/approve", headers=w.staff_h).status_code == 200
    # (c) so it cannot be approved again over the rival, until that clears
    assert client.post(f"/venue-bookings/{mine.id}/approve", headers=w.staff_h).status_code == 409


def test_scrum96_ac2_it_counts_again_once_venue_staff_approve_it(client, db_session, world):
    w = world
    booking = _booking(db_session, w, w.marina, BookingStatus.approved)
    assert _change(client, w.h, booking.id, venue_id=w.sky.id).status_code == 200

    assert client.post(f"/venue-bookings/{booking.id}/approve", headers=w.staff_h).status_code == 200

    assert _status(db_session, booking) is BookingStatus.approved
    db_session.refresh(w.event)
    assert not any("Sky Room" in line for line in outstanding_arrangements(db_session, w.event))


def test_scrum96_ac2_the_event_is_not_cancelled_or_moved_on(client, db_session, world):
    w = world
    booking = _booking(db_session, w, w.marina, BookingStatus.approved)

    assert _change(client, w.h, booking.id, venue_id=w.sky.id).status_code == 200

    db_session.refresh(w.event)
    assert w.event.status is EventStatus.planning_event


def test_scrum96_ac2_a_bookings_time_is_the_events_and_cannot_be_changed_here(
    client, db_session, world
):
    """A booking has no time of its own. A time sent anyway is ignored, not
    applied: the booking still follows the event."""
    w = world
    booking = _booking(db_session, w, w.marina, BookingStatus.approved)

    res = _change(
        client, w.h, booking.id,
        venue_id=w.sky.id, start_time="2030-01-01T00:00:00Z", end_time="2030-01-01T02:00:00Z",
    )

    assert res.status_code == 200
    row = _snap(db_session, booking)
    db_session.refresh(w.event)
    assert row["start_time"] == w.event.proposed_start and row["end_time"] == w.event.proposed_end


def test_scrum96_ac2_the_booking_keeps_its_identity_and_its_requester(client, db_session, world):
    w = world
    booking = _booking(db_session, w, w.marina, BookingStatus.approved)

    res = _change(client, w.h, booking.id, venue_id=w.sky.id)

    assert res.json()["id"] == booking.id
    assert _snap(db_session, booking)["status"] is BookingStatus.pending
    db_session.expire_all()
    assert db_session.get(VenueBooking, booking.id).requested_by == w.coordinator.id
    assert db_session.query(VenueBooking).filter_by(event_id=w.event.id).count() == 1


def test_scrum96_ac2_a_blank_need_goes_back_to_what_the_event_says(client, db_session, world):
    w = world
    booking = _booking(
        db_session, w, w.marina, BookingStatus.approved, facilities_needs="Projector"
    )

    assert _change(client, w.h, booking.id, facilities_needs="   ").status_code == 200

    row = _snap(db_session, booking)
    assert row["facilities_needs"] is None and row["status"] is BookingStatus.pending


def test_scrum96_ac2_a_venue_the_event_already_has_is_refused(client, db_session, world):
    w = world
    booking = _booking(db_session, w, w.marina, BookingStatus.approved)
    _booking(db_session, w, w.garden, BookingStatus.pending)
    before = _snap(db_session, booking)

    res = _change(client, w.h, booking.id, venue_id=w.garden.id)

    assert res.status_code == 409
    assert _snap(db_session, booking) == before
    _nothing_happened(db_session, w, 0, 0)


def test_scrum96_ac2_a_venue_the_event_once_cancelled_can_be_chosen_again(client, db_session, world):
    w = world
    booking = _booking(db_session, w, w.marina, BookingStatus.approved)
    _booking(db_session, w, w.garden, BookingStatus.cancelled)

    assert _change(client, w.h, booking.id, venue_id=w.garden.id).status_code == 200


def test_scrum96_ac2_an_unknown_or_inactive_venue_is_refused(client, db_session, world):
    w = world
    booking = _booking(db_session, w, w.marina, BookingStatus.approved)
    before = _snap(db_session, booking)

    assert _change(client, w.h, booking.id, venue_id=99999).status_code == 422
    assert _change(client, w.h, booking.id, venue_id=w.closed.id).status_code == 422

    assert _snap(db_session, booking) == before
    _nothing_happened(db_session, w, 0, 0)


@pytest.mark.parametrize(
    "body",
    [{}, {"venue_id": "same"}, {"room_layout_preference": "Theatre"}, {"facilities_needs": ""}],
    ids=["empty", "same venue", "same layout", "blank need that was already blank"],
)
def test_scrum96_ac2_a_change_that_changes_nothing_is_refused(client, db_session, world, body):
    """Nothing to review, so nothing goes back to Venue Staff, and a repeat of
    a change already made is not a second change."""
    w = world
    booking = _booking(
        db_session, w, w.marina, BookingStatus.approved, room_layout_preference="Theatre"
    )
    body = {k: (w.marina.id if v == "same" else v) for k, v in body.items()}
    before = _snap(db_session, booking)

    res = _change(client, w.h, booking.id, **body)

    assert res.status_code == 422
    assert _snap(db_session, booking) == before
    _nothing_happened(db_session, w, 0, 0)


def test_scrum96_ac2_the_same_change_twice_is_one_change(client, db_session, world):
    w = world
    booking = _booking(db_session, w, w.marina, BookingStatus.approved)
    assert _change(client, w.h, booking.id, venue_id=w.sky.id).status_code == 200
    log, told = len(_log(db_session, w.event)), len(_told(db_session, w.staff))

    assert _change(client, w.h, booking.id, venue_id=w.sky.id).status_code == 422

    assert len(_log(db_session, w.event)) == log
    assert len(_told(db_session, w.staff)) == told == 1


@pytest.mark.parametrize("status", SETTLED)
def test_scrum96_ac2_a_rejected_or_cancelled_booking_cannot_be_changed(
    client, db_session, world, status
):
    """It is history: a new request is how another venue is asked."""
    w = world
    booking = _booking(db_session, w, w.marina, status)
    before = _snap(db_session, booking)

    res = _change(client, w.h, booking.id, venue_id=w.sky.id)

    assert res.status_code == 409
    assert _snap(db_session, booking) == before
    _nothing_happened(db_session, w, 0, 0)


@pytest.mark.parametrize("status", OUT_OF_WINDOW)
def test_scrum96_ac2_a_booking_cannot_be_changed_outside_planning(
    client, db_session, world, status
):
    w = world
    booking = _booking(db_session, w, w.marina, BookingStatus.approved)
    w.event.status = status
    db_session.commit()
    before = _snap(db_session, booking)

    res = _change(client, w.h, booking.id, venue_id=w.sky.id)

    assert res.status_code == 409
    assert _snap(db_session, booking) == before
    _nothing_happened(db_session, w, 0, 0)


# ---------------------------------------------------------------------------
# AC3 -- cancel all, listed first, confirmed again
# ---------------------------------------------------------------------------


def test_scrum96_ac3_the_bookings_to_be_cancelled_are_listed_first(client, db_session, world):
    w = world
    approved, pending, held = _three(db_session, w)
    _booking(db_session, w, w.closed, BookingStatus.rejected)
    _booking(db_session, w, _venue(db_session, "Old Hall"), BookingStatus.cancelled)

    res = _preview(client, w.h, w.event.id)

    assert res.status_code == 200
    listed = res.json()
    assert [b["id"] for b in listed] == [approved.id, pending.id, held.id]
    assert [b["venue"]["name"] for b in listed] == ["Marina Hall", "Garden Hall", "Sky Room"]
    assert [b["status"] for b in listed] == ["approved", "pending", "tentative_hold"]


def test_scrum96_ac3_listing_changes_nothing(client, db_session, world):
    w = world
    bookings = _three(db_session, w)
    before = {b.id: _snap(db_session, b) for b in bookings}

    assert _preview(client, w.h, w.event.id).status_code == 200

    assert {b.id: _snap(db_session, b) for b in bookings} == before
    _nothing_happened(db_session, w, 0, 0)


def test_scrum96_ac3_confirming_the_list_cancels_those_bookings_and_only_those(
    client, db_session, world
):
    w = world
    approved, pending, held = _three(db_session, w)
    rejected = _booking(db_session, w, w.closed, BookingStatus.rejected)
    rival_event = _event(db_session, w.organiser, w.other, name="Rival Summit")
    rival = _booking(
        db_session, w, w.marina, BookingStatus.pending, event=rival_event, requested_by=w.other.id
    )
    untouched = {b.id: _snap(db_session, b) for b in (rejected, rival)}
    ids = [b["id"] for b in _preview(client, w.h, w.event.id).json()]

    res = _cancel_all(client, w.h, w.event.id, ids)

    assert res.status_code == 200, res.text
    assert sorted(b["id"] for b in res.json()) == sorted(ids)
    assert all(b["status"] == "cancelled" for b in res.json())
    for booking in (approved, pending, held):
        assert _status(db_session, booking) is BookingStatus.cancelled
    for booking in (rejected, rival):
        assert _snap(db_session, booking) == untouched[booking.id]


def test_scrum96_ac3_the_event_is_not_cancelled_but_has_no_venue_left(client, db_session, world):
    w = world
    _three(db_session, w)
    ids = [b["id"] for b in _preview(client, w.h, w.event.id).json()]

    assert _cancel_all(client, w.h, w.event.id, ids).status_code == 200

    db_session.refresh(w.event)
    assert w.event.status is EventStatus.planning_event
    assert any("no venue" in line.lower() for line in outstanding_arrangements(db_session, w.event))


def test_scrum96_ac3_a_request_without_the_list_it_was_shown_cancels_nothing(
    client, db_session, world
):
    """The second confirmation is enforced by the server, not just the page:
    cancelling needs the ids that were listed."""
    w = world
    bookings = _three(db_session, w)
    before = {b.id: _snap(db_session, b) for b in bookings}

    assert client.post(
        f"/venue-bookings/events/{w.event.id}/cancel-all", json={}, headers=w.h
    ).status_code == 422
    assert _cancel_all(client, w.h, w.event.id, []).status_code == 422

    assert {b.id: _snap(db_session, b) for b in bookings} == before
    _nothing_happened(db_session, w, 0, 0)


def test_scrum96_ac3_a_list_that_has_gone_stale_cancels_nothing(client, db_session, world):
    """A booking was added after the list was shown. Cancelling only what was
    listed would leave the Coordinator believing everything is cancelled, and
    cancelling the new one would cancel something they never saw."""
    w = world
    approved, pending, held = _three(db_session, w)
    shown = [b["id"] for b in _preview(client, w.h, w.event.id).json()]
    late = _booking(db_session, w, _venue(db_session, "Late Hall"), BookingStatus.pending)
    before = {b.id: _snap(db_session, b) for b in (approved, pending, held, late)}

    res = _cancel_all(client, w.h, w.event.id, shown)

    assert res.status_code == 409
    assert {b.id: _snap(db_session, b) for b in (approved, pending, held, late)} == before
    _nothing_happened(db_session, w, 0, 0)
    # and a fresh list now includes the new booking
    assert late.id in [b["id"] for b in _preview(client, w.h, w.event.id).json()]


def test_scrum96_ac3_a_list_with_a_booking_that_is_no_longer_live_cancels_nothing(
    client, db_session, world
):
    w = world
    approved, pending, held = _three(db_session, w)
    shown = [b["id"] for b in _preview(client, w.h, w.event.id).json()]
    assert _cancel(client, w.h, pending.id).status_code == 200
    before = {b.id: _snap(db_session, b) for b in (approved, held)}
    log = len(_log(db_session, w.event))

    res = _cancel_all(client, w.h, w.event.id, shown)

    assert res.status_code == 409
    assert {b.id: _snap(db_session, b) for b in (approved, held)} == before
    assert len(_log(db_session, w.event)) == log


def test_scrum96_ac3_another_events_booking_in_the_list_is_refused_and_untouched(
    client, db_session, world
):
    w = world
    approved, pending, held = _three(db_session, w)
    rival_event = _event(db_session, w.organiser, w.other, name="Rival Summit")
    rival = _booking(
        db_session, w, w.marina, BookingStatus.pending, event=rival_event, requested_by=w.other.id
    )
    shown = [b["id"] for b in _preview(client, w.h, w.event.id).json()]
    rival_before = _snap(db_session, rival)

    res = _cancel_all(client, w.h, w.event.id, [*shown, rival.id])

    assert res.status_code == 409
    assert _snap(db_session, rival) == rival_before
    assert _status(db_session, approved) is BookingStatus.approved


def test_scrum96_ac3_an_event_with_nothing_to_cancel_says_so(client, db_session, world):
    w = world
    _booking(db_session, w, w.marina, BookingStatus.rejected)

    assert _preview(client, w.h, w.event.id).json() == []
    assert _cancel_all(client, w.h, w.event.id, [1]).status_code == 409


def test_scrum96_ac3_confirming_twice_is_refused_the_second_time(client, db_session, world):
    w = world
    _three(db_session, w)
    ids = [b["id"] for b in _preview(client, w.h, w.event.id).json()]
    assert _cancel_all(client, w.h, w.event.id, ids).status_code == 200
    log = len(_log(db_session, w.event))
    told = len(_told(db_session, w.staff))

    assert _cancel_all(client, w.h, w.event.id, ids).status_code == 409

    assert len(_log(db_session, w.event)) == log
    assert len(_told(db_session, w.staff)) == told


def test_scrum96_ac3_a_reason_is_optional_and_goes_on_each_bookings_record(
    client, db_session, world
):
    w = world
    _three(db_session, w)
    ids = [b["id"] for b in _preview(client, w.h, w.event.id).json()]

    res = _cancel_all(client, w.h, w.event.id, ids, reason="The event is moving venue entirely")

    assert res.status_code == 200
    notes = [h.note for h in _log(db_session, w.event)]
    assert len(notes) == 3
    assert all("moving venue entirely" in n for n in notes)


@pytest.mark.parametrize("status", OUT_OF_WINDOW)
def test_scrum96_ac3_nothing_is_listed_or_cancelled_outside_planning(
    client, db_session, world, status
):
    w = world
    bookings = _three(db_session, w)
    ids = [b.id for b in bookings]
    w.event.status = status
    db_session.commit()
    before = {b.id: _snap(db_session, b) for b in bookings}

    assert _preview(client, w.h, w.event.id).status_code == 409
    assert _cancel_all(client, w.h, w.event.id, ids).status_code == 409

    assert {b.id: _snap(db_session, b) for b in bookings} == before
    _nothing_happened(db_session, w, 0, 0)


# ---------------------------------------------------------------------------
# AC4 -- Venue Staff are told, and the Activity Log records it
# ---------------------------------------------------------------------------


def test_scrum96_ac4_cancelling_tells_every_venue_staff_member_once(client, db_session, world):
    w = world
    booking = _booking(db_session, w, w.marina, BookingStatus.approved)

    assert _cancel(client, w.h, booking.id).status_code == 200

    for staff in (w.staff, w.staff2):
        [notice] = _told(db_session, staff)
        assert notice.type == NotificationType.venue_booking_cancelled
        assert notice.event_id == w.event.id
        assert "Marina Hall" in notice.message
        assert "Regional Partner Conference" in notice.message
        assert "cancel" in notice.message.lower()


def test_scrum96_ac4_changing_the_venue_tells_venue_staff_both_venues(client, db_session, world):
    w = world
    booking = _booking(db_session, w, w.marina, BookingStatus.approved)

    assert _change(client, w.h, booking.id, venue_id=w.sky.id).status_code == 200

    for staff in (w.staff, w.staff2):
        [notice] = _told(db_session, staff)
        assert notice.type == NotificationType.venue_booking_changed
        assert notice.event_id == w.event.id
        assert "Marina Hall" in notice.message and "Sky Room" in notice.message
        assert "Regional Partner Conference" in notice.message


def test_scrum96_ac4_changing_a_need_tells_venue_staff_what_changed(client, db_session, world):
    w = world
    booking = _booking(db_session, w, w.marina, BookingStatus.approved)

    assert _change(client, w.h, booking.id, room_layout_preference="Classroom").status_code == 200

    [notice] = _told(db_session, w.staff)
    assert notice.type == NotificationType.venue_booking_changed
    assert "Marina Hall" in notice.message and "Classroom" in notice.message


def test_scrum96_ac4_nobody_outside_venue_staff_is_told(client, db_session, world):
    """The recipients are Venue Staff and nobody else: not the Coordinator
    who did it, another Coordinator, the Organiser, Technical Support or an
    Attendee."""
    w = world
    a, b, c = _three(db_session, w)

    assert _change(client, w.h, a.id, venue_id=_venue(db_session, "Spare Hall").id).status_code == 200
    assert _cancel(client, w.h, b.id, reason="Not needed").status_code == 200
    ids = [x["id"] for x in _preview(client, w.h, w.event.id).json()]
    assert _cancel_all(client, w.h, w.event.id, ids).status_code == 200

    for outsider in (w.coordinator, w.other, w.organiser, w.tech, w.attendee):
        assert _told(db_session, outsider) == [], outsider.name


def test_scrum96_ac4_the_activity_log_records_who_what_and_when(client, db_session, world):
    w = world
    booking = _booking(db_session, w, w.marina, BookingStatus.approved)

    assert _change(client, w.h, booking.id, venue_id=w.sky.id).status_code == 200

    [entry] = _log(db_session, w.event)
    assert entry.changed_by == w.coordinator.id
    assert entry.created_at is not None
    assert "changed" in entry.note.lower()
    assert "Marina Hall" in entry.note and "Sky Room" in entry.note


def test_scrum96_ac4_cancelling_is_logged_with_the_venue_and_who_did_it(client, db_session, world):
    w = world
    booking = _booking(db_session, w, w.marina, BookingStatus.approved)

    assert _cancel(client, w.h, booking.id, reason="Roof leak").status_code == 200

    [entry] = _log(db_session, w.event)
    assert entry.changed_by == w.coordinator.id
    assert "cancelled" in entry.note.lower() and "Marina Hall" in entry.note
    assert "Roof leak" in entry.note


def test_scrum96_ac4_the_log_line_leaves_the_events_status_as_it_was(client, db_session, world):
    """It is an Activity Log line, not a status change: same status before and
    after (DoD 11a)."""
    w = world
    booking = _booking(db_session, w, w.marina, BookingStatus.approved)

    assert _cancel(client, w.h, booking.id).status_code == 200

    [entry] = _log(db_session, w.event)
    assert entry.from_status == entry.to_status == EventStatus.planning_event


def test_scrum96_ac4_cancelling_all_logs_and_tells_for_each_booking(client, db_session, world):
    w = world
    _three(db_session, w)
    ids = [b["id"] for b in _preview(client, w.h, w.event.id).json()]

    assert _cancel_all(client, w.h, w.event.id, ids).status_code == 200

    notes = [h.note for h in _log(db_session, w.event)]
    assert len(notes) == 3
    for venue in ("Marina Hall", "Garden Hall", "Sky Room"):
        assert sum(venue in n for n in notes) == 1
    for staff in (w.staff, w.staff2):
        told = _told(db_session, staff)
        assert len(told) == 3
        assert {n.type for n in told} == {NotificationType.venue_booking_cancelled}


# ---------------------------------------------------------------------------
# Who may do it -- every endpoint, server-side
# ---------------------------------------------------------------------------


def _every_call(client, headers, w, booking_id):
    return [
        _change(client, headers, booking_id, venue_id=w.sky.id),
        _cancel(client, headers, booking_id),
        _preview(client, headers, w.event.id),
        _cancel_all(client, headers, w.event.id, [booking_id]),
    ]


@pytest.mark.parametrize(
    "role",
    [Role.ORGANISER, Role.VENUE_STAFF, Role.TECH_SUPPORT, Role.ATTENDEE,
     Role.COORDINATOR_LEAD, Role.SAFETY_OFFICER],
)
def test_scrum96_only_a_coordinator_may_change_or_cancel(client, db_session, world, role):
    w = world
    booking = _booking(db_session, w, w.marina, BookingStatus.approved)
    _, headers = _person(db_session, role, "Someone")
    before = _snap(db_session, booking)

    assert [r.status_code for r in _every_call(client, headers, w, booking.id)] == [403] * 4

    assert _snap(db_session, booking) == before
    _nothing_happened(db_session, w, 0, 0)


def test_scrum96_an_anonymous_caller_is_unauthenticated(client, db_session, world):
    w = world
    booking = _booking(db_session, w, w.marina, BookingStatus.approved)

    results = [
        client.patch(f"/venue-bookings/{booking.id}", json={"venue_id": w.sky.id}),
        client.post(f"/venue-bookings/{booking.id}/cancel", json={}),
        client.get(f"/venue-bookings/events/{w.event.id}/cancellable"),
        client.post(f"/venue-bookings/events/{w.event.id}/cancel-all", json={"booking_ids": [booking.id]}),
    ]

    assert [r.status_code for r in results] == [401] * 4
    assert _status(db_session, booking) is BookingStatus.approved


def test_scrum96_another_coordinators_event_is_not_found(client, db_session, world):
    """"Not yours" and "does not exist" look the same, so ids cannot be probed."""
    w = world
    booking = _booking(db_session, w, w.marina, BookingStatus.approved)
    before = _snap(db_session, booking)

    results = _every_call(client, w.other_h, w, booking.id)

    assert [r.status_code for r in results] == [404] * 4
    assert _snap(db_session, booking) == before
    _nothing_happened(db_session, w, 0, 0)


def test_scrum96_an_event_with_no_coordinator_is_not_found(client, db_session, world):
    w = world
    booking = _booking(db_session, w, w.marina, BookingStatus.approved)
    w.event.coordinator_id = None
    db_session.commit()

    assert [r.status_code for r in _every_call(client, w.h, w, booking.id)] == [404] * 4
    assert _status(db_session, booking) is BookingStatus.approved


def test_scrum96_an_unknown_booking_or_event_is_not_found(client, db_session, world):
    w = world
    assert _change(client, w.h, 99999, venue_id=w.sky.id).status_code == 404
    assert _cancel(client, w.h, 99999).status_code == 404
    assert _preview(client, w.h, 99999).status_code == 404
    assert _cancel_all(client, w.h, 99999, [1]).status_code == 404
