"""The Event statuses are exactly those of dod.md section 11a -- no more, no fewer.

dod.md is read at test time, so changing a status name there (or adding one)
without changing the code fails here. The same names must be spelled alike in
the Python enum, the database enum in db/schema.sql and the frontend labels.
"""

import re
from pathlib import Path

from app.models.enums import (
    ACTIVE_ASSIGNMENT_STATUSES,
    CHANGE_REQUEST_ALLOWED_STATUSES,
    CHANGE_REQUEST_DISALLOWED_STATUSES,
    PLANNING_STATUSES,
    TERMINAL_EVENT_STATUSES,
    EventStatus,
)

ROOT = Path(__file__).resolve().parents[2]


def _dod_names() -> list[str]:
    text = (ROOT / "dod.md").read_text(encoding="utf-8")
    section = text.split("### 11a.")[1].split("### 11b.")[0]
    return re.findall(r"^- \*\*(.+?)\*\* –", section, flags=re.MULTILINE)


def _slug(name: str) -> str:
    """'Safety Check Passed (Event Confirmed)' -> 'safety_check_passed'."""
    name = re.sub(r"\(.*?\)", "", name)
    return re.sub(r"[^a-z]+", "_", name.lower()).strip("_")


def test_dod_lists_eleven_event_statuses():
    assert len(_dod_names()) == 11


def test_python_enum_is_exactly_the_dod_statuses():
    assert [s.value for s in EventStatus] == [_slug(n) for n in _dod_names()]


def test_database_enum_is_exactly_the_dod_statuses():
    schema = (ROOT / "backend/db/schema.sql").read_text(encoding="utf-8")
    block = re.search(r"create type event_status as enum \((.*?)\);", schema, flags=re.S).group(1)
    assert re.findall(r"'(\w+)'", block) == [_slug(n) for n in _dod_names()]


def test_frontend_labels_are_exactly_the_dod_names():
    source = (ROOT / "frontend/src/lib/events.ts").read_text(encoding="utf-8")
    block = source.split("export const EVENT_STATUS_LABELS")[1].split("}")[0]
    assert re.findall(r"\]: '(.+?)',", block) == _dod_names()


def test_the_down_migration_exists_beside_the_up_migration():
    assert (ROOT / "backend/sql/018_event_statuses_follow_dod.sql").exists()
    assert (ROOT / "backend/sql/down/018_event_statuses_follow_dod.sql").exists()


def test_shared_status_groups_cover_the_current_workflow():
    assert EventStatus.awaiting_safety_check in CHANGE_REQUEST_ALLOWED_STATUSES
    assert set(CHANGE_REQUEST_DISALLOWED_STATUSES) == {
        EventStatus.draft,
        EventStatus.event_completed,
        EventStatus.event_cancelled,
        EventStatus.event_rejected,
    }
    assert set(CHANGE_REQUEST_ALLOWED_STATUSES) == set(EventStatus) - set(
        CHANGE_REQUEST_DISALLOWED_STATUSES
    )
    assert set(TERMINAL_EVENT_STATUSES) == {
        EventStatus.event_completed,
        EventStatus.event_cancelled,
        EventStatus.event_rejected,
    }
    assert set(ACTIVE_ASSIGNMENT_STATUSES) == set(EventStatus) - {
        EventStatus.draft,
        *TERMINAL_EVENT_STATUSES,
    }
    assert PLANNING_STATUSES == (EventStatus.event_approved, EventStatus.planning_event)
