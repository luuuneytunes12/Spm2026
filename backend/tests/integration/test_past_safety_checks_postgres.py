"""Past Safety Checks on real PostgreSQL.

The list is one row per event, newest decision first, read from timestamped
activity-log rows -- ordering and timestamp handling that SQLite (second-
resolution CURRENT_TIMESTAMP, no time zone) does not exercise.
"""

from datetime import datetime, timedelta, timezone

from app.core.roles import Role
from app.models.enums import EventStatus
from app.models.events import Event, EventStatusHistory
from app.routers.events import SAFETY_RESULT_NOTES

START = datetime(2026, 11, 2, 9, tzinfo=timezone.utc)
DECIDED = datetime(2026, 10, 10, 8, tzinfo=timezone.utc)


def _event(db, org, name, status):
    event = Event(
        organiser_id=org.id,
        name=name,
        proposed_start=START,
        proposed_end=START + timedelta(hours=8),
        status=status,
    )
    db.add(event)
    db.commit()
    return event


def _decision(db, event, officer, to_status, note, at):
    db.add(
        EventStatusHistory(
            event_id=event.id,
            changed_by=officer.id,
            from_status=EventStatus.awaiting_safety_check,
            to_status=to_status,
            note=note,
            created_at=at,
        )
    )


def test_ac1_one_row_per_event_newest_decision_first(make_client, db, make_user):
    org, _ = make_user(Role.ORGANISER, "org@connectsphere.test", "Olivia Organiser")
    officer, officer_h = make_user(Role.SAFETY_OFFICER, "safety@connectsphere.test", "Sam Safety")
    other, _ = make_user(Role.SAFETY_OFFICER, "safety2@connectsphere.test", "Sasha Second")
    first = _event(db, org, "First Event", EventStatus.safety_check_passed)
    second = _event(db, org, "Second Event", EventStatus.event_cancelled)
    rejected, changes = SAFETY_RESULT_NOTES["Rejected"], SAFETY_RESULT_NOTES["Changes Requested"]
    # Microseconds apart: the order must come from the timestamps, not the ids.
    _decision(db, first, officer, EventStatus.safety_check_passed, "passed", DECIDED + timedelta(microseconds=30))
    _decision(db, first, officer, EventStatus.planning_event, rejected + "Exits", DECIDED + timedelta(microseconds=10))
    _decision(db, second, officer, EventStatus.planning_event, changes + "Move it", DECIDED + timedelta(microseconds=20))
    _decision(db, second, other, EventStatus.planning_event, rejected + "Theirs", DECIDED + timedelta(hours=1))
    db.commit()

    rows = make_client().get("/safety-checks/history", headers=officer_h).json()

    assert [(r["name"], r["decision"], r["reason"], r["status"]) for r in rows] == [
        ("First Event", "Approved", None, EventStatus.safety_check_passed),
        ("Second Event", "Changes Requested", "Move it", EventStatus.event_cancelled),
    ]


def test_ac3_detail_lists_every_officers_decision_newest_first(make_client, db, make_user):
    org, _ = make_user(Role.ORGANISER, "org@connectsphere.test", "Olivia Organiser")
    officer, officer_h = make_user(Role.SAFETY_OFFICER, "safety@connectsphere.test", "Sam Safety")
    other, _ = make_user(Role.SAFETY_OFFICER, "safety2@connectsphere.test", "Sasha Second")
    event = _event(db, org, "Regional Partner Conference", EventStatus.planning_event)
    rejected, changes = SAFETY_RESULT_NOTES["Rejected"], SAFETY_RESULT_NOTES["Changes Requested"]
    _decision(db, event, officer, EventStatus.planning_event, rejected + "First", DECIDED)
    _decision(db, event, other, EventStatus.planning_event, changes + "Second", DECIDED + timedelta(days=1))
    db.commit()

    decisions = make_client().get(f"/safety-checks/{event.id}", headers=officer_h).json()["decisions"]

    assert [(d["decision"], d["reason"], d["decided_by_name"]) for d in decisions] == [
        ("Changes Requested", "Second", "Sasha Second"),
        ("Rejected", "First", "Sam Safety"),
    ]
