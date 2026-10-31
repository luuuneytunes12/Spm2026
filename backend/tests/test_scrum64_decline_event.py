"""Tests for SCRUM-64 "Declare Coordinator Per-Event Unavailability".

    As an Event Coordinator, I want to decline a specific event I'm assigned
    to, so that it gets reassigned to someone else without affecting my
    availability for other events.

The rule lives in `services.assignment.reassign_event`, so that is what these
call. No route reaches it yet, which the last test records.
"""

import pytest

from app.core.roles import Role
from app.models.enums import EventStatus, NotificationType
from app.models.events import Event, EventStatusHistory
from app.models.notifications import Notification
from app.services.assignment import assign_coordinator, available_coordinators, reassign_event
from tests.event_review_test_helpers import COMPLETE, review_setup, user


@pytest.fixture()
def w(client, db_session):
    organiser, org_h, outgoing, outgoing_h, event_id = review_setup(client, db_session)
    other, _ = user(client, db_session, Role.COORDINATOR, "other@example.com", "Priya Nair")
    return {
        "organiser": organiser,
        "org_h": org_h,
        "outgoing": outgoing,
        "outgoing_h": outgoing_h,
        "other": other,
        "event": db_session.get(Event, event_id),
    }


def _decline(db_session, w):
    taken_by = reassign_event(db_session, w["event"], w["outgoing"])
    db_session.commit()
    return taken_by


def _types(db_session, user_id):
    return {n.type for n in db_session.query(Notification).filter_by(user_id=user_id)}


def _last_log_line(db_session, w):
    return (
        db_session.query(EventStatusHistory)
        .filter_by(event_id=w["event"].id)
        .order_by(EventStatusHistory.id.desc())
        .first()
    )


def test_ac1_declining_reassigns_the_event_to_another_coordinator(db_session, w):
    assert _decline(db_session, w).id == w["other"].id
    assert w["event"].coordinator_id == w["other"].id


def test_ac1_the_status_and_details_are_left_as_they_were(db_session, w):
    name = w["event"].name
    _decline(db_session, w)
    assert w["event"].status == EventStatus.under_review
    assert w["event"].name == name


def test_ac1_the_new_coordinator_the_outgoing_one_and_the_organiser_are_told(db_session, w):
    _decline(db_session, w)
    assert NotificationType.event_assigned in _types(db_session, w["other"].id)
    assert NotificationType.event_reassigned_away in _types(db_session, w["outgoing"].id)
    assert NotificationType.event_coordinator_assigned in _types(db_session, w["organiser"].id)


def test_ac1_with_nobody_else_available_the_event_is_left_unassigned(db_session, w):
    w["other"].is_available = False
    db_session.commit()

    assert _decline(db_session, w) is None

    assert w["event"].coordinator_id is None
    assert NotificationType.event_reassigned_away not in _types(db_session, w["outgoing"].id)


def test_ac2_the_coordinator_stays_in_the_pool_for_other_events(client, db_session, w):
    _decline(db_session, w)
    assert w["outgoing"].id in {c.id for c in available_coordinators(db_session)}

    # Now holding nothing, they are the lightest load, so they get the next one.
    next_id = client.post("/events", json=COMPLETE, headers=w["org_h"]).json()["id"]
    assert client.post(f"/events/{next_id}/submit", headers=w["org_h"]).status_code == 200
    picked = assign_coordinator(db_session, db_session.get(Event, next_id), actor_id=w["organiser"].id)
    assert picked.id == w["outgoing"].id


def test_ac3_their_profile_status_is_unaffected(client, db_session, w):
    _decline(db_session, w)
    db_session.expire_all()
    assert w["outgoing"].is_available is True
    assert client.get("/auth/me", headers=w["outgoing_h"]).json()["user"]["is_available"] is True


def test_ac4_the_decline_is_logged_with_their_name_and_the_time(db_session, w):
    _decline(db_session, w)
    line = _last_log_line(db_session, w)
    assert line.changed_by == w["outgoing"].id
    assert line.created_at is not None
    assert w["outgoing"].name in line.note and "declined" in line.note
    assert w["other"].name in line.note


def test_ac4_the_decline_is_logged_even_when_nobody_takes_over(db_session, w):
    w["other"].is_available = False
    db_session.commit()
    _decline(db_session, w)
    line = _last_log_line(db_session, w)
    assert line.changed_by == w["outgoing"].id
    assert "declined" in line.note and "unassigned" in line.note


@pytest.mark.xfail(
    strict=False,
    raises=AssertionError,
    reason="SCRUM-64 is not reachable: no route calls reassign_event, so a Coordinator cannot decline.",
)
def test_ac1_a_coordinator_can_decline_through_the_api(client, w):
    res = client.post(f"/events/{w['event'].id}/decline", headers=w["outgoing_h"])
    assert res.status_code == 200
