"""Tests for SCRUM-60 "Set Up Notification Infrastructure".

    As a developer, I want an in-app notification service set up, so that the
    system can deliver role-appropriate notifications to users when triggered
    events occur.

The broker behind GET /notifications/stream is tested directly: TestClient
cannot hold an endless server-sent stream open.
"""

import asyncio
import threading

from app.core.roles import Role
from app.models.enums import NotificationType
from app.models.notifications import Notification
from app.models.user import User
from app.routers.notifications import stream_my_notifications
from app.services.notifications import NotificationBroker, broker, notify
from tests.event_review_test_helpers import COMPLETE, user

PAYLOAD = {
    "id": 1,
    "event_id": None,
    "type": "event_assigned",
    "message": "Hello",
    "is_read": False,
    "created_at": "2026-11-02T09:00:00Z",
}


def _run(coroutine):
    return asyncio.run(asyncio.wait_for(coroutine, timeout=5))


# --- AC1: a trigger creates a record for the correct recipient ----------------


def test_ac1_a_notification_is_recorded_for_its_recipient_only(client, db_session):
    recipient, _ = user(client, db_session, Role.COORDINATOR, "one@example.com", "One")
    other, _ = user(client, db_session, Role.COORDINATOR, "two@example.com", "Two")

    notify(db_session, user_id=recipient.id, type=NotificationType.event_assigned, message="Yours")
    db_session.commit()

    [row] = db_session.query(Notification).all()
    assert row.user_id == recipient.id and row.message == "Yours" and row.is_read is False
    assert db_session.query(Notification).filter_by(user_id=other.id).count() == 0


def test_ac1_nothing_is_recorded_when_the_work_that_caused_it_rolls_back(client, db_session):
    recipient, _ = user(client, db_session, Role.COORDINATOR, "one@example.com", "One")

    notify(db_session, user_id=recipient.id, type=NotificationType.event_assigned, message="Undone")
    db_session.rollback()

    assert db_session.query(Notification).count() == 0


# --- AC2: the panel shows the message and timestamp ---------------------------


def test_ac2_the_recipient_sees_the_message_and_timestamp(client, db_session):
    recipient, headers = user(client, db_session, Role.COORDINATOR, "one@example.com", "One")
    notify(db_session, user_id=recipient.id, type=NotificationType.event_assigned, message="Yours")
    db_session.commit()

    [row] = client.get("/notifications", headers=headers).json()

    assert row["message"] == "Yours"
    assert row["created_at"]
    assert row["is_read"] is False


# --- AC3: a role that is not the target receives nothing ----------------------


def test_ac3_a_trigger_for_one_role_reaches_no_other_role(client, db_session):
    _, organiser = user(client, db_session, Role.ORGANISER, "org@example.com", "Org")
    _, lead = user(client, db_session, Role.COORDINATOR_LEAD, "lead@example.com", "Lead")
    others = [
        user(client, db_session, role, f"{role.value}@example.com", role.value)[1]
        for role in (Role.COORDINATOR, Role.VENUE_STAFF, Role.TECH_SUPPORT, Role.ATTENDEE, Role.SAFETY_OFFICER)
    ]

    event_id = client.post("/events", json=COMPLETE, headers=organiser).json()["id"]
    assert client.post(f"/events/{event_id}/submit", headers=organiser).status_code == 200

    assert len(client.get("/notifications", headers=lead).json()) == 1
    for headers in others:
        assert client.get("/notifications", headers=headers).json() == []


# --- The live broker ----------------------------------------------------------


def test_ac1_a_published_notification_reaches_the_users_open_stream():
    async def scenario():
        hub = NotificationBroker()
        async with hub.subscribe(7) as queue:
            hub.publish(7, PAYLOAD)
            return await queue.get()

    assert _run(scenario()) == PAYLOAD


def test_ac1_each_open_tab_gets_its_own_copy():
    async def scenario():
        hub = NotificationBroker()
        async with hub.subscribe(7) as first, hub.subscribe(7) as second:
            hub.publish(7, PAYLOAD)
            return await first.get(), await second.get()

    assert _run(scenario()) == (PAYLOAD, PAYLOAD)


def test_ac3_another_users_stream_receives_nothing():
    async def scenario():
        hub = NotificationBroker()
        async with hub.subscribe(8) as queue:
            hub.publish(7, PAYLOAD)
            await asyncio.sleep(0)
            return queue.empty()

    assert _run(scenario()) is True


def test_publishing_to_a_user_with_no_open_stream_does_nothing():
    NotificationBroker().publish(7, PAYLOAD)


def test_closing_a_stream_unsubscribes_it():
    async def scenario():
        hub = NotificationBroker()
        async with hub.subscribe(7), hub.subscribe(7):
            pass
        return hub._subscribers

    assert _run(scenario()) == {}


def test_closing_one_tab_leaves_the_other_subscribed():
    async def scenario():
        hub = NotificationBroker()
        async with hub.subscribe(7) as kept:
            async with hub.subscribe(7):
                pass
            hub.publish(7, PAYLOAD)
            return await kept.get()

    assert _run(scenario()) == PAYLOAD


def test_publishing_from_a_worker_thread_reaches_the_event_loop():
    # Most routes are sync and run in FastAPI's threadpool; the queues are the loop's.
    async def scenario():
        hub = NotificationBroker()
        async with hub.subscribe(7) as queue:
            threading.Thread(target=hub.publish, args=(7, PAYLOAD)).start()
            return await queue.get()

    assert _run(scenario()) == PAYLOAD


def test_the_stream_route_yields_the_callers_notifications_and_then_unsubscribes():
    async def scenario():
        stream = stream_my_notifications(user=User(id=4242, role=Role.ATTENDEE.value))
        pending = asyncio.ensure_future(anext(stream))
        while 4242 not in broker._subscribers:
            await asyncio.sleep(0)
        broker.publish(4242, PAYLOAD)
        received = await pending
        await stream.aclose()
        return received, 4242 in broker._subscribers

    received, still_subscribed = _run(scenario())
    assert received.message == "Hello"
    assert still_subscribed is False
