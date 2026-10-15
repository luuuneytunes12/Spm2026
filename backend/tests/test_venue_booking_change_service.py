"""Unit tests for the classes behind "Change or Cancel One Venue Booking".

test_venue_booking_change_cancel.py proves the behaviour through HTTP. These
call the classes directly, with no web layer, to show where the rules live:

    BookingChange (value object)
        What a change was: the venue before and after, and each need before
        and after. It decides whether anything changed at all, and puts the
        change into words for the Activity Log and for Venue Staff.

    VenueStaffRecipients (abstract)
        Who is told. AllVenueStaff is today's rule: no document assigns Venue
        Staff to venues, and their queue is already global. A rule that tells
        only the staff of the venues involved is a different subclass, handed
        to the service in its place -- the service never knows which.

    ActivityLog (abstract) / EventHistoryLog
        Where the record goes. The real one writes the Event's status history.

    VenueBookingChangeService
        The rules and the orchestration, with both of the above injected.
        Like the other domain services it does not commit: the route does.
"""

import dataclasses
import itertools
from datetime import datetime, timedelta, timezone

import pytest

from app.core.roles import Role
from app.domain.errors import Conflict, DomainError, InvalidInput, NotFound
from app.domain.venue_booking_changes import (
    VENUE_CHANGE_EVENT_STATUSES,
    ActivityLog,
    AllVenueStaff,
    BookingChange,
    EventHistoryLog,
    VenueBookingChangeService,
    VenueStaffRecipients,
)
from app.models.enums import BookingStatus, EventStatus, NotificationType
from app.models.events import Event, EventStatusHistory
from app.models.notifications import Notification
from app.models.user import User
from app.models.venues import Venue, VenueBooking
from app.routers.venue_bookings import BOOKABLE_EVENT_STATUSES

START = datetime(2026, 11, 2, 9, tzinfo=timezone.utc)
END = datetime(2026, 11, 2, 17, tzinfo=timezone.utc)
_n = itertools.count()


# ---------------------------------------------------------------------------
# The window -- kept in step with requesting a venue
# ---------------------------------------------------------------------------


def test_the_window_for_changing_is_the_window_for_requesting():
    """A booking can be changed or cancelled in the same statuses in which a
    venue can be requested.

    That is deliberate, and it is the one place to look when the two should
    move together. W7 #2 says that when a booked venue becomes unavailable the
    Coordinator must be able to request a replacement -- which can be after
    the Safety Check. Requesting is limited to planning today. If that is
    widened, this test fails, and changing and cancelling must be widened
    with it: a Coordinator who can ask for a replacement but not withdraw
    the booking it replaces would be stuck."""
    assert tuple(VENUE_CHANGE_EVENT_STATUSES) == tuple(BOOKABLE_EVENT_STATUSES)


# ---------------------------------------------------------------------------
# BookingChange
# ---------------------------------------------------------------------------

NO_NEEDS = {"room_layout_preference": None, "accessibility_needs": None, "facilities_needs": None}


def _change(venue_after="Marina Hall", needs_after=None, needs_before=None):
    return BookingChange(
        venue_before="Marina Hall",
        venue_after=venue_after,
        needs_before={**NO_NEEDS, "room_layout_preference": "Theatre", **(needs_before or {})},
        needs_after={**NO_NEEDS, "room_layout_preference": "Theatre", **(needs_after or {})},
    )


def test_a_change_with_nothing_different_is_empty():
    change = _change()

    assert change.is_empty
    assert change.changed_fields == []


def test_a_new_venue_is_a_change():
    change = _change(venue_after="Garden Hall")

    assert not change.is_empty
    assert change.changed_fields == ["venue"]


def test_a_need_that_differs_is_a_change_and_is_named():
    change = _change(needs_after={"room_layout_preference": "Classroom"})

    assert change.changed_fields == ["room_layout_preference"]


def test_every_change_is_named_in_a_fixed_order():
    change = _change(
        venue_after="Garden Hall",
        needs_after={"facilities_needs": "Projector", "room_layout_preference": "Classroom"},
    )

    assert change.changed_fields == ["venue", "room_layout_preference", "facilities_needs"]


def test_the_summary_names_the_old_and_the_new_venue():
    summary = _change(venue_after="Garden Hall").summary()

    assert "Marina Hall" in summary and "Garden Hall" in summary


def test_the_summary_names_the_old_and_the_new_need():
    summary = _change(needs_after={"room_layout_preference": "Classroom"}).summary()

    assert "Theatre" in summary and "Classroom" in summary


