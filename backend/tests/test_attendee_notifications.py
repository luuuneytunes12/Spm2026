"""Tests for the Attendee's notifications about events they registered for.

    AC1  A confirmed Event's date, time or Venue changes (including a
         replacement Venue): each registered Attendee gets ONE notification
         giving the new date, time or Venue, even when several change in the
         same save.
    AC2  An Attendee who withdrew no longer gets notifications for it.
    AC3  A registration saved as Registered or Withdrawn: that Attendee gets a
         notification confirming the Event and the new status.
    AC4  No registration, or withdrawn: no notification about a change.

Test names carry the acceptance criterion they prove. A date or time changes
through an Organiser's change request the Coordinator approves; a Venue
through a replacement booking Venue Staff approve (SCRUM-95).
"""

import pytest

from app.core.roles import Role
from app.models.enums import EventStatus, NotificationType, RegistrationStatus
from app.models.events import Event
from app.models.notifications import Notification
from app.models.registrations import Registration
from app.services.attendee_notices import (
    AttendeeNotice,
    EventChangedNotice,
    RegistrationStatusNotice,
)
from app.services.submission_notice import EventNotice
from tests.event_review_test_helpers import review_setup, user
from tests.test_venue_replacement import _approve_replacement, _confirmed_flagged_world

CHANGED = NotificationType.event_details_changed.value
SAVED = NotificationType.registration_status_changed.value

NEW_START = "2026-11-03T10:00:00Z"
NEW_END = "2026-11-03T18:00:00Z"


def _confirmed_event(client, db_session):
    """A confirmed Event open for registration, with its Organiser and
    Coordinator. Starts 2 Nov 2026, 09:00-17:00 UTC."""
    _, org_h, coordinator, coord_h, event_id = review_setup(client, db_session)
    event = db_session.get(Event, event_id)
    event.status = EventStatus.safety_check_passed
    event.registration_enabled = True
    db_session.commit()
    return {"event_id": event_id, "org_h": org_h, "coord_h": coord_h, "coordinator": coordinator}


def _attendee(client, db_session, key):
    return user(client, db_session, Role.ATTENDEE, f"{key}@example.com", key.title())


def _register(client, w, headers):
    return client.post(f"/registrations/events/{w['event_id']}", headers=headers)


def _withdraw(client, w, headers):
    return client.post(f"/registrations/events/{w['event_id']}/withdraw", headers=headers)


def _change(client, w, **proposed):
    """The Organiser asks for `proposed`; the Coordinator approves it."""
    requested = client.post(
        f"/events/{w['event_id']}/change-requests",
        json={"description": "Moving the event", "proposed_changes": proposed},
        headers=w["org_h"],
    )
    assert requested.status_code == 201, requested.text
    approved = client.post(
        f"/events/change-requests/{requested.json()['id']}/approve", json={}, headers=w["coord_h"]
    )
    assert approved.status_code == 200, approved.text
    return requested.json()["id"]


def _notes(db_session, user_id, type):
    db_session.expire_all()
    return [
        n.message
        for n in db_session.query(Notification).filter_by(user_id=user_id, type=type).order_by(Notification.id)
    ]


def _inbox(client, headers, type):
    return [n["message"] for n in client.get("/notifications", headers=headers).json() if n["type"] == type]


# --- AC1: one notice per save, giving the new date / time ------------------


def test_ac1_a_new_date_and_time_in_one_save_gives_one_notice_with_both(client, db_session):
    w = _confirmed_event(client, db_session)
    amy, amy_h = _attendee(client, db_session, "amy")
    _register(client, w, amy_h)

    _change(client, w, proposed_start=NEW_START, proposed_end=NEW_END)

    assert _inbox(client, amy_h, CHANGED) == [
        "'Regional Partner Conference', which you are registered for, has changed: "
        "it now starts 3 Nov 2026, 10:00 UTC; it now ends 3 Nov 2026, 18:00 UTC."
    ]


