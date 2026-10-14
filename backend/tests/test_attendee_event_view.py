"""As an Attendee, I want to view the attendee-facing details of a confirmed
Event, so that I have the information I need to attend.

Test names carry the acceptance criterion they prove.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.roles import Role
from app.models.enums import BookingStatus, EventStatus
from app.models.events import Event
from app.models.venues import VenueBooking
from tests.event_review_test_helpers import user
from tests.test_safety_checks import _setup

PUBLIC_FIELDS = {
    "id", "name", "description", "event_type", "proposed_start", "proposed_end",
    "venues", "accessibility_needs", "programme", "registration_open",
    "registration_opens_at", "registration_closes_at", "my_status",
}


def _confirmed(client, db_session):
    """A Safety-Check-passed event with registration open, plus an Attendee."""
    s = _setup(client, db_session)
    assert client.post(f"/safety-checks/{s['event_id']}/approve", headers=s["officer_h"]).status_code == 200
    event = db_session.get(Event, s["event_id"])
    now = datetime.now(timezone.utc)
    event.description = "A day of partner briefings."
    event.programme = "09:00 Welcome\n10:00 Keynote"
    event.special_arrangements = "INTERNAL: VIP parking for sponsors"
    event.registration_enabled = True
    event.registration_opens_at = now - timedelta(days=1)
    event.registration_closes_at = now + timedelta(days=5)
    db_session.commit()
    _, s["att_h"] = user(client, db_session, Role.ATTENDEE, "att@example.com", "Ada Attendee")
    return s


def _view(client, s):
    return client.get(f"/registrations/events/{s['event_id']}", headers=s["att_h"])


def test_ac1_attendee_sees_the_public_details_of_a_confirmed_open_event(client, db_session):
    s = _confirmed(client, db_session)

    res = _view(client, s)

    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "Regional Partner Conference"
    assert body["description"] == "A day of partner briefings."
    assert body["event_type"] == "conference"
    assert body["proposed_start"].startswith("2026-11-02T09:00")
    assert body["proposed_end"].startswith("2026-11-02T17:00")
    assert {(v["name"], v["location"]) for v in body["venues"]} == {
        ("Marina Hall", "10 Bayfront Ave"),
        ("Garden Pavilion", "10 Bayfront Ave"),
    }
    assert body["accessibility_needs"] == "Step-free access"
    assert body["programme"] == "09:00 Welcome\n10:00 Keynote"
    assert body["registration_opens_at"] and body["registration_closes_at"]
    assert body["registration_open"] is True


def test_ac2_no_internal_planning_information_is_returned(client, db_session):
    s = _confirmed(client, db_session)

    res = _view(client, s)

    assert set(res.json()) == PUBLIC_FIELDS
    assert set(res.json()["venues"][0]) == {"name", "location"}
    for internal in (
        "INTERNAL", "Back of hall", "Projector", "Vera Staff", "Tess Tech", "Sam Safety",
        "Coordinator", "approved", "Safety Check", "fire exits", "No open flames",
    ):
        assert internal not in res.text


@pytest.mark.parametrize(
    "path",
    ["/events/assigned/{id}", "/safety-checks/{id}", "/events/{id}", "/equipment-requirements/events/{id}"],
)
def test_ac3_internal_planning_pages_are_refused_to_an_attendee(client, db_session, path):
    s = _confirmed(client, db_session)

    res = client.get(path.format(id=s["event_id"]), headers=s["att_h"])

    assert res.status_code in (403, 404)
    assert "Back of hall" not in res.text and "INTERNAL" not in res.text


@pytest.mark.parametrize(
    "status", [EventStatus.planning_event, EventStatus.awaiting_safety_check, EventStatus.event_approved]
)
def test_ac3_an_unconfirmed_event_is_not_found_for_an_attendee(client, db_session, status):
    s = _confirmed(client, db_session)
    db_session.get(Event, s["event_id"]).status = status
    db_session.commit()

    assert _view(client, s).status_code == 404


def test_ac3_an_event_without_registration_is_not_found_for_an_attendee(client, db_session):
    s = _confirmed(client, db_session)
    db_session.get(Event, s["event_id"]).registration_enabled = False
    db_session.commit()

    assert _view(client, s).status_code == 404


@pytest.mark.parametrize("who", ["org_h", "coord_h", "officer_h"])
def test_ac3_only_an_attendee_uses_the_attendee_view(client, db_session, who):
    s = _confirmed(client, db_session)

    assert client.get(f"/registrations/events/{s['event_id']}", headers=s[who]).status_code == 403


def test_ac4_a_replaced_venue_shows_the_current_one_not_the_superseded(client, db_session):
    s = _confirmed(client, db_session)
    db_session.get(VenueBooking, s["booking_id"]).status = BookingStatus.cancelled
    db_session.commit()

    venues = [v["name"] for v in _view(client, s).json()["venues"]]

    assert venues == ["Garden Pavilion"]


def test_ac4_changed_details_are_shown_as_they_are_now(client, db_session):
    s = _confirmed(client, db_session)
    db_session.get(Event, s["event_id"]).programme = "09:30 Welcome"
    db_session.commit()

    assert _view(client, s).json()["programme"] == "09:30 Welcome"
