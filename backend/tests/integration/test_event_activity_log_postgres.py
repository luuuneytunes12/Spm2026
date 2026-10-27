"""The append-only Event Activity Log on the production database engine,
and the event workflow decisions that must hold under concurrent requests."""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.roles import Role
from app.models.enums import ChangeRequestStatus, EventStatus
from app.models.events import Event, EventChangeRequest, EventStatusHistory
from app.models.notifications import Notification
from app.services.event_activity import event_activity

pytestmark = pytest.mark.integration


def test_ac3_postgres_refuses_activity_log_updates_and_deletes(db, make_user):
    organiser, _ = make_user(Role.ORGANISER, "activity-owner@integration.test")
    event = Event(
        organiser_id=organiser.id,
        name="Immutable Event",
        status=EventStatus.draft,
    )
    db.add(event)
    db.flush()
    entry = EventStatusHistory(
        event_id=event.id,
        changed_by=organiser.id,
        from_status="draft",
        to_status="draft",
        note="Original activity.",
    )
    db.add(entry)
    db.commit()

    with pytest.raises(DBAPIError, match="immutable"):
        db.execute(
            text("update event_status_history set note = 'Edited' where id = :id"),
            {"id": entry.id},
        )
    db.rollback()

    with pytest.raises(DBAPIError, match="immutable"):
        db.execute(
            text("delete from event_status_history where id = :id"),
            {"id": entry.id},
        )
    db.rollback()

    db.expire_all()
    assert db.get(EventStatusHistory, entry.id).note == "Original activity."


def test_ac1_postgres_persists_system_as_the_hold_expiry_actor(db, make_user):
    organiser, _ = make_user(Role.ORGANISER, "system-actor@integration.test")
    event = Event(
        organiser_id=organiser.id,
        name="System Activity",
        status=EventStatus.planning_event,
    )
    db.add(event)
    db.flush()
    db.add(
        EventStatusHistory(
            event_id=event.id,
            changed_by=None,
            from_status=event.status,
            to_status=event.status,
            note="Tentative hold expired.",
            actor_name="System",
        )
    )
    db.commit()

    assert event_activity(db, event.id)[0].changed_by_name == "System"


def test_ac3_postgres_deleting_an_event_still_removes_its_log(db, make_user):
    """The trigger refuses an entry on its own, not the cascade from its
    Event: the e2e cleanup (frontend/e2e/support/db.ts) deletes Events."""
    organiser, _ = make_user(Role.ORGANISER, "cascade-owner@integration.test")
    event = Event(organiser_id=organiser.id, name="Cascade", status=EventStatus.draft)
    db.add(event)
    db.flush()
    db.add(
        EventStatusHistory(
            event_id=event.id,
            changed_by=organiser.id,
            from_status="draft",
            to_status="draft",
            note="Some history.",
        )
    )
    db.commit()
    event_id = event.id

    db.query(Event).filter(Event.id == event_id).delete(synchronize_session=False)
    db.commit()

    assert db.query(EventStatusHistory).filter_by(event_id=event_id).count() == 0


THREADS = 6


def _race(make_client, call):
    barrier = threading.Barrier(THREADS)
    clients = [make_client() for _ in range(THREADS)]

    def worker(index_and_client):
        index, client = index_and_client
        barrier.wait()
        return call(index, client)

    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        return list(pool.map(worker, enumerate(clients)))


def _assigned_event(db, make_user, status):
    organiser, organiser_headers = make_user(
        Role.ORGANISER, "race-owner@integration.test", "Race Owner"
    )
    coordinator, coordinator_headers = make_user(
        Role.COORDINATOR, "race-coordinator@integration.test", "Race Coordinator"
    )
    event = Event(
        organiser_id=organiser.id,
        coordinator_id=coordinator.id,
        name="Race Event",
        status=status,
        proposed_start=datetime(2020, 1, 1, 9, tzinfo=timezone.utc),
        proposed_end=datetime(2020, 1, 1, 17, tzinfo=timezone.utc),
        expected_attendance=50,
    )
    db.add(event)
    db.commit()
    return organiser, organiser_headers, coordinator_headers, event.id


def test_us3_ac7_approve_and_reject_fired_together_decide_the_request_once(
    db, make_user, make_client
):
    organiser, _, coordinator_headers, event_id = _assigned_event(
        db, make_user, EventStatus.under_review
    )
    request = EventChangeRequest(
        event_id=event_id,
        requested_by=organiser.id,
        description="Race me.",
        proposed_changes={"description": "Raced"},
    )
    db.add(request)
    db.commit()
    # Read once here: a commit expires `request`, and reading it from the
    # racing threads would reload it through this one shared session at once.
    request_id = request.id

    results = _race(
        make_client,
        lambda i, c: c.post(
            f"/events/change-requests/{request_id}/{'approve' if i % 2 else 'reject'}",
            headers=coordinator_headers,
            json={},
        ),
    )

    codes = sorted(r.status_code for r in results)
    assert codes == [200] + [409] * (THREADS - 1), codes
    db.expire_all()
    assert db.get(EventChangeRequest, request_id).status != ChangeRequestStatus.pending
    assert db.query(EventStatusHistory).filter(
        EventStatusHistory.event_id == event_id,
        EventStatusHistory.note.like("Change Request %"),
    ).count() == 1
    assert db.query(Notification).filter(
        Notification.user_id == organiser.id,
        Notification.type.in_(["event_change_approved", "event_change_rejected"]),
    ).count() == 1


def test_us4_ac1_ac5_a_completion_fired_many_times_is_recorded_once(
    db, make_user, make_client
):
    _, _, coordinator_headers, event_id = _assigned_event(
        db, make_user, EventStatus.safety_check_passed
    )

    results = _race(
        make_client,
        lambda i, c: c.post(f"/events/{event_id}/complete", headers=coordinator_headers),
    )

    codes = sorted(r.status_code for r in results)
    assert codes == [200] + [409] * (THREADS - 1), codes
    db.expire_all()
    assert db.get(Event, event_id).status == EventStatus.event_completed
    assert db.query(EventStatusHistory).filter_by(
        event_id=event_id, to_status=EventStatus.event_completed
    ).count() == 1