def test_ac1_a_new_time_only_names_just_what_changed(client, db_session):
    w = _confirmed_event(client, db_session)
    amy, amy_h = _attendee(client, db_session, "amy")
    _register(client, w, amy_h)

    _change(client, w, proposed_end="2026-11-02T19:00:00Z")

    [message] = _inbox(client, amy_h, CHANGED)
    assert message.endswith("has changed: it now ends 2 Nov 2026, 19:00 UTC.")
    assert "starts" not in message


def test_ac1_every_registered_attendee_gets_their_own_notice(client, db_session):
    w = _confirmed_event(client, db_session)
    amy, amy_h = _attendee(client, db_session, "amy")
    ben, ben_h = _attendee(client, db_session, "ben")
    _register(client, w, amy_h)
    _register(client, w, ben_h)

    _change(client, w, proposed_start=NEW_START, proposed_end=NEW_END)

    assert len(_notes(db_session, amy.id, CHANGED)) == 1
    assert len(_notes(db_session, ben.id, CHANGED)) == 1


def test_ac1_a_replacement_venue_gives_one_notice_with_the_new_venue(client, db_session):
    w, original, other = _confirmed_flagged_world(client, db_session)
    amy, _ = _attendee(client, db_session, "amy")
    db_session.add(Registration(event_id=original.event_id, attendee_id=amy.id))
    db_session.commit()

    _approve_replacement(client, w, original, other)

    assert _notes(db_session, amy.id, CHANGED) == [
        "'Gala', which you are registered for, has changed: "
        "the venue is now Other Hall (replacing Marina Hall)."
    ]


def test_ac1_a_requested_or_rejected_replacement_sends_nothing(client, db_session):
    w, original, other = _confirmed_flagged_world(client, db_session)
    amy, _ = _attendee(client, db_session, "amy")
    db_session.add(Registration(event_id=original.event_id, attendee_id=amy.id))
    db_session.commit()

    new = client.post(
        f"/venue-bookings/{original.id}/replacement", json={"venue_id": other.id}, headers=w["sam_h"]
    )
    assert new.status_code == 201
    assert _notes(db_session, amy.id, CHANGED) == []
    client.post(f"/venue-bookings/{new.json()['id']}/reject", json={"reason": "No"}, headers=w["staff_h"])
    assert _notes(db_session, amy.id, CHANGED) == []


def test_ac1_a_change_that_is_not_a_date_time_or_venue_sends_nothing(client, db_session):
    w = _confirmed_event(client, db_session)
    amy, amy_h = _attendee(client, db_session, "amy")
    _register(client, w, amy_h)

    _change(client, w, name="Renamed Conference")

    assert _inbox(client, amy_h, CHANGED) == []


def test_ac1_the_same_date_and_time_again_is_not_a_change(client, db_session):
    w = _confirmed_event(client, db_session)
    amy, amy_h = _attendee(client, db_session, "amy")
    _register(client, w, amy_h)

    _change(client, w, proposed_start="2026-11-02T09:00:00Z", proposed_end="2026-11-02T17:00:00Z")

    assert _inbox(client, amy_h, CHANGED) == []


def test_ac1_a_rejected_change_request_sends_nothing(client, db_session):
    w = _confirmed_event(client, db_session)
    amy, amy_h = _attendee(client, db_session, "amy")
    _register(client, w, amy_h)
    requested = client.post(
        f"/events/{w['event_id']}/change-requests",
        json={"description": "Moving", "proposed_changes": {"proposed_start": NEW_START, "proposed_end": NEW_END}},
        headers=w["org_h"],
    ).json()

    client.post(f"/events/change-requests/{requested['id']}/reject", json={}, headers=w["coord_h"])

    assert _inbox(client, amy_h, CHANGED) == []