def test_a_need_given_up_reads_as_what_the_event_says():
    summary = _change(needs_after={"room_layout_preference": None}).summary()

    assert "as the event says" in summary.lower()


def test_the_summary_leaves_out_what_did_not_change():
    summary = _change(
        venue_after="Garden Hall", needs_before={"facilities_needs": "Projector"},
        needs_after={"facilities_needs": "Projector"},
    ).summary()

    assert "Projector" not in summary and "Theatre" not in summary


def test_a_change_cannot_be_altered_once_made():
    change = _change()

    with pytest.raises(dataclasses.FrozenInstanceError):
        change.venue_after = "Elsewhere"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Database-backed fixtures
# ---------------------------------------------------------------------------


def _user(db, role, name="Someone"):
    user = User(name=name, email=f"u{next(_n)}@example.com", password_hash="x", role=role.value)
    db.add(user)
    db.flush()
    return user


def _venue(db, name):
    venue = Venue(name=name, location="Here", capacity=100)
    db.add(venue)
    db.flush()
    return venue


@pytest.fixture()
def world(db_session):
    db = db_session
    organiser = _user(db, Role.ORGANISER, "Olivia")
    coordinator = _user(db, Role.COORDINATOR, "Sam")
    other = _user(db, Role.COORDINATOR, "Oscar")
    staff = [_user(db, Role.VENUE_STAFF, "Vera"), _user(db, Role.VENUE_STAFF, "Victor")]
    outsiders = [_user(db, Role.TECH_SUPPORT, "Tess"), _user(db, Role.ATTENDEE, "Alex"), organiser, other]
    event = Event(
        name="Conference", organiser_id=organiser.id, coordinator_id=coordinator.id,
        status=EventStatus.planning_event, proposed_start=START, proposed_end=END,
    )
    db.add(event)
    db.flush()
    venues = {name: _venue(db, name) for name in ("Marina Hall", "Garden Hall", "Sky Room")}
    db.commit()

    class World:
        pass

    w = World()
    w.db, w.coordinator, w.other, w.staff, w.outsiders = db, coordinator, other, staff, outsiders
    w.event, w.venues = event, venues
    return w


def _booking(w, venue, status=BookingStatus.pending, **overrides):
    fields = dict(
        event_id=w.event.id, venue_id=w.venues[venue].id, requested_by=w.coordinator.id,
        start_time=START, end_time=END, status=status,
    )
    if status is BookingStatus.approved:
        fields.update(reviewed_by=w.staff[0].id, reviewed_at=datetime.now(timezone.utc))
    if status is BookingStatus.tentative_hold:
        fields.update(expires_at=datetime.now(timezone.utc) + timedelta(hours=24))
    fields.update(overrides)
    booking = VenueBooking(**fields)
    w.db.add(booking)
    w.db.commit()
    return booking


class FakeActivityLog(ActivityLog):
    """An Activity Log that just remembers what it was told."""

    def __init__(self):
        self.entries = []

    def record(self, event, actor, note):
        self.entries.append((event.id, actor.id, note))


class StaffOfOneVenue(VenueStaffRecipients):
    """A different rule for who is told: only the staff given for a venue.
    What a per-venue assignment would look like -- here to show the service
    takes whichever rule it is handed."""

    def __init__(self, by_venue_id):
        self._by_venue_id = by_venue_id

    def for_venues(self, venue_ids):
        told, seen = [], set()
        for venue_id in venue_ids:
            for user in self._by_venue_id.get(venue_id, []):
                if user.id not in seen:
                    seen.add(user.id)
                    told.append(user)
        return told


def _service(w, recipients=None, activity=None):
    return VenueBookingChangeService(
        w.db,
        recipients if recipients is not None else AllVenueStaff(w.db),
        activity if activity is not None else EventHistoryLog(w.db),
    )


def _notices(w, user):
    w.db.flush()
    return w.db.query(Notification).filter_by(user_id=user.id).all()


# ---------------------------------------------------------------------------
# VenueStaffRecipients
# ---------------------------------------------------------------------------


def test_recipients_cannot_be_used_without_saying_who():
    with pytest.raises(TypeError):
        VenueStaffRecipients()  # abstract


def test_all_venue_staff_is_every_venue_staff_member_and_nobody_else(world):
    told = AllVenueStaff(world.db).for_venues([world.venues["Marina Hall"].id])

    assert [u.id for u in told] == [u.id for u in world.staff]
    for outsider in world.outsiders:
        assert outsider.id not in [u.id for u in told]


