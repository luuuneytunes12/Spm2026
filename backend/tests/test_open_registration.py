"""Tests for SCRUM-66, Open Registration for a Confirmed Event.

    As an Event Coordinator, I want to open registration for a confirmed event
    and set its open and close dates, so that attendees can register before
    the event.

Each test name states the acceptance criterion it covers. Who moves an event
to "confirmed" is not this story's job, so the tests set that status directly.
The tests of the story's own Jira ACs (SCRUM-66 AC1-AC6) are in
test_schedule_registration.py; this file keeps the registration-window rules
and the Attendee's side.
"""

from datetime import datetime, timedelta, timezone

from app.core.roles import Role
from app.models.enums import BookingStatus, EventStatus
from app.models.events import Event
from app.models.venues import Venue, VenueBooking
from tests.event_review_test_helpers import user


def _iso(delta_days: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=delta_days)).isoformat()


def _setup(client, db_session, *, status=EventStatus.safety_check_passed):
    organiser, organiser_h = user(client, db_session, Role.ORGANISER, "org@example.com", "Organiser")
    coordinator, coordinator_h = user(
        client, db_session, Role.COORDINATOR, "coord@example.com", "Coordinator"
    )
    _, attendee_h = user(client, db_session, Role.ATTENDEE, "att@example.com", "Attendee")
    start = datetime.now(timezone.utc) + timedelta(days=30)
    event = Event(
        organiser_id=organiser.id,
        coordinator_id=coordinator.id,
        name="Partner Summit",
        proposed_start=start,
        proposed_end=start + timedelta(hours=8),
        registration_enabled=False,
        status=status,
    )
    db_session.add(event)
    db_session.flush()
    # A confirmed event still has its venue: enabling registration checks that.
    venue = Venue(name="Marina Hall", location="Block A", capacity=300)
    db_session.add(venue)
    db_session.flush()
    db_session.add(
        VenueBooking(
            event_id=event.id,
            venue_id=venue.id,
            requested_by=coordinator.id,
            start_time=event.proposed_start,
            end_time=event.proposed_end,
            status=BookingStatus.approved,
        )
    )
    db_session.commit()
    return event, organiser_h, coordinator_h, attendee_h


def _put(client, headers, event_id, *, enabled=True, opens=None, closes=None):
    return client.put(
        f"/events/assigned/{event_id}/registration",
        json={
            "registration_enabled": enabled,
            "registration_opens_at": opens,
            "registration_closes_at": closes,
        },
        headers=headers,
    )


def _flagged(res) -> set[str]:
    return {item["loc"][-1] for item in res.json()["detail"]}


# --- AC1: dates are saved and shown on the event record ---------------------


def test_ac1_enabling_on_a_confirmed_event_saves_and_shows_the_dates(client, db_session):
    event, organiser_h, coordinator_h, _ = _setup(client, db_session)

    res = _put(client, coordinator_h, event.id, opens=_iso(1), closes=_iso(10))

    assert res.status_code == 200
    body = res.json()
    assert body["registration_enabled"] is True
    assert body["registration_opens_at"] is not None
    assert body["registration_closes_at"] is not None

    # Shown on the event record -- for the Coordinator and for the Organiser.
    assigned = client.get(f"/events/assigned/{event.id}", headers=coordinator_h).json()
    assert assigned["registration_enabled"] is True
    assert assigned["registration_opens_at"] == body["registration_opens_at"]
    assert assigned["registration_closes_at"] == body["registration_closes_at"]
    own = client.get(f"/events/{event.id}", headers=organiser_h).json()
    assert own["registration_opens_at"] == body["registration_opens_at"]
    assert own["registration_closes_at"] == body["registration_closes_at"]


def test_ac1_the_saved_dates_are_stored(client, db_session):
    event, _, coordinator_h, _ = _setup(client, db_session)
    _put(client, coordinator_h, event.id, opens=_iso(1), closes=_iso(10))

    db_session.expire_all()
    saved = db_session.get(Event, event.id)
    assert saved.registration_enabled is True
    assert saved.registration_opens_at is not None
    assert saved.registration_closes_at is not None


def test_ac1_both_dates_are_required_when_enabling(client, db_session):
    event, _, coordinator_h, _ = _setup(client, db_session)

    res = _put(client, coordinator_h, event.id, opens=_iso(1), closes=None)

    assert res.status_code == 422
    assert _flagged(res) == {"registration_closes_at"}
    db_session.expire_all()
    assert db_session.get(Event, event.id).registration_enabled is False


# --- AC2: close before open is blocked and the date fields are flagged ------


def test_ac2_close_before_open_is_blocked_and_both_date_fields_flagged(client, db_session):
    event, _, coordinator_h, _ = _setup(client, db_session)

    res = _put(client, coordinator_h, event.id, opens=_iso(10), closes=_iso(2))

    assert res.status_code == 422
    assert _flagged(res) == {"registration_opens_at", "registration_closes_at"}
    # The two sentences the Coordinator reads: what is wrong, and what to do.
    assert [item["msg"] for item in res.json()["detail"]] == [
        "Registration cannot close before it opens.",
        "Ensure the registration close date is later than the open date.",
    ]
    db_session.expire_all()
    saved = db_session.get(Event, event.id)
    assert saved.registration_enabled is False
    assert saved.registration_opens_at is None
    assert saved.registration_closes_at is None