def test_ac1_an_event_that_is_not_confirmed_sends_nothing(client, db_session):
    """Before confirmation nobody can be registered; even a stray row is not told."""
    _, org_h, _, coord_h, event_id = review_setup(client, db_session)  # under review
    amy, _ = _attendee(client, db_session, "amy")
    db_session.add(Registration(event_id=event_id, attendee_id=amy.id))
    db_session.commit()

    _change(client, {"event_id": event_id, "org_h": org_h, "coord_h": coord_h},
            proposed_start=NEW_START, proposed_end=NEW_END)

    assert _notes(db_session, amy.id, CHANGED) == []


def test_ac1_the_change_is_still_applied(client, db_session):
    """Frozen: approving a change request still applies it."""
    w = _confirmed_event(client, db_session)
    _change(client, w, proposed_start=NEW_START, proposed_end=NEW_END)
    db_session.expire_all()
    assert db_session.get(Event, w["event_id"]).proposed_start.hour == 10


# --- AC1: the Coordinator editing the confirmed Event directly -------------


def _edit(client, w, **body):
    """The assigned Coordinator edits the Event's details in one save."""
    edited = client.patch(f"/events/assigned/{w['event_id']}/planning", json=body, headers=w["coord_h"])
    assert edited.status_code == 200, edited.text
    return edited.json()


def test_ac1_a_coordinator_edit_of_date_and_time_gives_one_notice_with_both(client, db_session):
    w = _confirmed_event(client, db_session)
    amy, amy_h = _attendee(client, db_session, "amy")
    _register(client, w, amy_h)

    _edit(client, w, proposed_start=NEW_START, proposed_end=NEW_END)

    assert _inbox(client, amy_h, CHANGED) == [
        "'Regional Partner Conference', which you are registered for, has changed: "
        "it now starts 3 Nov 2026, 10:00 UTC; it now ends 3 Nov 2026, 18:00 UTC."
    ]


def test_ac1_a_coordinator_edit_of_the_end_only_names_just_that(client, db_session):
    w = _confirmed_event(client, db_session)
    amy, amy_h = _attendee(client, db_session, "amy")
    _register(client, w, amy_h)

    _edit(client, w, proposed_end="2026-11-02T19:00:00Z")

    [message] = _inbox(client, amy_h, CHANGED)
    assert message.endswith("has changed: it now ends 2 Nov 2026, 19:00 UTC.")


def test_ac1_a_coordinator_edit_not_touching_date_or_time_sends_nothing(client, db_session):
    w = _confirmed_event(client, db_session)
    amy, amy_h = _attendee(client, db_session, "amy")
    _register(client, w, amy_h)

    _edit(client, w, description="A longer description.")

    assert _inbox(client, amy_h, CHANGED) == []


def test_ac1_a_coordinator_edit_to_the_same_date_and_time_sends_nothing(client, db_session):
    w = _confirmed_event(client, db_session)
    amy, amy_h = _attendee(client, db_session, "amy")
    _register(client, w, amy_h)

    _edit(client, w, proposed_start="2026-11-02T09:00:00Z", proposed_end="2026-11-02T17:00:00Z")

    assert _inbox(client, amy_h, CHANGED) == []


def test_ac1_a_coordinator_edit_of_an_unconfirmed_event_sends_nothing(client, db_session):
    w = _confirmed_event(client, db_session)
    amy, amy_h = _attendee(client, db_session, "amy")
    _register(client, w, amy_h)
    db_session.get(Event, w["event_id"]).status = EventStatus.planning_event
    db_session.commit()

    _edit(client, w, proposed_start=NEW_START, proposed_end=NEW_END)

    assert _notes(db_session, amy.id, CHANGED) == []


def test_ac1_a_refused_coordinator_edit_sends_nothing(client, db_session):
    w = _confirmed_event(client, db_session)
    amy, amy_h = _attendee(client, db_session, "amy")
    _register(client, w, amy_h)

    refused = client.patch(
        f"/events/assigned/{w['event_id']}/planning",
        json={"proposed_start": NEW_END, "proposed_end": NEW_START},  # ends before it starts
        headers=w["coord_h"],
    )

    assert refused.status_code == 422
    assert _inbox(client, amy_h, CHANGED) == []


