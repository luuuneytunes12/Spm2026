"""Tests for "Notify Technical Support of equipment changes".

    As a Technical Support Staff member, I want to be notified when
    equipment is required, changed or removed for an Event, or when the
    Event's date or time changes, so that I can review and reserve it
    promptly.

    AC1  a requirement is saved: every Technical Support Staff member is
         notified with the Event name, equipment, quantity and date/time
    AC2  its type, quantity or technical notes change, or it is removed:
         they are told what changed, including when equipment is already
         reserved for it
    AC3  an Event with a requirement or reservation changes date or time:
         they are told the old and new date/time
"""

from datetime import datetime, timezone

import pytest

from app.core.roles import Role
from app.models.enums import EquipmentStatus, EventStatus, NotificationType
from app.models.equipment import Equipment
from app.models.events import Event
from app.models.notifications import Notification
from app.schemas.event import EventIn
from app.services.clarifications import reply_to_clarification
from app.services.submission_notice import EventNotice
from app.services.tech_support_notices import (
    EquipmentRequiredNotice,
    EquipmentRequirementChangedNotice,
    EquipmentRequirementRemovedNotice,
    EventRescheduledNotice,
    TechSupportNotice,
    when,
)
from tests.test_equipment_requirement_fulfillment import _reserved
from tests.test_equipment_requirements import _added, _equipment, _organiser_line, _user, _world

REQUIRED = NotificationType.equipment_required.value
CHANGED = NotificationType.equipment_requirement_changed.value
REMOVED = NotificationType.equipment_requirement_removed.value
MOVED = NotificationType.equipment_event_rescheduled.value

START = datetime(2026, 11, 2, 9, tzinfo=timezone.utc)
END = datetime(2026, 11, 2, 17, tzinfo=timezone.utc)


def _setup(client, db_session):
    """The equipment-requirements world, its event dated, and two Technical
    Support Staff members."""
    w = _world(client, db_session)
    w.event.proposed_start, w.event.proposed_end = START, END
    db_session.commit()
    w.tech, w.tech_h = _user(client, db_session, Role.TECH_SUPPORT, name="Tess Tech")
    w.tech2, w.tech2_h = _user(client, db_session, Role.TECH_SUPPORT, name="Theo Tech")
    return w


def _inbox(client, headers, type):
    return [n for n in client.get("/notifications", headers=headers).json() if n["type"] == type]


def _edit(client, w, rid, **body):
    res = client.patch(f"/equipment-requirements/{rid}", json=body, headers=w.headers)
    assert res.status_code == 200, res.text
    return res


# --- AC1: recorded -> event, equipment, quantity, date/time -------------------


def test_ac1_recording_a_requirement_notifies_technical_support_with_the_details(client, db_session):
    w = _setup(client, db_session)
    _added(client, w.headers, w.event.id, category="Audio", quantity_needed=6, technical_notes="Wireless, two bands")

    [notice] = _inbox(client, w.tech_h, REQUIRED)
    assert notice["event_id"] == w.event.id
    assert notice["message"] == (
        "Equipment required for 'Regional Partner Conference' (2 Nov 2026, 09:00-17:00 UTC): "
        "6 x Audio. Notes: Wireless, two bands"
    )


def test_ac1_every_technical_support_staff_member_is_notified(client, db_session):
    w = _setup(client, db_session)
    _added(client, w.headers, w.event.id)
    assert len(_inbox(client, w.tech_h, REQUIRED)) == len(_inbox(client, w.tech2_h, REQUIRED)) == 1


def test_ac1_each_requirement_is_its_own_notification(client, db_session):
    w = _setup(client, db_session)
    _added(client, w.headers, w.event.id, category="Audio", quantity_needed=2)
    _added(client, w.headers, w.event.id, category="Projection", quantity_needed=1)
    messages = [n["message"] for n in _inbox(client, w.tech_h, REQUIRED)]
    assert sorted(m.split(": ")[-1] for m in messages) == ["1 x Projection.", "2 x Audio."]


@pytest.mark.parametrize("role", [Role.ORGANISER, Role.COORDINATOR, Role.VENUE_STAFF, Role.SAFETY_OFFICER])
def test_ac1_negative_nobody_but_technical_support_is_told(client, db_session, role):
    w = _setup(client, db_session)
    other, _ = _user(client, db_session, role)
    _added(client, w.headers, w.event.id)
    assert db_session.query(Notification).filter_by(user_id=other.id, type=REQUIRED).count() == 0
    assert db_session.query(Notification).filter_by(user_id=w.coordinator.id, type=REQUIRED).count() == 0


