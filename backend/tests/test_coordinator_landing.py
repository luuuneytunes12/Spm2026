"""Tests for the Event Coordinator landing page's numbers.

The page counts two things from existing endpoints, so the AC tests prove
those endpoints hand back exactly the caller's own rows:

    AC3  a Coordinator's assigned Events and unread Notifications are what
         the page counts
    AC4  a Coordinator with none gets empty lists, so no number is shown

and, as the access-denied checks the Definition of Done asks for, that
other people's events and notifications never leak into those counts.
"""

from app.core.roles import Role
from app.models.events import Event
from app.models.notifications import Notification
from tests.event_review_test_helpers import COMPLETE, user


def _submitted(client, headers, name):
    event_id = client.post("/events", json={**COMPLETE, "name": name}, headers=headers).json()["id"]
    assert client.post(f"/events/{event_id}/submit", headers=headers).status_code == 200
    return event_id


def _assign(db_session, event_id, coordinator):
    event = db_session.get(Event, event_id)
    event.coordinator_id = coordinator.id
    db_session.commit()


def _setup(client, db_session):
    organiser, org_h = user(client, db_session, Role.ORGANISER, "org@example.com", "Olivia Organiser")
    sam, sam_h = user(client, db_session, Role.COORDINATOR, "sam@example.com", "Sam Tan")
    priya, priya_h = user(client, db_session, Role.COORDINATOR, "priya@example.com", "Priya Nair")
    return org_h, sam, sam_h, priya, priya_h


def test_ac3_the_assigned_count_is_the_events_assigned_to_this_coordinator(client, db_session):
    org_h, sam, sam_h, priya, _ = _setup(client, db_session)
    _assign(db_session, _submitted(client, org_h, "One"), sam)
    _assign(db_session, _submitted(client, org_h, "Two"), sam)
    _assign(db_session, _submitted(client, org_h, "Three"), priya)

    assert len(client.get("/events/assigned", headers=sam_h).json()) == 2


def test_ac3_unread_notifications_are_counted_and_read_ones_are_not(client, db_session):
    _, sam, sam_h, _, _ = _setup(client, db_session)
    for i in range(3):
        db_session.add(Notification(user_id=sam.id, type="event_assigned", message=f"n{i}"))
    db_session.commit()

    notifications = client.get("/notifications", headers=sam_h).json()
    assert len([n for n in notifications if not n["is_read"]]) == 3

    client.post("/notifications/read", json={"ids": [notifications[0]["id"]]}, headers=sam_h)
    after = client.get("/notifications", headers=sam_h).json()
    assert len([n for n in after if not n["is_read"]]) == 2


def test_ac4_a_coordinator_with_nothing_assigned_and_nothing_unread_gets_empty_lists(client, db_session):
    _, _, sam_h, _, _ = _setup(client, db_session)

    assert client.get("/events/assigned", headers=sam_h).json() == []
    assert client.get("/notifications", headers=sam_h).json() == []


def test_an_unassigned_submitted_request_is_not_counted(client, db_session):
    org_h, _, sam_h, _, _ = _setup(client, db_session)
    _submitted(client, org_h, "Waiting in the Lead's queue")

    assert client.get("/events/assigned", headers=sam_h).json() == []


def test_another_coordinators_events_are_never_counted(client, db_session):
    org_h, sam, sam_h, priya, priya_h = _setup(client, db_session)
    _assign(db_session, _submitted(client, org_h, "Priya's event"), priya)

    assert client.get("/events/assigned", headers=sam_h).json() == []
    assert len(client.get("/events/assigned", headers=priya_h).json()) == 1


def test_another_users_notifications_are_never_counted(client, db_session):
    _, _, sam_h, priya, _ = _setup(client, db_session)
    db_session.add(Notification(user_id=priya.id, type="event_assigned", message="not yours"))
    db_session.commit()

    assert client.get("/notifications", headers=sam_h).json() == []


def test_the_counts_need_a_signed_in_user(client):
    assert client.get("/events/assigned").status_code == 401
    assert client.get("/notifications").status_code == 401