def test_ac1_a_coordinator_edit_still_reopens_the_event(client, db_session):
    """Frozen: a new date still sends the confirmed Event back to planning."""
    w = _confirmed_event(client, db_session)
    assert _edit(client, w, proposed_start=NEW_START, proposed_end=NEW_END)["status"] == "planning_event"


def test_ac2_a_withdrawn_attendee_is_not_told_about_a_coordinator_edit(client, db_session):
    w = _confirmed_event(client, db_session)
    amy, amy_h = _attendee(client, db_session, "amy")
    ben, ben_h = _attendee(client, db_session, "ben")
    _register(client, w, amy_h)
    _register(client, w, ben_h)
    _withdraw(client, w, ben_h)

    _edit(client, w, proposed_start=NEW_START, proposed_end=NEW_END)

    assert len(_notes(db_session, amy.id, CHANGED)) == 1
    assert _notes(db_session, ben.id, CHANGED) == []


# --- AC2 / AC4: withdrawn or unregistered -> nothing -----------------------


def test_ac2_a_withdrawn_attendee_is_not_told_about_the_change(client, db_session):
    w = _confirmed_event(client, db_session)
    amy, amy_h = _attendee(client, db_session, "amy")
    ben, ben_h = _attendee(client, db_session, "ben")
    _register(client, w, amy_h)
    _register(client, w, ben_h)
    _withdraw(client, w, amy_h)

    _change(client, w, proposed_start=NEW_START, proposed_end=NEW_END)

    assert _inbox(client, amy_h, CHANGED) == []
    assert len(_inbox(client, ben_h, CHANGED)) == 1


def test_ac2_a_withdrawn_attendee_is_not_told_about_a_replacement_venue(client, db_session):
    w, original, other = _confirmed_flagged_world(client, db_session)
    amy, _ = _attendee(client, db_session, "amy")
    db_session.add(
        Registration(event_id=original.event_id, attendee_id=amy.id, status=RegistrationStatus.withdrawn)
    )
    db_session.commit()

    _approve_replacement(client, w, original, other)

    assert _notes(db_session, amy.id, CHANGED) == []


def test_ac2_registering_again_after_withdrawing_brings_the_notices_back(client, db_session):
    w = _confirmed_event(client, db_session)
    amy, amy_h = _attendee(client, db_session, "amy")
    _register(client, w, amy_h)
    _withdraw(client, w, amy_h)
    _register(client, w, amy_h)

    _change(client, w, proposed_start=NEW_START, proposed_end=NEW_END)

    assert len(_inbox(client, amy_h, CHANGED)) == 1


def test_ac4_an_attendee_with_no_registration_gets_nothing(client, db_session):
    w = _confirmed_event(client, db_session)
    _, amy_h = _attendee(client, db_session, "amy")
    _, ben_h = _attendee(client, db_session, "ben")
    _register(client, w, ben_h)

    _change(client, w, proposed_start=NEW_START, proposed_end=NEW_END)

    assert client.get("/notifications", headers=amy_h).json() == []


def test_ac4_nobody_but_registered_attendees_gets_the_change_notice(client, db_session):
    w = _confirmed_event(client, db_session)
    amy, amy_h = _attendee(client, db_session, "amy")
    _register(client, w, amy_h)

    _change(client, w, proposed_start=NEW_START, proposed_end=NEW_END)

    db_session.expire_all()
    assert {n.user_id for n in db_session.query(Notification).filter_by(type=CHANGED)} == {amy.id}


# --- AC3: Registered / Withdrawn is confirmed ------------------------------


