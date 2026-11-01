"""Unit tests for the less common replies to a clarification request.

SCRUM-103  Respond to Clarification Request as Event Organiser

    As an Event Organiser, I want to respond to an Event Coordinator's
    clarification request on my Event Request, so that the review can continue
    without delay.

    AC2  when a reply is saved, the assigned Event Coordinator is notified
    AC6  amended Event Request fields are saved, the status becomes Under
         Review and the Activity Log shows what changed

The main paths are tests/test_clarifications.py; these are the branches it
leaves unexecuted.
"""

from app.models.enums import EventStatus, NotificationType
from app.models.equipment import Equipment
from app.models.notifications import Notification
from tests.test_clarifications import _awaiting, _event, _log, _reply, w  # noqa: F401


def test_scrum103_ac2_a_reply_on_an_event_with_no_coordinator_notifies_nobody(client, w):  # noqa: F811
    _awaiting(client, w)
    event = _event(w)
    event.coordinator_id = None
    w["db"].commit()

    assert _reply(client, w).status_code == 201

    assert w["db"].query(Notification).filter_by(type=NotificationType.clarification_replied).count() == 0
    assert _event(w).status == EventStatus.under_review


def test_scrum103_ac6_amending_the_equipment_is_saved_and_logged(client, w):  # noqa: F811
    item = Equipment(name="Projector", category="Projection", total_quantity=10)
    w["db"].add(item)
    w["db"].commit()
    _awaiting(client, w)

    res = _reply(
        client,
        w,
        {
            "message": "Added a projector.",
            "updates": {"equipment_items": [{"equipment_id": item.id, "quantity_requested": 2}]},
        },
    )

    assert res.status_code == 201
    [line] = _event(w).equipment_items
    assert line.equipment_id == item.id and line.quantity_requested == 2
    assert "equipment_items updated" in _log(client, w)[0]["note"]


def test_scrum103_ac6_a_reply_that_changes_nothing_logs_only_the_message(client, w):  # noqa: F811
    _awaiting(client, w)
    same = _event(w).expected_attendance

    res = _reply(client, w, {"message": "Nothing to change.", "updates": {"expected_attendance": same}})

    assert res.status_code == 201
    assert _log(client, w)[0]["note"] == "Nothing to change."
