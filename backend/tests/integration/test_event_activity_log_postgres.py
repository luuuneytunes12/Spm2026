"""The append-only Event Activity Log on the production database engine."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.roles import Role
from app.models.enums import EventStatus
from app.models.events import Event, EventStatusHistory
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