def test_ac3_registering_confirms_the_event_and_registered(client, db_session):
    w = _confirmed_event(client, db_session)
    _, amy_h = _attendee(client, db_session, "amy")

    assert _register(client, w, amy_h).status_code == 200

    notices = [n for n in client.get("/notifications", headers=amy_h).json() if n["type"] == SAVED]
    assert [n["message"] for n in notices] == [
        "Your registration for 'Regional Partner Conference' on 2 Nov 2026, 09:00 UTC is now Registered."
    ]
    assert notices[0]["event_id"] == w["event_id"]


def test_ac3_withdrawing_confirms_the_event_and_withdrawn(client, db_session):
    w = _confirmed_event(client, db_session)
    amy, amy_h = _attendee(client, db_session, "amy")
    _register(client, w, amy_h)

    assert _withdraw(client, w, amy_h).status_code == 200

    assert _notes(db_session, amy.id, SAVED)[-1] == (
        "Your registration for 'Regional Partner Conference' on 2 Nov 2026, 09:00 UTC is now Withdrawn."
    )


def test_ac3_each_save_is_confirmed_once(client, db_session):
    w = _confirmed_event(client, db_session)
    amy, amy_h = _attendee(client, db_session, "amy")
    _register(client, w, amy_h)
    _withdraw(client, w, amy_h)
    _register(client, w, amy_h)

    assert [m.rsplit(" ", 1)[-1] for m in _notes(db_session, amy.id, SAVED)] == [
        "Registered.",
        "Withdrawn.",
        "Registered.",
    ]


def test_ac3_a_refused_register_or_withdraw_sends_nothing_new(client, db_session):
    w = _confirmed_event(client, db_session)
    _, amy_h = _attendee(client, db_session, "amy")

    assert _withdraw(client, w, amy_h).status_code == 404  # nothing to withdraw
    assert _inbox(client, amy_h, SAVED) == []
    _register(client, w, amy_h)
    assert _register(client, w, amy_h).status_code == 409  # already registered
    assert len(_inbox(client, amy_h, SAVED)) == 1


def test_ac3_registration_closed_sends_nothing(client, db_session):
    w = _confirmed_event(client, db_session)
    db_session.get(Event, w["event_id"]).registration_enabled = False
    db_session.commit()
    _, amy_h = _attendee(client, db_session, "amy")

    assert _register(client, w, amy_h).status_code == 404
    assert _inbox(client, amy_h, SAVED) == []


def test_ac3_only_that_attendee_is_told(client, db_session):
    w = _confirmed_event(client, db_session)
    amy, amy_h = _attendee(client, db_session, "amy")
    _, ben_h = _attendee(client, db_session, "ben")

    _register(client, w, amy_h)

    assert _inbox(client, ben_h, SAVED) == []
    assert _inbox(client, w["org_h"], SAVED) == []
    assert _inbox(client, w["coord_h"], SAVED) == []
    db_session.expire_all()
    assert {n.user_id for n in db_session.query(Notification).filter_by(type=SAVED)} == {amy.id}


@pytest.mark.parametrize("role", [Role.ORGANISER, Role.COORDINATOR, Role.SAFETY_OFFICER])
def test_ac3_other_roles_cannot_register_and_nothing_is_sent(client, db_session, role):
    w = _confirmed_event(client, db_session)
    _, other_h = user(client, db_session, role, "other@example.com", "Other")

    assert _register(client, w, other_h).status_code == 403

    db_session.expire_all()
    assert db_session.query(Notification).filter_by(type=SAVED).count() == 0


# --- OOP -------------------------------------------------------------------


def test_attendee_notices_extend_the_base_notice_with_their_own_types():
    assert issubclass(AttendeeNotice, EventNotice)
    assert issubclass(EventChangedNotice, AttendeeNotice)
    assert issubclass(RegistrationStatusNotice, EventNotice)
    assert EventChangedNotice.type == "event_details_changed"
    assert RegistrationStatusNotice.type == "registration_status_changed"


def test_an_empty_change_is_never_sent(db_session):
    EventChangedNotice([]).send(db_session, None)  # returns before touching the event
    assert db_session.query(Notification).count() == 0
