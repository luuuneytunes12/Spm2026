"""Can a requirement's link and Ercong's reservation be committed together?

Story B ("Update Equipment Requirement Status") ties a Coordinator's
requirement to the reservations that fulfil it. The link is OURS; the
reservation is Ercong's, made by his unchanged `reserve_equipment`, which
commits the session itself.

The design stands or falls on one claim: add our link to the session BEFORE
calling his function, and his own `db.commit()` writes both in the same
transaction -- so a reservation can never exist without its link, and a
link can never exist without its reservation. If that claim were false the
only alternative is two independent commits, which can leave a reservation
committed and its link lost. These tests prove the claim, on the real
function, before anything is built on it.

The link is keyed by (event, item), not by his row's id. His row's id does
not exist until his function creates it, so a link to the row could only be
written AFTER his commit -- which is the gap this design closes.
"""

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import event as sa_event
from sqlalchemy.exc import IntegrityError

from app.core.roles import Role
from app.models.enums import EquipmentStatus, EventStatus
from app.models.equipment import (
    CoordinatorEquipmentRequirement,
    Equipment,
    EquipmentRequest,
    RequirementReservationLink,
)
from app.models.events import Event
from app.models.user import User
from app.routers.equipment_reservations import reserve_equipment  # Ercong's, unchanged
from app.schemas.equipment_reservation import EquipmentReservationCreate

START = datetime(2026, 11, 2, 9, tzinfo=timezone.utc)
END = datetime(2026, 11, 2, 17, tzinfo=timezone.utc)


@pytest.fixture()
def world(db_session):
    def user(role):
        u = User(name=role.value, email=f"{role.value}@example.com", password_hash="x", role=role.value)
        db_session.add(u)
        db_session.flush()
        return u

    organiser, coordinator, tech = user(Role.ORGANISER), user(Role.COORDINATOR), user(Role.TECH_SUPPORT)
    mic = Equipment(name="Shure BLX24", category="Audio", total_quantity=10)
    db_session.add(mic)
    event = Event(
        name="Conference",
        organiser_id=organiser.id,
        coordinator_id=coordinator.id,
        status=EventStatus.approved,
        proposed_start=START,
        proposed_end=END,
    )
    db_session.add(event)
    db_session.flush()
    requirement = CoordinatorEquipmentRequirement(
        event_id=event.id, category="Audio", quantity_needed=4, created_by=coordinator.id
    )
    db_session.add(requirement)
    db_session.commit()
    return dict(tech=tech, mic=mic, event=event, requirement=requirement)


def _reserve(db_session, w, quantity=4):
    """Ercong's function, called as it is -- the way the orchestration will."""
    return reserve_equipment(
        body=EquipmentReservationCreate(
            event_id=w["event"].id, equipment_id=w["mic"].id, quantity=quantity
        ),
        db=db_session,
        user=w["tech"],
    )


def _pending_link(db_session, w):
    link = RequirementReservationLink(
        requirement_id=w["requirement"].id, event_id=w["event"].id, equipment_id=w["mic"].id
    )
    db_session.add(link)
    return link


def _commits(db_session):
    """Count the commits the session makes while the test runs."""
    seen = []
    sa_event.listen(db_session, "after_commit", lambda session: seen.append(1))
    return seen


def test_the_link_and_the_reservation_are_committed_together(db_session, world):
    commits = _commits(db_session)

    _pending_link(db_session, world)  # added BEFORE his function runs
    _reserve(db_session, world)

    # Exactly one commit -- his. Mine rides along; I never commit.
    assert len(commits) == 1
    # Rolling back now would discard anything still pending. Both are still
    # there, so both were committed, not merely flushed.
    db_session.rollback()
    assert db_session.query(RequirementReservationLink).count() == 1
    line = db_session.query(EquipmentRequest).one()
    assert line.status is EquipmentStatus.reserved
    assert line.quantity_requested == 4


def test_a_reservation_he_refuses_leaves_no_link_behind(db_session, world):
    """He answers 409 when fewer units are free than asked for. The link was
    only pending, so rolling back discards it with nothing else to undo."""
    _pending_link(db_session, world)

    with pytest.raises(HTTPException) as refused:
        _reserve(db_session, world, quantity=11)  # 10 owned
    db_session.rollback()

    assert refused.value.status_code == 409
    assert db_session.query(RequirementReservationLink).count() == 0
    assert db_session.query(EquipmentRequest).count() == 0


def test_a_link_that_cannot_be_written_stops_the_reservation_too(db_session, world):
    """The other direction: if OUR write fails, his reservation must not
    survive it. An item already linked for this event makes the new link a
    duplicate, which the database rejects when his commit flushes."""
    db_session.add(
        RequirementReservationLink(
            requirement_id=world["requirement"].id,
            event_id=world["event"].id,
            equipment_id=world["mic"].id,
        )
    )
    db_session.commit()

    _pending_link(db_session, world)  # a second link for the same (event, item)
    with pytest.raises(IntegrityError):
        _reserve(db_session, world)
    db_session.rollback()

    assert db_session.query(EquipmentRequest).count() == 0  # no reservation
    assert db_session.query(RequirementReservationLink).count() == 1  # only the first


def test_his_function_is_called_unchanged(world):
    """The orchestration depends on this exact signature, so a change to it
    fails here, loudly, rather than somewhere in the middle of a reservation."""
    import inspect

    params = inspect.signature(reserve_equipment).parameters
    assert list(params) == ["body", "db", "user"]
