"""Safety Check decisions, read back from the activity log.

A decision is an `event_status_history` row that leaves
`awaiting_safety_check`: a pass (-> `safety_check_passed`) or a send-back
whose note starts with one of SAFETY_RESULT_NOTES (routers/safety_checks.py
writes both). Other rows leaving that status -- a cancellation, say -- are
not decisions and are skipped.

Read only: the log is never written or changed here.
"""

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload

from app.models.enums import EventStatus
from app.models.events import EventStatusHistory
from app.routers.events import SAFETY_RESULT_NOTES
from app.schemas.safety_check import PastSafetyCheck, SafetyDecision

APPROVED = "Approved"


def _decision(entry: EventStatusHistory) -> SafetyDecision | None:
    """The decision `entry` records, or None if it records none."""
    if entry.to_status == EventStatus.safety_check_passed:
        result, reason = APPROVED, None
    else:
        note = entry.note or ""
        result = next((r for r, prefix in SAFETY_RESULT_NOTES.items() if note.startswith(prefix)), None)
        if result is None:
            return None
        reason = note.removeprefix(SAFETY_RESULT_NOTES[result])
    return SafetyDecision(
        decision=result,
        reason=reason,
        decided_by_name=entry.changed_by_user.name if entry.changed_by_user else None,
        decided_at=entry.created_at,
    )


class SafetyDecisionLog:
    """Every Safety Check decision on record, newest first."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _query(self) -> Select[tuple[EventStatusHistory]]:
        return (
            select(EventStatusHistory)
            .options(joinedload(EventStatusHistory.changed_by_user))
            .where(EventStatusHistory.from_status == EventStatus.awaiting_safety_check)
            .order_by(EventStatusHistory.created_at.desc(), EventStatusHistory.id.desc())
        )

    def _entries(self) -> list[tuple[EventStatusHistory, SafetyDecision]]:
        rows = self.db.scalars(self._query()).unique()
        return [(entry, decision) for entry in rows if (decision := _decision(entry)) is not None]

    def decisions(self) -> list[SafetyDecision]:
        return [decision for _, decision in self._entries()]


class EventSafetyDecisions(SafetyDecisionLog):
    """One Event's decisions, by any Safety Officer, newest first."""

    def __init__(self, db: Session, event_id: int) -> None:
        super().__init__(db)
        self.event_id = event_id

    def _query(self) -> Select[tuple[EventStatusHistory]]:
        return super()._query().where(EventStatusHistory.event_id == self.event_id)


class OfficerPastSafetyChecks(SafetyDecisionLog):
    """The Events one Safety Officer has decided: one row per Event with
    their latest decision on it, newest decision first. Events since
    cancelled or completed stay listed."""

    def __init__(self, db: Session, officer_id: int) -> None:
        super().__init__(db)
        self.officer_id = officer_id

    def _query(self) -> Select[tuple[EventStatusHistory]]:
        return (
            super()
            ._query()
            .options(joinedload(EventStatusHistory.event))
            .where(EventStatusHistory.changed_by == self.officer_id)
        )

    def rows(self) -> list[PastSafetyCheck]:
        seen: set[int] = set()
        rows: list[PastSafetyCheck] = []
        for entry, decision in self._entries():
            if entry.event_id in seen:
                continue
            seen.add(entry.event_id)
            event = entry.event
            rows.append(
                PastSafetyCheck(
                    id=event.id,
                    name=event.name,
                    proposed_start=event.proposed_start,
                    proposed_end=event.proposed_end,
                    status=event.status,
                    decision=decision.decision,
                    reason=decision.reason,
                    decided_at=decision.decided_at,
                )
            )
        return rows
