"""Recording equipment moves an approved event into planning.

The same step the first venue booking makes (SCRUM-39 AC3), applied to the
Coordinator's equipment requirements (SCRUM-43): upon an 'Event Approved'
Event, when the Coordinator records an Equipment Requirement, the Event moves
to 'Planning Event'.

    PL1  the first requirement on an 'Event Approved' event moves it to
         'Planning Event'
    PL2  the move is in the Activity Log with the Coordinator's name and time
    PL3  an event already in planning, or later, is left where it is, and a
         second requirement logs nothing more
    PL4  a requirement that is refused moves nothing
    PL5  an event assigned to someone else is refused and not moved
"""

import pytest

from app.core.roles import Role
from app.models.enums import EventStatus
from app.models.events import Event, EventStatusHistory
from tests.test_equipment_requirements import _added, _add, _equipment, _event, _user


def _setup(client, db_session, status=EventStatus.event_approved):
    organiser, _ = _user(client, db_session, Role.ORGANISER)
    coordinator, headers = _user(client, db_session, Role.COORDINATOR, name="Sam Tan")
    _equipment(db_session, "Shure BLX24")
    event = _event(db_session, organiser, coordinator, status=status)
    return event, coordinator, headers


def _status(db_session, event):
    db_session.expire_all()
    return db_session.get(Event, event.id).status


def _moves(db_session, event):
    return (
        db_session.query(EventStatusHistory)
        .filter(EventStatusHistory.event_id == event.id, EventStatusHistory.to_status == EventStatus.planning_event)
        .all()
    )


def test_pl1_the_first_requirement_moves_an_approved_event_to_planning_event(client, db_session):
    event, _, headers = _setup(client, db_session)

    _added(client, headers, event.id)

    assert _status(db_session, event) == EventStatus.planning_event


def test_pl2_the_move_is_logged_with_the_coordinators_name_and_time(client, db_session):
    event, coordinator, headers = _setup(client, db_session)
    _added(client, headers, event.id)

    log = client.get(f"/events/assigned/{event.id}", headers=headers).json()["activity"]

    entry = next(e for e in log if e["to_status"] == EventStatus.planning_event)
    assert entry["changed_by_name"] == "Sam Tan"
    assert entry["from_status"] == EventStatus.event_approved
    assert entry["created_at"]


def test_pl3_a_second_requirement_does_not_log_the_move_again(client, db_session):
    event, _, headers = _setup(client, db_session)

    _added(client, headers, event.id)
    _added(client, headers, event.id)

    assert len(_moves(db_session, event)) == 1
    assert _status(db_session, event) == EventStatus.planning_event


@pytest.mark.parametrize("status", [EventStatus.planning_event, EventStatus.safety_check_passed])
def test_pl3_an_event_already_in_planning_or_later_is_left_where_it_is(client, db_session, status):
    event, _, headers = _setup(client, db_session, status=status)

    _added(client, headers, event.id)

    assert _status(db_session, event) == status
    assert _moves(db_session, event) == []


def test_pl4_a_requirement_that_is_refused_moves_nothing(client, db_session):
    event, _, headers = _setup(client, db_session)

    res = _add(client, headers, event.id, quantity_needed=0)

    assert res.status_code == 422
    assert _status(db_session, event) == EventStatus.event_approved
    assert _moves(db_session, event) == []


def test_pl4_an_event_that_is_not_yet_approved_refuses_the_requirement_and_stays_put(client, db_session):
    event, _, headers = _setup(client, db_session, status=EventStatus.under_review)

    res = _add(client, headers, event.id)

    assert res.status_code == 409
    assert _status(db_session, event) == EventStatus.under_review


def test_pl5_an_event_assigned_to_someone_else_is_refused_and_not_moved(client, db_session):
    event, _, _ = _setup(client, db_session)
    _, other_headers = _user(client, db_session, Role.COORDINATOR, name="Priya Nair")

    res = _add(client, other_headers, event.id)

    assert res.status_code == 404
    assert _status(db_session, event) == EventStatus.event_approved
    assert _moves(db_session, event) == []