def test_ac1_negative_a_refused_requirement_notifies_nobody(client, db_session):
    w = _setup(client, db_session)
    res = client.post(
        f"/equipment-requirements/events/{w.event.id}",
        json={"category": "Teleporters", "quantity_needed": 1},
        headers=w.headers,
    )
    assert res.status_code == 422
    assert db_session.query(Notification).filter_by(type=REQUIRED).count() == 0


# --- AC2: changed or removed -> what changed, and what is reserved -----------


def test_ac2_changing_the_quantity_says_from_what_to_what(client, db_session):
    w = _setup(client, db_session)
    rid = _added(client, w.headers, w.event.id, quantity_needed=6)["id"]
    _edit(client, w, rid, quantity_needed=8)
    [notice] = _inbox(client, w.tech_h, CHANGED)
    assert notice["message"] == (
        "Equipment requirement changed for 'Regional Partner Conference' (2 Nov 2026, 09:00-17:00 UTC): "
        "Audio - quantity 6 -> 8."
    )


def test_ac2_changing_the_type_and_the_notes_lists_both(client, db_session):
    w = _setup(client, db_session)
    rid = _added(client, w.headers, w.event.id, category="Audio", technical_notes="XLR")["id"]
    _edit(client, w, rid, category="Projection", technical_notes="HDMI")
    [notice] = _inbox(client, w.tech_h, CHANGED)
    assert "Projection - type Audio -> Projection; technical notes changed to: HDMI." in notice["message"]


@pytest.mark.parametrize(
    ("before", "after", "said"),
    [(None, "HDMI", "technical notes added: HDMI"), ("HDMI", None, "technical notes removed")],
)
def test_ac2_notes_added_or_removed_say_so(client, db_session, before, after, said):
    w = _setup(client, db_session)
    rid = _added(client, w.headers, w.event.id, technical_notes=before)["id"]
    _edit(client, w, rid, technical_notes=after)
    [notice] = _inbox(client, w.tech_h, CHANGED)
    assert said in notice["message"]


def test_ac2_a_change_to_a_reserved_requirement_says_what_is_reserved(client, db_session):
    w = _setup(client, db_session)
    mic = db_session.query(Equipment).filter_by(name="Shure BLX24").one()  # from _world
    rid = _added(client, w.headers, w.event.id, category="Audio", quantity_needed=4)["id"]
    _reserved(client, w.tech_h, rid, mic.id, quantity=3)

    _edit(client, w, rid, quantity_needed=6)

    [notice] = _inbox(client, w.tech_h, CHANGED)
    assert "quantity 4 -> 6." in notice["message"]
    assert "3 already reserved for it: check the reservation still fits." in notice["message"]


def test_ac2_removing_a_requirement_says_what_is_no_longer_needed(client, db_session):
    w = _setup(client, db_session)
    rid = _added(client, w.headers, w.event.id, category="Projection", quantity_needed=2)["id"]
    assert client.delete(f"/equipment-requirements/{rid}", headers=w.headers).status_code == 204
    [notice] = _inbox(client, w.tech_h, REMOVED)
    assert notice["message"] == (
        "Equipment requirement removed for 'Regional Partner Conference' (2 Nov 2026, 09:00-17:00 UTC): "
        "2 x Projection is no longer needed."
    )
    assert len(_inbox(client, w.tech2_h, REMOVED)) == 1


def test_ac2_frozen_literal_an_edit_that_changes_nothing_tells_no_one(client, db_session):
    """The edit form always sends the type again; that alone is not a change."""
    w = _setup(client, db_session)
    rid = _added(client, w.headers, w.event.id, category="Audio", quantity_needed=6)["id"]
    _edit(client, w, rid, category="audio", quantity_needed=6)  # same type, any case
    assert db_session.query(Notification).filter_by(type=CHANGED).count() == 0


def test_ac2_negative_a_refused_edit_or_removal_tells_no_one(client, db_session):
    w = _setup(client, db_session)
    mic = db_session.query(Equipment).filter_by(name="Shure BLX24").one()  # from _world
    rid = _added(client, w.headers, w.event.id, category="Audio", quantity_needed=4)["id"]
    _reserved(client, w.tech_h, rid, mic.id, quantity=3)

    below = client.patch(f"/equipment-requirements/{rid}", json={"quantity_needed": 1}, headers=w.headers)
    removed = client.delete(f"/equipment-requirements/{rid}", headers=w.headers)

    assert below.status_code == 409 and removed.status_code == 409
    assert db_session.query(Notification).filter(Notification.type.in_([CHANGED, REMOVED])).count() == 0


# --- AC3: the Event moved -> old and new date/time ----------------------------


def _move(client, w, start, end):
    """The Organiser asks to move the Event; its Coordinator approves."""
    requested = client.post(
        f"/events/{w.event.id}/change-requests",
        json={"description": "New date", "proposed_changes": {"proposed_start": start.isoformat(), "proposed_end": end.isoformat()}},
        headers=w.organiser_headers,
    )
    assert requested.status_code == 201, requested.text
    res = client.post(f"/events/change-requests/{requested.json()['id']}/approve", json={}, headers=w.headers)
    assert res.status_code == 200, res.text