def test_all_venue_staff_lists_each_person_once_whichever_venues_are_given(world):
    ids = [world.venues["Marina Hall"].id, world.venues["Garden Hall"].id]

    told = AllVenueStaff(world.db).for_venues(ids)

    assert len({u.id for u in told}) == len(told) == len(world.staff)


# ---------------------------------------------------------------------------
# EventHistoryLog
# ---------------------------------------------------------------------------


def test_the_event_history_log_writes_a_line_that_changes_no_status(world):
    EventHistoryLog(world.db).record(world.event, world.coordinator, "Something happened")
    world.db.flush()

    [entry] = world.db.query(EventStatusHistory).all()
    assert entry.event_id == world.event.id and entry.changed_by == world.coordinator.id
    assert entry.from_status == entry.to_status == EventStatus.planning_event
    assert entry.note == "Something happened"


# ---------------------------------------------------------------------------
# VenueBookingChangeService
# ---------------------------------------------------------------------------


def test_changing_the_venue_sends_the_booking_back_to_pending(world):
    booking = _booking(world, "Marina Hall", BookingStatus.approved)

    changed = _service(world).change(
        booking.id, world.coordinator, venue_id=world.venues["Sky Room"].id
    )

    assert changed.status is BookingStatus.pending
    assert changed.venue_id == world.venues["Sky Room"].id
    assert changed.reviewed_by is None and changed.reviewed_at is None


def test_the_service_does_not_commit(world):
    """The route commits. A service that committed could not be undone by a
    failure later in the same request."""
    booking = _booking(world, "Marina Hall", BookingStatus.approved)
    _service(world).change(booking.id, world.coordinator, venue_id=world.venues["Sky Room"].id)

    world.db.rollback()

    row = world.db.get(VenueBooking, booking.id)
    assert row.status is BookingStatus.approved
    assert row.venue_id == world.venues["Marina Hall"].id
    assert world.db.query(EventStatusHistory).count() == 0


def test_a_time_cannot_be_changed_here(world):
    booking = _booking(world, "Marina Hall", BookingStatus.approved)

    with pytest.raises(TypeError):
        _service(world).change(booking.id, world.coordinator, start_time=START)


def test_a_change_that_changes_nothing_is_refused(world):
    booking = _booking(world, "Marina Hall", BookingStatus.approved)

    with pytest.raises(InvalidInput):
        _service(world).change(booking.id, world.coordinator, venue_id=world.venues["Marina Hall"].id)
    with pytest.raises(InvalidInput):
        _service(world).change(booking.id, world.coordinator)

    assert world.db.get(VenueBooking, booking.id).status is BookingStatus.approved


def test_a_booking_that_is_history_cannot_be_changed_or_cancelled(world):
    for status in (BookingStatus.rejected, BookingStatus.cancelled):
        booking = _booking(world, "Marina Hall", status)
        with pytest.raises(Conflict):
            _service(world).change(booking.id, world.coordinator, venue_id=world.venues["Sky Room"].id)
        with pytest.raises(Conflict):
            _service(world).cancel(booking.id, world.coordinator)
        world.db.delete(booking)
        world.db.commit()


def test_another_coordinators_booking_is_not_found(world):
    booking = _booking(world, "Marina Hall", BookingStatus.approved)

    for call in (
        lambda s: s.change(booking.id, world.other, venue_id=world.venues["Sky Room"].id),
        lambda s: s.cancel(booking.id, world.other),
        lambda s: s.live_bookings(world.event.id, world.other),
        lambda s: s.cancel_all(world.event.id, world.other, [booking.id]),
    ):
        with pytest.raises(NotFound):
            call(_service(world))


@pytest.mark.parametrize("status", [s for s in EventStatus if s not in VENUE_CHANGE_EVENT_STATUSES])
def test_nothing_is_changed_outside_the_window(world, status):
    booking = _booking(world, "Marina Hall", BookingStatus.approved)
    world.event.status = status
    world.db.commit()

    for call in (
        lambda s: s.change(booking.id, world.coordinator, venue_id=world.venues["Sky Room"].id),
        lambda s: s.cancel(booking.id, world.coordinator),
        lambda s: s.live_bookings(world.event.id, world.coordinator),
        lambda s: s.cancel_all(world.event.id, world.coordinator, [booking.id]),
    ):
        with pytest.raises(Conflict):
            call(_service(world))
    assert world.db.get(VenueBooking, booking.id).status is BookingStatus.approved


