"""Technical Support equipment notifications, on real PostgreSQL.

The SQLite unit tests (tests/test_tech_support_equipment_notices.py) prove
the wording and the rules; these prove that on the production engine each
notification is written in the same transaction as the change -- a change
that is refused leaves no notification behind -- and that the old and new
date/time survive the timestamptz round trip.
"""

from datetime import datetime, timezone

import pytest

from app.core.roles import Role
from app.models.enums import EquipmentOperationalStatus, EventStatus
from app.models.equipment import Equipment
from app.models.events import Event
from app.models.notifications import Notification

pytestmark = pytest.mark.integration

START = datetime(2026, 11, 2, 9, tzinfo=timezone.utc)
END = datetime(2026, 11, 2, 17, tzinfo=timezone.utc)


def _world(db, make_user):
    org, org_h = make_user(Role.ORGANISER, "org@connectsphere.test", "Olivia Organiser")
    coord, coord_h = make_user(Role.COORDINATOR, "sam@connectsphere.test", "Sam Tan")
    techs = [make_user(Role.TECH_SUPPORT, f"tech{i}@connectsphere.test", f"Tech {i}")[0] for i in (1, 2)]
    db.add(
        Equipment(
            name="Shure BLX24", category="Audio", description="Mic", total_quantity=10,
            location="Store", operational_status=EquipmentOperationalStatus.available,
        )
    )
    event = Event(
        organiser_id=org.id, coordinator_id=coord.id, name="Regional Partner Conference",
        proposed_start=START, proposed_end=END, status=EventStatus.event_approved,
    )
    db.add(event)
    db.commit()
    return event.id, org_h, coord_h, techs


def _messages(db, type):
    db.expire_all()
    return [n.message for n in db.query(Notification).filter_by(type=type).order_by(Notification.id)]


def test_ac1_ac2_ac3_notices_are_written_with_the_change_on_postgres(client, db, make_user):
    event_id, org_h, coord_h, techs = _world(db, make_user)

    # AC1: recorded.
    res = client.post(
        f"/equipment-requirements/events/{event_id}", json={"category": "Audio", "quantity_needed": 6}, headers=coord_h
    )
    assert res.status_code == 201, res.text
    rid = res.json()["id"]
    assert _messages(db, "equipment_required") == [
        "Equipment required for 'Regional Partner Conference' (2 Nov 2026, 09:00-17:00 UTC): 6 x Audio."
    ] * len(techs)

    # A refused change rolls back with no notification.
    refused = client.post(
        f"/equipment-requirements/events/{event_id}", json={"category": "Teleporters", "quantity_needed": 1}, headers=coord_h
    )
    assert refused.status_code == 422
    assert len(_messages(db, "equipment_required")) == len(techs)

    # AC2: changed.
    assert client.patch(f"/equipment-requirements/{rid}", json={"quantity_needed": 8}, headers=coord_h).status_code == 200
    assert all("quantity 6 -> 8." in m for m in _messages(db, "equipment_requirement_changed"))

    # AC3: moved -- old and new date/time after the timestamptz round trip.
    requested = client.post(
        f"/events/{event_id}/change-requests",
        json={
            "description": "New date",
            "proposed_changes": {"proposed_start": "2026-11-09T13:00:00Z", "proposed_end": "2026-11-09T18:00:00Z"},
        },
        headers=org_h,
    )
    assert requested.status_code == 201, requested.text
    approved = client.post(f"/events/change-requests/{requested.json()['id']}/approve", json={}, headers=coord_h)
    assert approved.status_code == 200, approved.text
    moved = _messages(db, "equipment_event_rescheduled")
    assert len(moved) == len(techs)
    assert "from 2 Nov 2026, 09:00-17:00 UTC to 9 Nov 2026, 13:00-18:00 UTC" in moved[0]

    # AC2: removed.
    assert client.delete(f"/equipment-requirements/{rid}", headers=coord_h).status_code == 204
    assert len(_messages(db, "equipment_requirement_removed")) == len(techs)