NEW_START = datetime(2026, 11, 9, 13, tzinfo=timezone.utc)
NEW_END = datetime(2026, 11, 9, 18, tzinfo=timezone.utc)


def test_ac3_moving_an_event_with_a_requirement_gives_the_old_and_new_date_and_time(client, db_session):
    w = _setup(client, db_session)
    _added(client, w.headers, w.event.id)

    _move(client, w, NEW_START, NEW_END)

    [notice] = _inbox(client, w.tech_h, MOVED)
    assert notice["message"] == (
        "'Regional Partner Conference' has moved from 2 Nov 2026, 09:00-17:00 UTC to "
        "9 Nov 2026, 13:00-18:00 UTC. Check its equipment requirements and reservations "
        "for the new date and time."
    )
    assert len(_inbox(client, w.tech2_h, MOVED)) == 1


def test_ac3_an_event_with_only_reserved_organiser_equipment_is_covered_too(client, db_session):
    w = _setup(client, db_session)
    line = _organiser_line(db_session, w.event, _equipment(db_session, "Extra screen", category="Projection"))
    line.status = EquipmentStatus.reserved
    db_session.commit()
    _move(client, w, NEW_START, NEW_END)
    assert len(_inbox(client, w.tech_h, MOVED)) == 1


def test_ac3_only_the_time_changing_is_a_move(client, db_session):
    w = _setup(client, db_session)
    _added(client, w.headers, w.event.id)
    _move(client, w, START, datetime(2026, 11, 2, 19, tzinfo=timezone.utc))
    [notice] = _inbox(client, w.tech_h, MOVED)
    assert "from 2 Nov 2026, 09:00-17:00 UTC to 2 Nov 2026, 09:00-19:00 UTC" in notice["message"]


def test_ac3_negative_an_event_with_no_equipment_tells_no_one(client, db_session):
    w = _setup(client, db_session)
    _move(client, w, NEW_START, NEW_END)
    assert db_session.query(Notification).filter_by(type=MOVED).count() == 0


def test_ac3_negative_a_change_that_keeps_the_date_and_time_tells_no_one(client, db_session):
    w = _setup(client, db_session)
    _added(client, w.headers, w.event.id)
    requested = client.post(
        f"/events/{w.event.id}/change-requests",
        json={"description": "Rename", "proposed_changes": {"name": "Regional Partner Summit"}},
        headers=w.organiser_headers,
    ).json()
    client.post(f"/events/change-requests/{requested['id']}/approve", json={}, headers=w.headers)
    assert db_session.query(Notification).filter_by(type=MOVED).count() == 0


def test_ac3_negative_a_rejected_move_tells_no_one(client, db_session):
    w = _setup(client, db_session)
    _added(client, w.headers, w.event.id)
    requested = client.post(
        f"/events/{w.event.id}/change-requests",
        json={"description": "New date", "proposed_changes": {"proposed_start": NEW_START.isoformat(), "proposed_end": NEW_END.isoformat()}},
        headers=w.organiser_headers,
    ).json()
    client.post(f"/events/change-requests/{requested['id']}/reject", json={"review_notes": "No."}, headers=w.headers)
    assert db_session.query(Notification).filter_by(type=MOVED).count() == 0


def test_ac3_a_move_in_an_organisers_clarification_reply_is_covered_too(client, db_session):
    w = _setup(client, db_session)
    _added(client, w.headers, w.event.id)
    event = db_session.get(Event, w.event.id)
    reply_to_clarification(
        db_session, event, w.organiser, "Moved it a week.",
        EventIn(proposed_start=NEW_START, proposed_end=NEW_END),
    )
    db_session.commit()
    [notice] = _inbox(client, w.tech_h, MOVED)
    assert "to 9 Nov 2026, 13:00-18:00 UTC" in notice["message"]


# --- OOP and formatting ---------------------------------------------------------


def test_every_notice_extends_the_technical_support_base():
    assert issubclass(TechSupportNotice, EventNotice)
    for cls in (EquipmentRequiredNotice, EquipmentRequirementChangedNotice, EquipmentRequirementRemovedNotice, EventRescheduledNotice):
        assert issubclass(cls, TechSupportNotice)


def test_when_reads_a_day_a_span_and_no_date():
    assert when(START, END) == "2 Nov 2026, 09:00-17:00 UTC"
    assert when(START, datetime(2026, 11, 3, 2, tzinfo=timezone.utc)) == "2 Nov 2026 09:00 - 3 Nov 2026 02:00 UTC"
    assert when(None, None) == "no date set"
