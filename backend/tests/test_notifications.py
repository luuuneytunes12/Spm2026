"""Tests for the notifications endpoints backing the Coordinator's inbox.

The primary write path (an auto-assignment creating a notification) is
covered in test_events.py, alongside the rest of that story's acceptance
criteria. These tests cover the read/write-back side: a user listing their
own notifications and marking one read.
"""

from app.core.roles import Role
from app.models.notifications import Notification
from app.models.user import User


def _user(client, db_session, email="user@example.com", role=Role.COORDINATOR):
    res = client.post(
        "/auth/register", json={"name": "Some User", "email": email, "password": "password123"}
    )
    assert res.status_code == 201
    user = db_session.query(User).filter(User.email == email).one()
    user.role = role.value
    db_session.commit()
    token = client.post("/auth/login", json={"email": email, "password": "password123"}).json()[
        "access_token"
    ]
    return user, {"Authorization": f"Bearer {token}"}


def test_lists_own_notifications_newest_first(client, db_session):
    user, headers = _user(client, db_session)
    db_session.add_all(
        [
            Notification(user_id=user.id, type="event_assigned", message="First"),
            Notification(user_id=user.id, type="event_assigned", message="Second"),
        ]
    )
    db_session.commit()

    res = client.get("/notifications", headers=headers)

    assert res.status_code == 200
    messages = [n["message"] for n in res.json()]
    assert messages == ["Second", "First"]
    assert all(n["is_read"] is False for n in res.json())


def test_does_not_see_someone_elses_notifications(client, db_session):
    other, _ = _user(client, db_session, email="other@example.com")
    db_session.add(Notification(user_id=other.id, type="event_assigned", message="Not yours"))
    db_session.commit()
    _, headers = _user(client, db_session, email="me@example.com")

    res = client.get("/notifications", headers=headers)

    assert res.status_code == 200
    assert res.json() == []


def test_anonymous_cannot_list_notifications(client):
    assert client.get("/notifications").status_code == 401


def test_mark_notification_read(client, db_session):
    user, headers = _user(client, db_session)
    notification = Notification(user_id=user.id, type="event_assigned", message="Read me")
    db_session.add(notification)
    db_session.commit()
    db_session.refresh(notification)

    res = client.patch(f"/notifications/{notification.id}/read", headers=headers)

    assert res.status_code == 200
    assert res.json()["is_read"] is True
    assert db_session.get(Notification, notification.id).is_read is True


def test_cannot_mark_someone_elses_notification_read(client, db_session):
    other, _ = _user(client, db_session, email="other@example.com")
    notification = Notification(user_id=other.id, type="event_assigned", message="Not yours")
    db_session.add(notification)
    db_session.commit()
    db_session.refresh(notification)
    _, headers = _user(client, db_session, email="me@example.com")

    res = client.patch(f"/notifications/{notification.id}/read", headers=headers)

    assert res.status_code == 404
    assert db_session.get(Notification, notification.id).is_read is False
