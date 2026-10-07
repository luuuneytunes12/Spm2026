"""Tests for the Event Organiser landing page's numbers.

The landing page counts three things from existing endpoints, so the AC
tests here prove those endpoints hand back exactly the caller's own rows:

    AC3  an Organiser's drafts, submitted requests and unread Notifications
         are what the page counts
    AC4  an Organiser with none gets empty lists, so no number is shown

and, as the access-denied checks the Definition of Done asks for, that
nobody else's events or notifications leak into those counts.
"""

from app.core.roles import Role
from app.models.notifications import Notification
from app.models.user import User
from tests.event_review_test_helpers import COMPLETE, user


def _organiser(client, db_session, email="org@example.com", name="Olivia Organiser"):
    return user(client, db_session, Role.ORGANISER, email, name)[1]


def _draft(client, headers, name):
    res = client.post("/events", json={**COMPLETE, "name": name}, headers=headers)
    assert res.status_code == 201
    return res.json()["id"]


def _submitted(client, headers, name):
    event_id = _draft(client, headers, name)
    assert client.post(f"/events/{event_id}/submit", headers=headers).status_code == 200
    return event_id


def test_ac3_counts_come_from_the_organisers_own_drafts_and_submitted_requests(client, db_session):
    headers = _organiser(client, db_session)
    _draft(client, headers, "Draft one")
    _draft(client, headers, "Draft two")
    _submitted(client, headers, "Submitted one")

    drafts = client.get("/events?status=draft", headers=headers).json()
    everything = client.get("/events", headers=headers).json()

    assert len(drafts) == 2
    assert len([e for e in everything if e["status"] != "draft"]) == 1


def test_ac3_unread_notifications_are_counted_and_read_ones_are_not(client, db_session):
    headers = _organiser(client, db_session)
    owner = db_session.query(User).filter(User.email == "org@example.com").one()
    for i in range(3):
        db_session.add(Notification(user_id=owner.id, type="event_approved", message=f"n{i}"))
    db_session.commit()

    unread = [n for n in client.get("/notifications", headers=headers).json() if not n["is_read"]]
    assert len(unread) == 3

    first = client.get("/notifications", headers=headers).json()[0]["id"]
    client.post("/notifications/read", json={"ids": [first]}, headers=headers)
    unread = [n for n in client.get("/notifications", headers=headers).json() if not n["is_read"]]
    assert len(unread) == 2


def test_ac4_an_organiser_with_no_events_or_notifications_gets_empty_lists(client, db_session):
    headers = _organiser(client, db_session)

    assert client.get("/events?status=draft", headers=headers).json() == []
    assert client.get("/events", headers=headers).json() == []
    assert client.get("/notifications", headers=headers).json() == []


def test_another_organisers_events_are_never_counted(client, db_session):
    mine = _organiser(client, db_session)
    theirs = _organiser(client, db_session, "other@example.com", "Other Organiser")
    _draft(client, theirs, "Their draft")
    _submitted(client, theirs, "Their submitted")

    assert client.get("/events?status=draft", headers=mine).json() == []
    assert client.get("/events", headers=mine).json() == []


def test_another_users_notifications_are_never_counted(client, db_session):
    mine = _organiser(client, db_session)
    _organiser(client, db_session, "other@example.com", "Other Organiser")
    other = db_session.query(User).filter(User.email == "other@example.com").one()
    db_session.add(Notification(user_id=other.id, type="event_approved", message="not yours"))
    db_session.commit()

    assert client.get("/notifications", headers=mine).json() == []


def test_the_counts_need_a_signed_in_user(client):
    assert client.get("/events").status_code == 401
    assert client.get("/events?status=draft").status_code == 401
    assert client.get("/notifications").status_code == 401