def test_cancelling_cancels_that_booking_and_leaves_the_rest(world):
    a = _booking(world, "Marina Hall", BookingStatus.approved)
    b = _booking(world, "Garden Hall", BookingStatus.pending)

    cancelled = _service(world).cancel(a.id, world.coordinator)

    assert cancelled.status is BookingStatus.cancelled
    assert world.db.get(VenueBooking, b.id).status is BookingStatus.pending


def test_the_live_bookings_are_the_ones_cancel_all_would_cancel(world):
    live = [_booking(world, "Marina Hall", BookingStatus.approved), _booking(world, "Garden Hall")]
    _booking(world, "Sky Room", BookingStatus.rejected)

    listed = _service(world).live_bookings(world.event.id, world.coordinator)

    assert [b.id for b in listed] == [b.id for b in live]


def test_cancel_all_needs_exactly_the_list_that_was_shown(world):
    a = _booking(world, "Marina Hall", BookingStatus.approved)
    b = _booking(world, "Garden Hall")

    with pytest.raises(Conflict):
        _service(world).cancel_all(world.event.id, world.coordinator, [a.id])  # b missing
    with pytest.raises(Conflict):
        _service(world).cancel_all(world.event.id, world.coordinator, [a.id, b.id, 99999])
    with pytest.raises(InvalidInput):
        _service(world).cancel_all(world.event.id, world.coordinator, [])

    assert world.db.get(VenueBooking, a.id).status is BookingStatus.approved
    assert world.db.get(VenueBooking, b.id).status is BookingStatus.pending


def test_cancel_all_cancels_each_listed_booking(world):
    a = _booking(world, "Marina Hall", BookingStatus.approved)
    b = _booking(world, "Garden Hall")

    cancelled = _service(world).cancel_all(world.event.id, world.coordinator, [b.id, a.id])

    assert [x.id for x in cancelled] == [a.id, b.id]
    assert {x.status for x in cancelled} == {BookingStatus.cancelled}


# --- who is told, and where it is recorded: both handed in ------------------


def test_the_service_tells_exactly_the_people_it_is_handed(world):
    """Polymorphism: swap the rule for who is told and the service follows it,
    without a line of the service changing."""
    booking = _booking(world, "Marina Hall", BookingStatus.approved)
    vera, victor = world.staff
    recipients = StaffOfOneVenue({world.venues["Marina Hall"].id: [vera]})

    _service(world, recipients=recipients).cancel(booking.id, world.coordinator)

    assert len(_notices(world, vera)) == 1
    assert _notices(world, victor) == []


def test_a_venue_change_tells_the_staff_of_both_venues_once_each(world):
    """The old venue's staff learn it was withdrawn; the new venue's staff
    learn of the request. Someone who staffs both is told once."""
    booking = _booking(world, "Marina Hall", BookingStatus.approved)
    vera, victor = world.staff
    recipients = StaffOfOneVenue(
        {world.venues["Marina Hall"].id: [vera], world.venues["Sky Room"].id: [vera, victor]}
    )

    _service(world, recipients=recipients).change(
        booking.id, world.coordinator, venue_id=world.venues["Sky Room"].id
    )

    assert len(_notices(world, vera)) == 1
    assert len(_notices(world, victor)) == 1


def test_the_notice_is_the_right_kind_for_each_action(world):
    a = _booking(world, "Marina Hall", BookingStatus.approved)
    b = _booking(world, "Garden Hall", BookingStatus.pending)
    service = _service(world)

    service.change(a.id, world.coordinator, room_layout_preference="Classroom")
    service.cancel(b.id, world.coordinator)

    kinds = sorted(n.type for n in _notices(world, world.staff[0]))
    assert kinds == sorted([NotificationType.venue_booking_changed, NotificationType.venue_booking_cancelled])


def test_the_service_records_through_the_log_it_is_handed(world):
    booking = _booking(world, "Marina Hall", BookingStatus.approved)
    log = FakeActivityLog()

    _service(world, activity=log).cancel(booking.id, world.coordinator, reason="Roof leak")

    [(event_id, actor_id, note)] = log.entries
    assert (event_id, actor_id) == (world.event.id, world.coordinator.id)
    assert "Marina Hall" in note and "Roof leak" in note
    assert world.db.query(EventStatusHistory).count() == 0  # nothing went to the real log


def test_a_refused_action_records_and_tells_no_one(world):
    booking = _booking(world, "Marina Hall", BookingStatus.rejected)
    log = FakeActivityLog()

    with pytest.raises(DomainError):
        _service(world, activity=log).cancel(booking.id, world.coordinator)

    assert log.entries == []
    assert all(_notices(world, user) == [] for user in world.staff)
