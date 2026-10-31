"""Tests for SCRUM-68 "View Event Catalogue", against GET /registrations/events.

    As an Attendee, I want to browse a catalogue of events open for
    registration, so that I can discover events and choose which ones to look
    into further.

The "no events" wording and the link to an event's details are the page's:
frontend/src/pages/registrations/EventCatalogue.test.tsx.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.roles import Role
from app.models.enums import BookingStatus, EventStatus
from app.models.events import Event
from app.models.venues import VenueBooking
from tests.event_review_test_helpers import user
from tests.test_venue_booking_request import _venue

# Words that would only appear in a key carrying internal planning information.
INTERNAL = ("coordinator", "note", "booking", "reservation", "equipment", "technical", "staff", "comment")


@pytest.fixture()
def w(client, db_session):
    organiser, _ = user(client, db_session, Role.ORGANISER, "org@example.com", "Org")
    coordinator, _ = user(client, db_session, Role.COORDINATOR, "coord@example.com", "Coord")
    _, attendee = user(client, db_session, Role.ATTENDEE, "att@example.com", "Att")
    return {"organiser": organiser, "coordinator": coordinator, "attendee": attendee}


def _event(db_session, w, *, status=EventStatus.safety_check_passed, enabled=True, days=30):
    start = datetime.now(timezone.utc) + timedelta(days=days)
    event = Event(
        organiser_id=w["organiser"].id,
        coordinator_id=w["coordinator"].id,
        name="Partner Summit",
        event_type="conference",
        proposed_start=start,
        proposed_end=start + timedelta(hours=8),
        registration_enabled=enabled,
        status=status,
    )
    db_session.add(event)
    db_session.commit()
    return event


def _catalogue(client, w):
    res = client.get("/registrations/events", headers=w["attendee"])
    assert res.status_code == 200
    return res.json()


def test_ac1_an_open_event_is_listed_with_its_name_date_and_time(client, db_session, w):
    event = _event(db_session, w)

    [row] = _catalogue(client, w)

    assert row["id"] == event.id and row["name"] == "Partner Summit"
    assert row["proposed_start"] and row["proposed_end"]
    assert row["registration_open"] is True


@pytest.mark.xfail(
    strict=False,
    raises=KeyError,
    reason="SCRUM-68 AC1 not implemented: RegistrableEvent has no category.",
)
def test_ac1_each_event_shows_its_category(client, db_session, w):
    _event(db_session, w)
    [row] = _catalogue(client, w)
    assert row["category"] == "conference"


@pytest.mark.xfail(
    strict=False,
    raises=KeyError,
    reason="SCRUM-68 AC1 not implemented: RegistrableEvent has no venue name.",
)
def test_ac1_each_event_shows_its_venue_name(client, db_session, w):
    event = _event(db_session, w)
    venue = _venue(db_session)
    db_session.add(
        VenueBooking(
            event_id=event.id,
            venue_id=venue.id,
            requested_by=w["coordinator"].id,
            start_time=event.proposed_start,
            end_time=event.proposed_end,
            status=BookingStatus.approved,
        )
    )
    db_session.commit()
    [row] = _catalogue(client, w)
    assert row["venue_name"] == "Marina Hall"


@pytest.mark.parametrize("status", [s for s in EventStatus if s != EventStatus.safety_check_passed])
def test_ac2_an_event_that_is_not_confirmed_is_not_listed(client, db_session, w, status):
    _event(db_session, w, status=status)
    assert _catalogue(client, w) == []


def test_ac2_an_event_not_taking_registrations_is_not_listed(client, db_session, w):
    _event(db_session, w, enabled=False)
    assert _catalogue(client, w) == []


@pytest.mark.xfail(
    strict=False,
    raises=AssertionError,
    reason="SCRUM-68 AC2 not met: an event closed for registration stays listed, marked closed.",
)
def test_ac2_an_event_closed_for_registration_is_not_listed(client, db_session, w):
    _event(db_session, w, days=-1)
    assert _catalogue(client, w) == []


def test_ac4_no_internal_planning_information_is_returned(client, db_session, w):
    _event(db_session, w)
    [row] = _catalogue(client, w)
    leaked = [key for key in row if any(word in key for word in INTERNAL)]
    assert leaked == []


def test_ac5_with_nothing_open_the_catalogue_is_empty(client, w):
    assert _catalogue(client, w) == []


def test_ac6_changed_confirmed_details_are_shown_as_they_are_now(client, db_session, w):
    event = _event(db_session, w)
    moved = event.proposed_start + timedelta(days=1)
    event.name = "Partner Summit 2027"
    event.proposed_start = moved
    db_session.commit()

    [row] = _catalogue(client, w)

    assert row["name"] == "Partner Summit 2027"
    assert row["proposed_start"].startswith(f"{moved:%Y-%m-%dT%H:%M}")


@pytest.mark.parametrize("role", [r for r in Role if r != Role.ATTENDEE])
def test_only_an_attendee_opens_the_catalogue(client, db_session, role):
    _, headers = user(client, db_session, role, "other@example.com", "Other")
    assert client.get("/registrations/events", headers=headers).status_code == 403


def test_someone_not_logged_in_cannot_open_the_catalogue(client):
    assert client.get("/registrations/events").status_code == 401