def test_ac2_closing_at_the_same_moment_it_opens_is_allowed(client, db_session):
    event, _, coordinator_h, _ = _setup(client, db_session)
    moment = _iso(3)

    assert _put(client, coordinator_h, event.id, opens=moment, closes=moment).status_code == 200


# --- AC3: an event that is not confirmed cannot have registration enabled ---


def test_ac3_enabling_on_an_unconfirmed_event_is_blocked(client, db_session):
    for status in (
        EventStatus.submitted_awaiting_coordinator,
        EventStatus.under_review,
        EventStatus.event_approved,
        EventStatus.event_rejected,
    ):
        event, _, coordinator_h, _ = _setup_fresh(client, db_session, status)

        res = _put(client, coordinator_h, event.id, opens=_iso(1), closes=_iso(10))

        assert res.status_code == 409, status
        db_session.expire_all()
        assert db_session.get(Event, event.id).registration_enabled is False, status


def _setup_fresh(client, db_session, status):
    """A new event (and a fresh Coordinator) for each status in a loop."""
    n = db_session.query(Event).count() + 1
    organiser, _ = user(client, db_session, Role.ORGANISER, f"org{n}@example.com", "Organiser")
    coordinator, coordinator_h = user(
        client, db_session, Role.COORDINATOR, f"coord{n}@example.com", "Coordinator"
    )
    start = datetime.now(timezone.utc) + timedelta(days=30)
    event = Event(
        organiser_id=organiser.id,
        coordinator_id=coordinator.id,
        name=f"Event {n}",
        proposed_start=start,
        proposed_end=start + timedelta(hours=8),
        registration_enabled=False,
        status=status,
    )
    db_session.add(event)
    db_session.commit()
    return event, None, coordinator_h, None


# --- AC4: enabled and today between the dates -> Attendee is offered register


def test_ac4_attendee_is_offered_registration_inside_the_window(client, db_session):
    event, _, coordinator_h, attendee_h = _setup(client, db_session)
    _put(client, coordinator_h, event.id, opens=_iso(-1), closes=_iso(5))

    rows = client.get("/registrations/events", headers=attendee_h).json()
    row = next(r for r in rows if r["id"] == event.id)

    assert row["registration_open"] is True
    assert row["registration_opens_at"] is not None
    assert row["registration_closes_at"] is not None
    assert client.post(f"/registrations/events/{event.id}", headers=attendee_h).status_code == 200


def test_ac4_no_offer_before_the_window_opens(client, db_session):
    event, _, coordinator_h, attendee_h = _setup(client, db_session)
    _put(client, coordinator_h, event.id, opens=_iso(2), closes=_iso(9))

    rows = client.get("/registrations/events", headers=attendee_h).json()
    row = next(r for r in rows if r["id"] == event.id)

    assert row["registration_open"] is False
    res = client.post(f"/registrations/events/{event.id}", headers=attendee_h)
    assert res.status_code == 409
    assert "not opened" in res.json()["detail"]


def test_ac4_no_offer_after_the_window_closes(client, db_session):
    event, _, coordinator_h, attendee_h = _setup(client, db_session)
    # Dates in the past cannot be saved "open" to anyone, but they can be saved.
    _put(client, coordinator_h, event.id, opens=_iso(-9), closes=_iso(-2))

    rows = client.get("/registrations/events", headers=attendee_h).json()
    row = next(r for r in rows if r["id"] == event.id)

    assert row["registration_open"] is False
    res = client.post(f"/registrations/events/{event.id}", headers=attendee_h)
    assert res.status_code == 409
    assert "closed" in res.json()["detail"]


def test_ac4_an_event_registration_was_never_enabled_for_is_not_offered(client, db_session):
    event, _, _, attendee_h = _setup(client, db_session)

    rows = client.get("/registrations/events", headers=attendee_h).json()

    assert all(r["id"] != event.id for r in rows)
    assert client.post(f"/registrations/events/{event.id}", headers=attendee_h).status_code == 404


# --- Guards -----------------------------------------------------------------


def test_registration_can_always_be_switched_off(client, db_session):
    event, _, coordinator_h, attendee_h = _setup(client, db_session)
    _put(client, coordinator_h, event.id, opens=_iso(-1), closes=_iso(5))

    res = _put(client, coordinator_h, event.id, enabled=False)

    assert res.status_code == 200
    assert res.json()["registration_enabled"] is False
    rows = client.get("/registrations/events", headers=attendee_h).json()
    assert all(r["id"] != event.id for r in rows)


def test_only_the_assigned_coordinator_can_set_registration(client, db_session):
    event, _, _, _ = _setup(client, db_session)
    _, other_coordinator_h = user(
        client, db_session, Role.COORDINATOR, "other@example.com", "Other Coordinator"
    )

    res = _put(client, other_coordinator_h, event.id, opens=_iso(1), closes=_iso(10))

    assert res.status_code == 404
    db_session.expire_all()
    assert db_session.get(Event, event.id).registration_enabled is False


def test_only_coordinators_can_set_registration(client, db_session):
    event, organiser_h, _, attendee_h = _setup(client, db_session)

    for headers in (organiser_h, attendee_h):
        res = _put(client, headers, event.id, opens=_iso(1), closes=_iso(10))
        assert res.status_code == 403
    assert _put(client, {}, event.id, opens=_iso(1), closes=_iso(10)).status_code == 401
