"""Concurrent requests against the coordinator stories, on real PostgreSQL.

Why this file exists: SQLite serialises every write, so it can never show a
race. On Postgres two requests genuinely overlap -- each reads the row
BEFORE the other commits -- so a check-then-act sequence ("is it still a
draft? ... now assign") can be satisfied by both. These tests fire the same
action from several threads at once (released together by a barrier) and
assert the outcome a user would expect from a single click:

    * a double-clicked Submit assigns ONE coordinator, once;
    * a double-clicked Decline hands the event over ONCE;
    * a repeated availability toggle records ONE change;
    * events submitted together never go to a coordinator who is out of the pool.

Every test uses one API client per thread and every request its own session
and connection, exactly as production would.
"""

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from app.core.roles import Role
from app.models.events import Event, EventStatusHistory
from app.models.notifications import Notification
from app.models.user import User
from tests.integration.conftest import COMPLETE_EVENT

THREADS = 6


def race(make_client, n: int, call: Callable):
    """Run `call(client)` in `n` threads released at the same instant.
    Returns the list of results in no particular order."""
    barrier = threading.Barrier(n)
    clients = [make_client() for _ in range(n)]

    def worker(client):
        barrier.wait()
        return call(client)

    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(worker, clients))


def draft(client, headers, **overrides) -> int:
    res = client.post("/events", json={**COMPLETE_EVENT, **overrides}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()["id"]


# --------------------------------------------------------------------------
# Double-clicked Submit
# --------------------------------------------------------------------------


def test_a_submit_fired_many_times_at_once_assigns_the_event_exactly_once(
    make_client, client, make_user, db
):
    _o, org_h = make_user(Role.ORGANISER, "org@connectsphere.test", "Priya Menon")
    make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")
    make_user(Role.COORDINATOR, "priya@connectsphere.test", "Priya Nair")
    event_id = draft(client, org_h)

    results = race(make_client, THREADS, lambda c: c.post(f"/events/{event_id}/submit", headers=org_h))

    codes = sorted(r.status_code for r in results)
    assert codes == [200] + [409] * (THREADS - 1), codes  # one wins, the rest are refused
    db.expire_all()
    assert db.query(EventStatusHistory).filter(
        EventStatusHistory.event_id == event_id, EventStatusHistory.note.like("Assigned to%")
    ).count() == 1
    assert db.query(EventStatusHistory).filter(
        EventStatusHistory.event_id == event_id, EventStatusHistory.note == "Submitted by organiser."
    ).count() == 1
    assert db.query(Notification).filter(Notification.type == "event_assigned").count() == 1
    assert db.query(Notification).filter(Notification.type == "event_coordinator_assigned").count() == 1


# --------------------------------------------------------------------------
# Double-clicked Decline (SCRUM-64)
# --------------------------------------------------------------------------


def test_a_decline_fired_many_times_at_once_hands_the_event_over_exactly_once(
    make_client, client, make_user, db
):
    _o, org_h = make_user(Role.ORGANISER, "org@connectsphere.test", "Priya Menon")
    sam, sam_h = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")
    make_user(Role.COORDINATOR, "priya@connectsphere.test", "Priya Nair")
    make_user(Role.COORDINATOR, "lee@connectsphere.test", "Lee Wong")
    event_id = draft(client, org_h)
    client.post(f"/events/{event_id}/submit", headers=org_h)
    assert db.get(Event, event_id).coordinator_id == sam.id

    results = race(
        make_client, THREADS, lambda c: c.post(f"/events/assigned/{event_id}/release", headers=sam_h)
    )

    codes = sorted(r.status_code for r in results)
    assert codes == [200] + [404] * (THREADS - 1), codes  # after the first, it is no longer Sam's
    db.expire_all()
    new_owner = db.get(Event, event_id).coordinator_id
    assert new_owner not in (None, sam.id)
    declined = db.query(EventStatusHistory).filter(
        EventStatusHistory.event_id == event_id, EventStatusHistory.note.like("%declined this event%")
    ).count()
    assert declined == 1  # SCRUM-64 AC4: one decline, one record
    assert db.query(Notification).filter(
        Notification.user_id == sam.id, Notification.type == "event_reassigned_away"
    ).count() == 1
    assert db.query(Notification).filter(
        Notification.type == "event_coordinator_assigned"
    ).count() == 2  # the first assignment plus exactly one reassignment


# --------------------------------------------------------------------------
# Repeated availability toggle (SCRUM-24)
# --------------------------------------------------------------------------


def test_the_same_availability_change_sent_many_times_at_once_is_recorded_once(
    make_client, make_user, db
):
    sam, sam_h = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")
    client = make_client()

    results = race(
        make_client,
        THREADS,
        lambda c: c.patch("/coordinators/me/availability", json={"is_available": False}, headers=sam_h),
    )

    assert all(r.status_code == 200 for r in results)
    history = client.get("/coordinators/me/availability-history", headers=sam_h).json()
    assert len(history) == 1  # SCRUM-24 AC4: one change, one entry
    assert history[0]["is_available"] is False
    db.expire_all()
    assert db.get(User, sam.id).is_available is False


def test_opposing_availability_changes_at_once_leave_the_history_consistent_with_the_flag(
    make_client, make_user, db
):
    sam, sam_h = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")
    values = [False, True, False, True, False, True]
    barrier = threading.Barrier(len(values))
    clients = [make_client() for _ in values]

    def worker(args):
        client, value = args
        barrier.wait()
        return client.patch(
            "/coordinators/me/availability", json={"is_available": value}, headers=sam_h
        )

    with ThreadPoolExecutor(max_workers=len(values)) as pool:
        results = list(pool.map(worker, zip(clients, values)))

    assert all(r.status_code == 200 for r in results)
    db.expire_all()
    final = db.get(User, sam.id).is_available
    history = make_client().get("/coordinators/me/availability-history", headers=sam_h).json()
    assert history, "at least the first change must be recorded"
    assert history[0]["is_available"] is final  # newest entry always agrees with the flag
    # No two neighbouring entries repeat a value: every entry is a real CHANGE.
    ordered = [h["is_available"] for h in reversed(history)]
    assert all(a != b for a, b in zip(ordered, ordered[1:])), ordered


# --------------------------------------------------------------------------
# Submissions racing an unavailable coordinator (SCRUM-24 AC2)
# --------------------------------------------------------------------------


def test_events_submitted_at_the_same_moment_never_go_to_a_coordinator_who_is_unavailable(
    make_client, client, make_user, db
):
    _o, org_h = make_user(Role.ORGANISER, "org@connectsphere.test", "Priya Menon")
    sam, _sh = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan", available=False)
    priya, _ph = make_user(Role.COORDINATOR, "priya@connectsphere.test", "Priya Nair")
    lee, _lh = make_user(Role.COORDINATOR, "lee@connectsphere.test", "Lee Wong")
    ids = [draft(client, org_h, name=f"Event {i}") for i in range(THREADS)]
    queue = list(ids)
    lock = threading.Lock()

    def submit(c):
        with lock:
            event_id = queue.pop()
        return c.post(f"/events/{event_id}/submit", headers=org_h)

    results = race(make_client, THREADS, submit)

    assert all(r.status_code == 200 for r in results)
    db.expire_all()
    owners = [db.get(Event, i).coordinator_id for i in ids]
    assert sam.id not in owners
    assert None not in owners  # somebody was available, so nothing is left unassigned
    assert set(owners) <= {priya.id, lee.id}
