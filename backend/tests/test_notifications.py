"""Tests for the signed-in user's notifications: listing, marking as read
(single, multi-select, select-all, everything) and the live push from
approve/reject.

Assignment and reassignment notifications are covered alongside the story
that creates them, in test_coordinator_availability.py.
"""

from unittest.mock import patch

from app.core.roles import Role
from app.models.notifications import Notification
from app.models.user import User
from app.services.notifications import broker

COMPLETE = {
    "name": "Regional Partner Conference",
    "purpose": "Annual partner briefing",
    "event_type": "conference",
    "proposed_start": "2026-11-02T09:00:00Z",
    "proposed_end": "2026-11-02T17:00:00Z",
    "expected_attendance": 120,
    "venue_requirements": "Main hall, stage, podium",
    "accessibility_needs": "Step-free access, hearing loop",
    "equipment_requirements": "2 projectors, 4 radio mics",
}


def _user(client, db_session, email, role=Role.ATTENDEE, name="Test User"):
    """Register a user with `role` and return (user, headers)."""
    password = "password123"
    res = client.post(
        "/auth/register", json={"name": name, "email": email, "password": password}
    )
    assert res.status_code == 201

    user = db_session.query(User).filter(User.email == email).one()
    user.role = role.value
    db_session.commit()

    token = client.post("/auth/login", json={"email": email, "password": password}).json()[
        "access_token"
    ]
    return user, {"Authorization": f"Bearer {token}"}


def _add(db_session, user, *messages) -> list[int]:
    """Give `user` one unread notification per message; return their ids."""
    rows = [Notification(user_id=user.id, type="event_assigned", message=m) for m in messages]
    db_session.add_all(rows)
    db_session.commit()
    return [row.id for row in rows]


def _unread_ids(client, headers) -> set[int]:
    return {n["id"] for n in client.get("/notifications", headers=headers).json() if not n["is_read"]}


# --------------------------------------------------------------------------
# Listing
# --------------------------------------------------------------------------


def test_lists_only_the_callers_notifications_newest_first(client, db_session):
    me, my_headers = _user(client, db_session, "me@connectsphere.test")
    other, _ = _user(client, db_session, "other@connectsphere.test")
    first, second = _add(db_session, me, "first", "second")
    _add(db_session, other, "not mine")

    body = client.get("/notifications", headers=my_headers).json()

    assert [n["id"] for n in body] == [second, first]
    assert all(n["is_read"] is False for n in body)


def test_anonymous_cannot_list_notifications(client):
    assert client.get("/notifications").status_code == 401


# --------------------------------------------------------------------------
# Marking as read
# --------------------------------------------------------------------------


def test_mark_selected_as_read_marks_only_those(client, db_session):
    """Multi-select: exactly the chosen ids flip, the rest stay unread."""
    me, headers = _user(client, db_session, "me@connectsphere.test")
    a, b, c = _add(db_session, me, "a", "b", "c")

    res = client.post("/notifications/read", json={"ids": [a, c]}, headers=headers)

    assert res.status_code == 200
    assert res.json() == {"updated": 2}
    assert _unread_ids(client, headers) == {b}


def test_marking_an_already_read_notification_is_not_counted(client, db_session):
    me, headers = _user(client, db_session, "me@connectsphere.test")
    (a,) = _add(db_session, me, "a")
    client.post("/notifications/read", json={"ids": [a]}, headers=headers)

    res = client.post("/notifications/read", json={"ids": [a]}, headers=headers)

    assert res.json() == {"updated": 0}


def test_cannot_mark_someone_elses_notifications_read(client, db_session):
    """Other users' ids are ignored silently -- same answer as an id that
    does not exist -- and their notifications stay unread."""
    _me, my_headers = _user(client, db_session, "me@connectsphere.test")
    other, other_headers = _user(client, db_session, "other@connectsphere.test")
    (theirs,) = _add(db_session, other, "not yours")

    res = client.post("/notifications/read", json={"ids": [theirs, 999_999]}, headers=my_headers)

    assert res.status_code == 200
    assert res.json() == {"updated": 0}
    assert _unread_ids(client, other_headers) == {theirs}


def test_mark_read_rejects_an_empty_or_oversized_selection(client, db_session):
    _me, headers = _user(client, db_session, "me@connectsphere.test")

    assert client.post("/notifications/read", json={"ids": []}, headers=headers).status_code == 422
    too_many = {"ids": list(range(1, 502))}
    assert client.post("/notifications/read", json=too_many, headers=headers).status_code == 422


def test_mark_all_read_affects_only_the_caller(client, db_session):
    me, my_headers = _user(client, db_session, "me@connectsphere.test")
    other, other_headers = _user(client, db_session, "other@connectsphere.test")
    _add(db_session, me, "a", "b")
    (theirs,) = _add(db_session, other, "not yours")

    res = client.post("/notifications/read-all", headers=my_headers)

    assert res.json() == {"updated": 2}
    assert _unread_ids(client, my_headers) == set()
    assert _unread_ids(client, other_headers) == {theirs}


def test_anonymous_cannot_mark_notifications_read(client):
    assert client.post("/notifications/read", json={"ids": [1]}).status_code == 401
    assert client.post("/notifications/read-all").status_code == 401


# --------------------------------------------------------------------------
# Live push from the review decision
# --------------------------------------------------------------------------


def _submitted_and_assigned(client, db_session):
    """An event submitted by an Organiser and auto-assigned to a Coordinator."""
    organiser, organiser_headers = _user(
        client, db_session, "org@connectsphere.test", Role.ORGANISER, "Priya Menon"
    )
    _coordinator, coordinator_headers = _user(
        client, db_session, "sam@connectsphere.test", Role.COORDINATOR, "Sam Tan"
    )
    event_id = client.post("/events", json=COMPLETE, headers=organiser_headers).json()["id"]
    assert client.post(f"/events/{event_id}/submit", headers=organiser_headers).status_code == 200
    return organiser, event_id, coordinator_headers


def test_approval_is_pushed_live_to_the_organiser(client, db_session):
    organiser, event_id, coordinator_headers = _submitted_and_assigned(client, db_session)

    with patch.object(broker, "publish") as publish:
        client.post(f"/events/{event_id}/approve", headers=coordinator_headers)

    publish.assert_called_once()
    user_id, payload = publish.call_args.args
    assert user_id == organiser.id
    assert payload["type"] == "event_approved"
    assert payload["event_id"] == event_id


def test_rejection_is_pushed_live_to_the_organiser(client, db_session):
    organiser, event_id, coordinator_headers = _submitted_and_assigned(client, db_session)

    with patch.object(broker, "publish") as publish:
        client.post(
            f"/events/{event_id}/reject",
            json={"reason": "Venue unavailable"},
            headers=coordinator_headers,
        )

    publish.assert_called_once()
    user_id, payload = publish.call_args.args
    assert user_id == organiser.id
    assert payload["type"] == "event_rejected"
    assert "Venue unavailable" in payload["message"]
