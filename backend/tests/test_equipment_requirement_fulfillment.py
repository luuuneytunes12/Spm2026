"""Tests for the "Update Equipment Requirement Status" story.

    As a Technical Support Staff member, I want to update the status of an
    event's equipment requirements, so that the Event Coordinator can track
    progress.

Acceptance criteria:

    UR AC1  I can update the status of each requirement (e.g. "reserved",
            "unavailable") so the Event Coordinator can track progress.
    UR AC2  I can update the quantity of the equipment as changes appear.
    UR AC3  The updated status and quantity are visible to the Event
            Coordinator on the event record.

Each test is named after the criterion it covers; the mapping is in
docs/test-cases-equipment-requirements.md.

The contract under test (Technical Support unless stated):

    PATCH  /equipment-requirements/support/requirements/{id}
           set the status Technical Support owns, and/or quantity_needed
    POST   /equipment-requirements/{id}/reservations
           reserve an item for a requirement, through Ercong's reservation

Reserving here IS Ercong's reservation: his unchanged `reserve_equipment`
does the stock check, the overlap check and the write. These tests run the
real thing and use his own endpoints (availability, reservations list) to
confirm what it did. Nothing here re-tests his rules.

The statuses are the Definition of Done's (11b), and only those:

    Requested    waiting for Technical Support -- including a requirement only
                 part reserved: the DoD has no "in progress"
    Reserved     the full quantity is reserved. Never set by hand
    Unavailable  Technical Support cannot provide it; a REASON is required
    Available    its reservation was freed. Never set by hand

Reserved and Available are worked out, not stored. Unavailable is stored in
the existing enum's `rejected`, and nothing else is added to it.
"""

import itertools
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.core.roles import Role
from app.core.security import create_access_token
from app.models.enums import EquipmentStatus, EventStatus
from app.models.equipment import (
    CoordinatorEquipmentRequirement,
    EquipmentRequest,
    RequirementReservationLink,
)
from app.models.events import Event, EventStatusHistory
from app.models.user import User
from app.services.equipment_lines import replace_equipment_lines
from tests.test_equipment_requirements import (
    INACTIVE,
    _added,
    _equipment,
    _event,
    _organiser_line,
)

START = datetime(2026, 11, 2, 9, tzinfo=timezone.utc)
END = datetime(2026, 11, 2, 17, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_emails = itertools.count()


def _user(client, db_session, role, name="Test User"):
    """A user of `role`, and their headers -- made directly, not by
    registering and logging in. Those hash a password with bcrypt each time,
    and a test that needs four people would spend its whole time on it. The
    token is the one /auth/login would have issued."""
    user = User(
        name=name, email=f"user{next(_emails)}@example.com", password_hash="x", role=role.value
    )
    db_session.add(user)
    db_session.commit()
    return user, {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}


def _world(client, db_session, needed=5, status=EventStatus.event_approved, **event_overrides):
    """An approved, dated event whose Coordinator needs `needed` Audio items,
    a catalogue with two Audio items and a projector, and Technical Support."""
    organiser, organiser_headers = _user(client, db_session, Role.ORGANISER, name="Organiser")
    coordinator, headers = _user(client, db_session, Role.COORDINATOR, name="Coordinator")
    _, tech = _user(client, db_session, Role.TECH_SUPPORT, name="Tech Support")
    mic = _equipment(db_session, "Shure BLX24", category="Audio")
    pa = _equipment(db_session, "Yamaha PA", category="Audio")
    projector = _equipment(db_session, "Epson EB-L200SW", category="Projection")
    event = _event(
        db_session, organiser, coordinator, status=status,
        proposed_start=event_overrides.pop("proposed_start", START),
        proposed_end=event_overrides.pop("proposed_end", END),
        **event_overrides,
    )
    requirement = _added(client, headers, event.id, category="Audio", quantity_needed=needed)
    return SimpleNamespace(
        organiser=organiser, organiser_headers=organiser_headers, coordinator=coordinator, headers=headers, tech=tech,
        mic=mic, pa=pa, projector=projector, event=event, requirement=requirement,
        rid=requirement["id"],
    )


def _reserve(client, headers, requirement_id, equipment_id, quantity=None):
    body = {"equipment_id": equipment_id}
    if quantity is not None:
        body["quantity"] = quantity
    return client.post(
        f"/equipment-requirements/{requirement_id}/reservations", json=body, headers=headers
    )


def _reserved(client, headers, requirement_id, equipment_id, quantity=None) -> dict:
    res = _reserve(client, headers, requirement_id, equipment_id, quantity)
    assert res.status_code == 200, res.text
    return res.json()


def _update(client, headers, requirement_id, **body):
    return client.patch(
        f"/equipment-requirements/support/requirements/{requirement_id}", json=body, headers=headers
    )


def _as_coordinator(client, w):
    """What the Coordinator's event record reads."""
    res = client.get(f"/equipment-requirements/events/{w.event.id}", headers=w.headers)
    assert res.status_code == 200
    return {r["id"]: r for r in res.json()}[w.rid]


def _as_support(client, w):
    res = client.get(f"/equipment-requirements/support/events/{w.event.id}", headers=w.tech)
    assert res.status_code == 200, res.text
    return {r["id"]: r for r in res.json()["requirements"]}[w.rid]


def _lines(db_session, event):
    db_session.expire_all()
    return db_session.query(EquipmentRequest).filter_by(event_id=event.id).all()


def _links(db_session):
    db_session.expire_all()
    return db_session.query(RequirementReservationLink).all()


def _flagged(res) -> set[str]:
    return {item["loc"][-1] for item in res.json()["detail"]}


# ---------------------------------------------------------------------------
# Reserving, through Ercong's reservation
# ---------------------------------------------------------------------------


def test_ur_ac1_reserving_a_requirement_fulfils_it_through_ercongs_reservation(client, db_session):
    w = _world(client, db_session, needed=4)

    body = _reserved(client, w.tech, w.rid, w.mic.id)

    assert body["status"] == "reserved"
    assert body["reserved_quantity"] == 4
    assert body["reservations"] == [
        {"equipment_id": w.mic.id, "equipment_name": "Shure BLX24", "quantity": 4, "placement_notes": None}
    ]
    # The reservation is his: a reserved equipment_requests row, with who and when.
    (line,) = _lines(db_session, w.event)
    assert line.status is EquipmentStatus.reserved and line.quantity_requested == 4
    assert line.reviewed_by is not None and line.reviewed_at is not None


def test_ur_ac1_his_own_endpoints_see_the_reservation(client, db_session):
    """Made through the requirement, visible on his page: one reservation,
    not two copies of one."""
    w = _world(client, db_session, needed=4)
    _reserved(client, w.tech, w.rid, w.mic.id)

    listed = client.get(f"/equipment-reservations?event_id={w.event.id}", headers=w.tech).json()
    assert [(r["equipment_name"], r["quantity"]) for r in listed] == [("Shure BLX24", 4)]


def test_ur_ac1_the_reservation_reduces_what_an_overlapping_event_can_have(client, db_session):
    """His availability rule, applied to a reservation made through a
    requirement: 10 owned, 4 reserved here, so 6 are free for another event
    in the same window."""
    w = _world(client, db_session, needed=4)
    _reserved(client, w.tech, w.rid, w.mic.id)

    res = client.get(
        "/equipment-reservations/availability",
        params={"equipment_id": w.mic.id, "start": START.isoformat(), "end": END.isoformat()},
        headers=w.tech,
    )

    assert res.json()["available_quantity"] == 6


def test_ur_ac1_part_of_a_requirement_can_be_reserved_and_shows_its_progress(client, db_session):
    w = _world(client, db_session, needed=5)

    body = _reserved(client, w.tech, w.rid, w.mic.id, quantity=3)

    assert body["quantity_needed"] == 5  # what is needed is not overwritten
    assert body["reserved_quantity"] == 3
    # Still waiting for Technical Support to finish it, so still Requested: the
    # DoD has no "in progress", and the progress is the reserved figure.
    assert body["status"] == "requested"


def test_ur_ac1_the_rest_can_be_reserved_from_another_item(client, db_session):
    w = _world(client, db_session, needed=5)
    _reserved(client, w.tech, w.rid, w.mic.id, quantity=3)

    body = _reserved(client, w.tech, w.rid, w.pa.id, quantity=2)

    assert body["reserved_quantity"] == 5 and body["status"] == "reserved"
    assert {r["equipment_name"]: r["quantity"] for r in body["reservations"]} == {
        "Shure BLX24": 3, "Yamaha PA": 2,
    }


def test_ur_ac1_a_quantity_left_out_reserves_what_is_still_needed(client, db_session):
    w = _world(client, db_session, needed=5)
    _reserved(client, w.tech, w.rid, w.mic.id, quantity=3)

    body = _reserved(client, w.tech, w.rid, w.pa.id)

    assert body["reservations"][-1]["quantity"] == 2
    assert body["status"] == "reserved"


def test_ur_ac1_an_item_the_organiser_asked_for_is_reserved_at_their_quantity(client, db_session):
    """His rule, kept: the Organiser's line is reserved whole. That is 4,
    and the requirement needs 6, so it is part of the way there."""
    w = _world(client, db_session, needed=6)
    _organiser_line(db_session, w.event, w.mic, quantity=4)

    body = _reserved(client, w.tech, w.rid, w.mic.id)

    assert body["reserved_quantity"] == 4 and body["status"] == "requested"
    (line,) = _lines(db_session, w.event)
    assert line.status is EquipmentStatus.reserved  # the Organiser's own line, moved on


def test_ur_ac1_a_reservation_that_would_over_fill_the_requirement_is_refused(client, db_session):
    """Needs 2; the Organiser's line is 4 and his rule will not take less.
    Reserving would commit 4 against a need of 2, with no way to give any
    back, so it is refused -- and nothing is reserved."""
    w = _world(client, db_session, needed=2)
    _organiser_line(db_session, w.event, w.mic, quantity=4)

    res = _reserve(client, w.tech, w.rid, w.mic.id)

    assert res.status_code == 409
    assert "4" in res.json()["detail"] and "2" in res.json()["detail"]
    (line,) = _lines(db_session, w.event)
    assert line.status is EquipmentStatus.requested
    assert _links(db_session) == []


def test_ur_ac1_more_than_is_still_needed_is_refused(client, db_session):
    w = _world(client, db_session, needed=4)

    res = _reserve(client, w.tech, w.rid, w.mic.id, quantity=5)

    assert res.status_code == 409
    assert _lines(db_session, w.event) == [] and _links(db_session) == []


def test_ur_ac1_an_item_of_another_type_is_refused(client, db_session):
    w = _world(client, db_session)

    res = _reserve(client, w.tech, w.rid, w.projector.id, quantity=1)

    assert res.status_code == 422
    assert _flagged(res) == {"equipment_id"}
    assert _lines(db_session, w.event) == []


def test_ur_ac1_an_unknown_item_is_refused(client, db_session):
    w = _world(client, db_session)

    assert _reserve(client, w.tech, w.rid, 99999, quantity=1).status_code == 422


def test_ur_ac1_his_stock_check_is_what_refuses_an_unavailable_quantity(client, db_session):
    """Ercong's availability rule, not a copy of it: 3 owned, 4 needed, and
    his own message comes back -- his words, his status."""
    w = _world(client, db_session, needed=4)
    scarce = _equipment(db_session, "Scarce mic", category="Audio", total_quantity=3)

    res = _reserve(client, w.tech, w.rid, scarce.id, quantity=4)

    assert res.status_code == 409
    assert res.json()["detail"] == (
        "Only 3 Scarce mic available for this event's date and time; 4 requested."
    )
    assert _lines(db_session, w.event) == [] and _links(db_session) == []
    # The link was added before his function ran; it must not be left pending
    # for the next request's commit to write.
    assert not db_session.new


def test_ur_ac1_stock_held_by_an_overlapping_event_is_not_reserved_again(client, db_session):
    """Overlap protection is his, and works through a requirement too."""
    w = _world(client, db_session, needed=8)
    other_event = _event(
        db_session, w.organiser, w.coordinator, proposed_start=START, proposed_end=END, name="Other"
    )
    db_session.add(
        EquipmentRequest(
            event_id=other_event.id, equipment_id=w.mic.id, quantity_requested=5,
            status=EquipmentStatus.reserved,
        )
    )
    db_session.commit()

    res = _reserve(client, w.tech, w.rid, w.mic.id, quantity=8)  # 10 owned, 5 held

    assert res.status_code == 409
    assert "Only 5" in res.json()["detail"]


def test_ur_ac1_the_same_item_cannot_fulfil_two_requirements_of_one_event(client, db_session):
    w = _world(client, db_session, needed=4)
    second = _added(client, w.headers, w.event.id, category="Audio", quantity_needed=3)
    _reserved(client, w.tech, w.rid, w.mic.id, quantity=4)

    res = _reserve(client, w.tech, second["id"], w.mic.id, quantity=3)

    assert res.status_code == 409  # his "already reserved" or ours; either way, refused
    assert len(_links(db_session)) == 1


def test_ur_ac1_an_event_with_no_date_cannot_have_equipment_reserved(client, db_session):
    w = _world(client, db_session)
    w.event.proposed_start = w.event.proposed_end = None
    db_session.commit()

    res = _reserve(client, w.tech, w.rid, w.mic.id, quantity=1)

    assert res.status_code == 409
    assert "date and time" in res.json()["detail"]


def test_ur_ac1_reserving_after_the_organiser_replaced_their_lines_works_again(client, db_session):
    """An approved Organiser change deletes and rebuilds the event's
    equipment_requests rows -- reserved ones with them. The requirement
    follows the reservations, not a stored copy: it drops back, and the same
    item can be reserved again."""
    w = _world(client, db_session, needed=4)
    _reserved(client, w.tech, w.rid, w.mic.id)

    replace_equipment_lines(db_session, db_session.get(Event, w.event.id), [])
    db_session.commit()

    assert _as_support(client, w)["reserved_quantity"] == 0
    assert _as_support(client, w)["status"] == "requested"
    again = _reserved(client, w.tech, w.rid, w.mic.id)
    assert again["status"] == "reserved"
    assert len(_links(db_session)) == 1  # the surviving link was reused


def test_ur_ac1_reserving_clears_an_unavailable_outcome_and_its_reason(client, db_session):
    w = _world(client, db_session, needed=4)
    assert _update(client, w.tech, w.rid, status="unavailable", reason="Mics damaged").status_code == 200

    body = _reserved(client, w.tech, w.rid, w.mic.id, quantity=2)

    assert body["status"] == "requested" and body["unavailable_reason"] is None
    row = db_session.get(CoordinatorEquipmentRequirement, w.rid)
    db_session.refresh(row)
    assert row.status is EquipmentStatus.requested and row.unavailable_reason is None


@pytest.mark.parametrize("role", [Role.COORDINATOR, Role.ORGANISER, Role.VENUE_STAFF, Role.ATTENDEE])
def test_ur_only_technical_support_can_reserve(client, db_session, role):
    w = _world(client, db_session)
    _, headers = _user(client, db_session, role)

    assert _reserve(client, headers, w.rid, w.mic.id, quantity=1).status_code == 403
    assert _lines(db_session, w.event) == []


def test_ur_an_anonymous_caller_cannot_reserve(client, db_session):
    w = _world(client, db_session)

    res = client.post(
        f"/equipment-requirements/{w.rid}/reservations", json={"equipment_id": w.mic.id}
    )

    assert res.status_code == 401


@pytest.mark.parametrize("status", INACTIVE)
def test_ur_a_requirement_outside_the_window_cannot_be_reserved(client, db_session, status):
    w = _world(client, db_session)
    w.event.status = status
    db_session.commit()

    assert _reserve(client, w.tech, w.rid, w.mic.id, quantity=1).status_code == 404


def test_ur_reserving_an_unknown_requirement_is_not_found(client, db_session):
    w = _world(client, db_session)

    assert _reserve(client, w.tech, 99999, w.mic.id, quantity=1).status_code == 404


# ---------------------------------------------------------------------------
# UR AC1 -- update the status
# ---------------------------------------------------------------------------


def test_ur_ac1_technical_support_can_mark_a_requirement_unavailable_with_a_reason(client, db_session):
    w = _world(client, db_session)

    res = _update(client, w.tech, w.rid, status="unavailable", reason="Not enough stock: 2 are damaged")

    assert res.status_code == 200
    assert res.json()["status"] == "unavailable"
    assert res.json()["unavailable_reason"] == "Not enough stock: 2 are damaged"


def test_ur_ac1_unavailable_is_stored_as_the_existing_rejected_value(client, db_session):
    """Nothing is added to the shared enum: Unavailable is how this feature
    names `rejected`, in the API and on screen."""
    w = _world(client, db_session)
    _update(client, w.tech, w.rid, status="unavailable", reason="Under maintenance")

    row = db_session.get(CoordinatorEquipmentRequirement, w.rid)
    db_session.refresh(row)
    assert row.status is EquipmentStatus.rejected
    assert row.unavailable_reason == "Under maintenance"


@pytest.mark.parametrize("reason", [None, "", "   "], ids=["none", "empty", "spaces"])
def test_ur_ac1_unavailable_needs_a_reason(client, db_session, reason):
    """DoD 11b: Unavailable -- reason required."""
    w = _world(client, db_session)
    body = {"status": "unavailable"} if reason is None else {"status": "unavailable", "reason": reason}

    res = _update(client, w.tech, w.rid, **body)

    assert res.status_code == 422
    assert _flagged(res) == {"reason"}
    assert _as_support(client, w)["status"] == "requested"
    assert not db_session.query(EventStatusHistory).count()


def test_ur_ac1_the_reason_is_shown_to_the_coordinator(client, db_session):
    w = _world(client, db_session)

    _update(client, w.tech, w.rid, status="unavailable", reason="Damaged in the last event")

    seen = _as_coordinator(client, w)
    assert seen["status"] == "unavailable" and seen["unavailable_reason"] == "Damaged in the last event"


def test_ur_ac1_going_back_to_requested_drops_the_reason(client, db_session):
    w = _world(client, db_session)
    _update(client, w.tech, w.rid, status="unavailable", reason="Damaged")

    body = _update(client, w.tech, w.rid, status="requested").json()

    assert body["status"] == "requested" and body["unavailable_reason"] is None


def test_ur_ac1_a_reason_sent_with_requested_is_not_kept(client, db_session):
    w = _world(client, db_session)

    body = _update(client, w.tech, w.rid, status="requested", reason="not a reason for this").json()

    assert body["unavailable_reason"] is None


@pytest.mark.parametrize("status", ["reserved", "available"])
def test_ur_ac1_reserved_and_available_cannot_be_set_by_hand(client, db_session, status):
    """Reserved has to be backed by a real reservation, and Available by one
    that was freed, so neither can be chosen."""
    w = _world(client, db_session)

    res = _update(client, w.tech, w.rid, status=status)

    assert res.status_code == 422
    assert _flagged(res) == {"status"}
    assert _as_support(client, w)["status"] == "requested"


@pytest.mark.parametrize("status", ["reviewing", "rejected", "cancelled", "on_the_truck"])
def test_ur_ac1_only_the_definition_of_done_statuses_are_accepted(client, db_session, status):
    """The DoD's names, and no others: the stored values `reviewing` and
    `rejected` are not part of this feature's vocabulary."""
    w = _world(client, db_session)

    res = _update(client, w.tech, w.rid, status=status)

    assert res.status_code == 422
    assert _flagged(res) == {"status"}


def test_ur_ac1_unavailable_cannot_be_set_once_something_is_reserved(client, db_session):
    w = _world(client, db_session, needed=5)
    _reserved(client, w.tech, w.rid, w.mic.id, quantity=2)

    res = _update(client, w.tech, w.rid, status="unavailable", reason="Changed my mind")

    assert res.status_code == 409
    assert _as_support(client, w)["status"] == "requested"


def test_ur_ac1_a_status_set_by_hand_does_not_hide_what_is_reserved(client, db_session):
    """Requested on a part-reserved requirement is what it already is."""
    w = _world(client, db_session, needed=5)
    _reserved(client, w.tech, w.rid, w.mic.id, quantity=2)

    body = _update(client, w.tech, w.rid, status="requested").json()

    assert body["status"] == "requested" and body["reserved_quantity"] == 2


def test_ur_ac1_a_stored_in_review_value_from_before_is_read_as_requested(client, db_session):
    """Rows saved while "In review" was a choice read as Requested now."""
    w = _world(client, db_session)
    row = db_session.get(CoordinatorEquipmentRequirement, w.rid)
    row.status = EquipmentStatus.reviewing
    db_session.commit()

    assert _as_support(client, w)["status"] == "requested"
    assert _as_coordinator(client, w)["status"] == "requested"


# ---------------------------------------------------------------------------
# UR AC2 -- update the quantity
# ---------------------------------------------------------------------------


def test_ur_ac2_technical_support_can_change_the_quantity_needed(client, db_session):
    w = _world(client, db_session, needed=5)

    res = _update(client, w.tech, w.rid, quantity_needed=8)

    assert res.status_code == 200 and res.json()["quantity_needed"] == 8
    assert _as_support(client, w)["quantity_needed"] == 8


def test_ur_ac2_raising_the_quantity_reopens_a_fully_reserved_requirement(client, db_session):
    w = _world(client, db_session, needed=4)
    _reserved(client, w.tech, w.rid, w.mic.id)

    body = _update(client, w.tech, w.rid, quantity_needed=6).json()

    # DoD 11b: "If the required quantity rises above the reserved quantity,
    # the status returns to Requested."
    assert body["status"] == "requested"
    assert body["reserved_quantity"] == 4  # the reservation is untouched


def test_ur_ac2_the_quantity_needed_cannot_go_below_what_is_reserved(client, db_session):
    w = _world(client, db_session, needed=5)
    _reserved(client, w.tech, w.rid, w.mic.id, quantity=4)

    res = _update(client, w.tech, w.rid, quantity_needed=3)

    assert res.status_code == 409
    assert _flagged(res) == {"quantity_needed"}
    assert _as_support(client, w)["quantity_needed"] == 5


def test_ur_ac2_the_quantity_needed_can_drop_to_exactly_what_is_reserved(client, db_session):
    w = _world(client, db_session, needed=5)
    _reserved(client, w.tech, w.rid, w.mic.id, quantity=4)

    body = _update(client, w.tech, w.rid, quantity_needed=4).json()

    assert body["status"] == "reserved"


@pytest.mark.parametrize("quantity", [0, -3])
def test_ur_ac2_a_quantity_below_one_is_refused(client, db_session, quantity):
    w = _world(client, db_session)

    res = _update(client, w.tech, w.rid, quantity_needed=quantity)

    assert res.status_code == 422 and _flagged(res) == {"quantity_needed"}


def test_ur_ac2_reserving_never_changes_the_quantity_needed(client, db_session):
    """5 needed / 3 reserved is a valid, distinguishable state."""
    w = _world(client, db_session, needed=5)

    _reserved(client, w.tech, w.rid, w.mic.id, quantity=3)

    db_session.expire_all()
    assert db_session.get(CoordinatorEquipmentRequirement, w.rid).quantity_needed == 5


def test_ur_ac2_only_status_and_quantity_can_be_updated_by_technical_support(client, db_session):
    """The type and the notes are the Coordinator's. A category sent anyway
    is ignored, not applied."""
    w = _world(client, db_session)

    res = _update(client, w.tech, w.rid, quantity_needed=7, category="Projection", technical_notes="x")

    assert res.status_code == 200
    body = _as_support(client, w)
    assert body["category"] == "Audio" and body["technical_notes"] is None


def test_ur_an_empty_update_changes_nothing(client, db_session):
    w = _world(client, db_session, needed=5)

    res = _update(client, w.tech, w.rid)

    assert res.status_code == 200 and res.json()["quantity_needed"] == 5


@pytest.mark.parametrize("role", [Role.COORDINATOR, Role.ORGANISER, Role.VENUE_STAFF, Role.ATTENDEE])
def test_ur_only_technical_support_can_update_a_requirement(client, db_session, role):
    w = _world(client, db_session)
    _, headers = _user(client, db_session, role)

    assert _update(client, headers, w.rid, quantity_needed=9).status_code == 403
    assert _as_support(client, w)["quantity_needed"] == 5


def test_ur_an_anonymous_caller_cannot_update_a_requirement(client, db_session):
    w = _world(client, db_session)

    res = client.patch(
        f"/equipment-requirements/support/requirements/{w.rid}", json={"quantity_needed": 9}
    )

    assert res.status_code == 401


@pytest.mark.parametrize("status", INACTIVE)
def test_ur_a_requirement_outside_the_window_cannot_be_updated(client, db_session, status):
    w = _world(client, db_session)
    w.event.status = status
    db_session.commit()

    assert _update(client, w.tech, w.rid, quantity_needed=9).status_code == 404


def test_ur_updating_an_unknown_requirement_is_not_found(client, db_session):
    w = _world(client, db_session)

    assert _update(client, w.tech, 99999, quantity_needed=9).status_code == 404


# ---------------------------------------------------------------------------
# UR AC3 -- visible to the Coordinator on the event record
# ---------------------------------------------------------------------------


def test_ur_ac3_a_status_set_by_technical_support_is_visible_to_the_coordinator(client, db_session):
    w = _world(client, db_session)

    _update(client, w.tech, w.rid, status="unavailable", reason="Damaged")

    assert _as_coordinator(client, w)["status"] == "unavailable"


def test_ur_ac3_a_quantity_changed_by_technical_support_is_visible_to_the_coordinator(client, db_session):
    w = _world(client, db_session, needed=5)

    _update(client, w.tech, w.rid, quantity_needed=8)

    assert _as_coordinator(client, w)["quantity_needed"] == 8


def test_ur_ac3_the_coordinator_sees_what_is_reserved_and_how_far_it_has_got(client, db_session):
    w = _world(client, db_session, needed=5)
    _reserved(client, w.tech, w.rid, w.mic.id, quantity=3)

    seen = _as_coordinator(client, w)

    assert seen["status"] == "requested"  # waiting for the other 2
    assert seen["quantity_needed"] == 5 and seen["reserved_quantity"] == 3
    assert seen["reservations"] == [
        {"equipment_id": w.mic.id, "equipment_name": "Shure BLX24", "quantity": 3, "placement_notes": None}
    ]


def test_ur_ac3_a_fully_reserved_requirement_reads_reserved_to_the_coordinator(client, db_session):
    w = _world(client, db_session, needed=4)
    _reserved(client, w.tech, w.rid, w.mic.id)

    assert _as_coordinator(client, w)["status"] == "reserved"


def test_ur_ac3_technical_support_and_the_coordinator_read_the_same_progress(client, db_session):
    w = _world(client, db_session, needed=5)
    _reserved(client, w.tech, w.rid, w.mic.id, quantity=3)

    support, coordinator = _as_support(client, w), _as_coordinator(client, w)

    for field in ("status", "quantity_needed", "reserved_quantity", "reservations"):
        assert support[field] == coordinator[field]


def test_ur_ac3_the_requirement_stays_listed_after_it_is_added_with_no_reservation(client, db_session):
    """A new requirement reads as before: requested, nothing reserved."""
    w = _world(client, db_session)

    seen = _as_coordinator(client, w)

    assert seen["status"] == "requested"
    assert seen["reserved_quantity"] == 0 and seen["reservations"] == []


def test_ur_ac3_technical_support_sees_what_is_reserved_without_the_coordinators_bookkeeping(client, db_session):
    """Still no author and no link to the Organiser's pick -- progress is
    added, nothing of the Coordinator's own is."""
    w = _world(client, db_session)

    assert set(_as_support(client, w)) == {
        "id", "category", "quantity_needed", "technical_notes", "status",
        "reserved_quantity", "released_quantity", "unavailable_reason", "reservations",
    }


def test_ur_the_organiser_still_never_receives_requirements_or_their_progress(client, db_session):
    w = _world(client, db_session, needed=4)
    _reserved(client, w.tech, w.rid, w.mic.id)

    for path in (f"/equipment-requirements/events/{w.event.id}",
                 f"/equipment-requirements/support/events/{w.event.id}"):
        assert client.get(path, headers=w.organiser_headers).status_code == 403


# ---------------------------------------------------------------------------
# What the Coordinator may still do once something is reserved
# ---------------------------------------------------------------------------


def _edit(client, w, **body):
    return client.patch(f"/equipment-requirements/{w.rid}", json=body, headers=w.headers)


def test_ur_a_requirement_with_a_reservation_cannot_be_deleted(client, db_session):
    """There is no way to release a reservation, so deleting the requirement
    would leave stock held for a need that no longer exists."""
    w = _world(client, db_session, needed=4)
    _reserved(client, w.tech, w.rid, w.mic.id)

    res = client.delete(f"/equipment-requirements/{w.rid}", headers=w.headers)

    assert res.status_code == 409
    assert _as_coordinator(client, w)["reserved_quantity"] == 4


def test_ur_a_requirement_with_nothing_reserved_can_still_be_deleted(client, db_session):
    w = _world(client, db_session)

    assert client.delete(f"/equipment-requirements/{w.rid}", headers=w.headers).status_code == 204


def test_ur_a_requirement_whose_reservation_was_lost_can_be_deleted(client, db_session):
    """Reserved means reserved NOW. If the Organiser's change wiped the
    reservation, nothing is held, and nothing stops removal."""
    w = _world(client, db_session, needed=4)
    _reserved(client, w.tech, w.rid, w.mic.id)
    replace_equipment_lines(db_session, db_session.get(Event, w.event.id), [])
    db_session.commit()

    assert client.delete(f"/equipment-requirements/{w.rid}", headers=w.headers).status_code == 204


def test_ur_the_type_of_a_requirement_with_a_reservation_cannot_change(client, db_session):
    w = _world(client, db_session, needed=4)
    _reserved(client, w.tech, w.rid, w.mic.id)

    res = _edit(client, w, category="Projection")

    assert res.status_code == 409 and _flagged(res) == {"category"}
    assert _as_coordinator(client, w)["category"] == "Audio"


def test_ur_the_same_type_sent_again_is_not_a_change(client, db_session):
    """The edit form always sends all three fields."""
    w = _world(client, db_session, needed=4)
    _reserved(client, w.tech, w.rid, w.mic.id)

    res = _edit(client, w, category="audio", quantity_needed=4, technical_notes="Handheld")

    assert res.status_code == 200
    assert res.json()["technical_notes"] == "Handheld"


def test_ur_the_type_can_change_while_nothing_is_reserved(client, db_session):
    w = _world(client, db_session)

    assert _edit(client, w, category="Projection").status_code == 200


def test_ur_notes_can_change_once_something_is_reserved(client, db_session):
    w = _world(client, db_session, needed=4)
    _reserved(client, w.tech, w.rid, w.mic.id)

    res = _edit(client, w, technical_notes="Lapel clips as well")

    assert res.status_code == 200 and res.json()["technical_notes"] == "Lapel clips as well"


def test_ur_the_coordinator_cannot_drop_the_quantity_below_what_is_reserved(client, db_session):
    w = _world(client, db_session, needed=5)
    _reserved(client, w.tech, w.rid, w.mic.id, quantity=4)

    res = _edit(client, w, quantity_needed=3)

    assert res.status_code == 409 and _flagged(res) == {"quantity_needed"}
    assert _as_coordinator(client, w)["quantity_needed"] == 5


def test_ur_the_coordinator_can_set_the_quantity_to_what_is_reserved_or_more(client, db_session):
    w = _world(client, db_session, needed=5)
    _reserved(client, w.tech, w.rid, w.mic.id, quantity=4)

    assert _edit(client, w, quantity_needed=4).status_code == 200
    assert _edit(client, w, quantity_needed=9).status_code == 200


def test_ur_the_coordinators_responses_carry_the_progress(client, db_session):
    """Add and edit answer with the same shape as the list, so the card
    never has to refetch to show it."""
    w = _world(client, db_session, needed=4)
    _reserved(client, w.tech, w.rid, w.mic.id, quantity=3)

    edited = _edit(client, w, technical_notes="Handheld").json()

    assert edited["status"] == "requested" and edited["reserved_quantity"] == 3
    added = _added(client, w.headers, w.event.id)
    assert added["reserved_quantity"] == 0 and added["reservations"] == [] and added["status"] == "requested"


# ---------------------------------------------------------------------------
# Placement: where Technical Support will set the equipment up
# ---------------------------------------------------------------------------


def _reserve_with_placement(client, headers, requirement_id, equipment_id, placement, quantity=None):
    body = {"equipment_id": equipment_id, "placement_notes": placement}
    if quantity is not None:
        body["quantity"] = quantity
    return client.post(f"/equipment-requirements/{requirement_id}/reservations", json=body, headers=headers)


def test_ur_placement_is_recorded_on_the_reservation_and_shown_with_it(client, db_session):
    """Where the item will be set up at the venue -- recorded by Technical
    Support when they reserve, and read by the Safety Officer. It lives on the
    reservation (his field), which is why a requirement waiting to be reserved
    has none."""
    w = _world(client, db_session, needed=4)

    res = _reserve_with_placement(client, w.tech, w.rid, w.mic.id, "Stage left, by the lectern")

    assert res.status_code == 200, res.text
    assert res.json()["reservations"][0]["placement_notes"] == "Stage left, by the lectern"
    (line,) = _lines(db_session, w.event)
    assert line.placement_notes == "Stage left, by the lectern"


def test_ur_placement_is_the_same_one_his_reservation_page_and_the_safety_officer_read(client, db_session):
    w = _world(client, db_session, needed=4)
    _reserve_with_placement(client, w.tech, w.rid, w.mic.id, "Back of the hall")

    listed = client.get(f"/equipment-reservations?event_id={w.event.id}", headers=w.tech).json()

    assert [r["placement_notes"] for r in listed] == ["Back of the hall"]


def test_ur_placement_is_optional(client, db_session):
    w = _world(client, db_session, needed=4)

    body = _reserved(client, w.tech, w.rid, w.mic.id)

    assert body["reservations"][0]["placement_notes"] is None


@pytest.mark.parametrize("placement", ["", "   "])
def test_ur_a_blank_placement_is_none(client, db_session, placement):
    w = _world(client, db_session, needed=4)

    res = _reserve_with_placement(client, w.tech, w.rid, w.mic.id, placement)

    assert res.json()["reservations"][0]["placement_notes"] is None


def test_ur_placement_is_recorded_for_an_item_the_organiser_asked_for_too(client, db_session):
    w = _world(client, db_session, needed=6)
    _organiser_line(db_session, w.event, w.mic, quantity=4)

    res = _reserve_with_placement(client, w.tech, w.rid, w.mic.id, "Front row")

    (line,) = _lines(db_session, w.event)
    assert res.status_code == 200 and line.placement_notes == "Front row"


def test_ur_each_reserved_item_keeps_its_own_placement(client, db_session):
    w = _world(client, db_session, needed=5)
    _reserve_with_placement(client, w.tech, w.rid, w.mic.id, "Stage left", quantity=3)
    body = _reserve_with_placement(client, w.tech, w.rid, w.pa.id, "Rear", quantity=2).json()

    assert {r["equipment_name"]: r["placement_notes"] for r in body["reservations"]} == {
        "Shure BLX24": "Stage left", "Yamaha PA": "Rear",
    }


def test_ur_a_placement_that_is_too_long_is_refused_and_nothing_is_reserved(client, db_session):
    w = _world(client, db_session, needed=4)

    res = _reserve_with_placement(client, w.tech, w.rid, w.mic.id, "x" * 2001)

    assert res.status_code == 422
    assert _lines(db_session, w.event) == [] and _links(db_session) == []


def test_ur_a_requirement_waiting_to_be_reserved_has_no_placement_yet(client, db_session):
    w = _world(client, db_session)

    assert _as_support(client, w)["reservations"] == []


# ---------------------------------------------------------------------------
# Available: its reservation was freed
# ---------------------------------------------------------------------------


def _event_has_ended(db_session, w):
    """The event's end time passes. Reservations hold stock until then (his
    rule, and why a cancelled event frees nothing early)."""
    w.event.proposed_start = datetime(2020, 5, 1, 9, tzinfo=timezone.utc)
    w.event.proposed_end = datetime(2020, 5, 1, 17, tzinfo=timezone.utc)
    db_session.commit()


def test_ur_a_reservation_freed_when_the_event_ends_reads_available(client, db_session):
    w = _world(client, db_session, needed=4)
    _reserved(client, w.tech, w.rid, w.mic.id)
    assert _as_support(client, w)["status"] == "reserved"

    _event_has_ended(db_session, w)

    seen = _as_support(client, w)
    assert seen["status"] == "available"
    assert seen["reserved_quantity"] == 0  # it holds nothing now
    assert seen["released_quantity"] == 4  # what was freed


def test_ur_available_is_worked_out_not_stored(client, db_session):
    w = _world(client, db_session, needed=4)
    _reserved(client, w.tech, w.rid, w.mic.id)
    _event_has_ended(db_session, w)
    assert _as_support(client, w)["status"] == "available"

    row = db_session.get(CoordinatorEquipmentRequirement, w.rid)
    db_session.refresh(row)
    assert row.status is EquipmentStatus.requested


def test_ur_a_part_reserved_requirement_is_freed_too(client, db_session):
    w = _world(client, db_session, needed=5)
    _reserved(client, w.tech, w.rid, w.mic.id, quantity=3)

    _event_has_ended(db_session, w)

    seen = _as_coordinator(client, w)
    assert seen["status"] == "available" and seen["released_quantity"] == 3


def test_ur_the_coordinator_sees_available_on_the_event_record(client, db_session):
    w = _world(client, db_session, needed=4)
    _reserved(client, w.tech, w.rid, w.mic.id)

    _event_has_ended(db_session, w)

    assert _as_coordinator(client, w)["status"] == "available"


def test_ur_a_requirement_that_was_never_reserved_is_not_available(client, db_session):
    """Nothing was held, so nothing was freed."""
    w = _world(client, db_session)

    _event_has_ended(db_session, w)

    assert _as_support(client, w)["status"] == "requested"


def test_ur_an_unavailable_requirement_stays_unavailable_with_its_reason(client, db_session):
    w = _world(client, db_session)
    _update(client, w.tech, w.rid, status="unavailable", reason="Damaged")

    _event_has_ended(db_session, w)

    seen = _as_support(client, w)
    assert seen["status"] == "unavailable" and seen["unavailable_reason"] == "Damaged"


def test_ur_an_event_with_no_end_time_is_never_freed(client, db_session):
    w = _world(client, db_session, needed=4)
    _reserved(client, w.tech, w.rid, w.mic.id)
    w.event.proposed_start = w.event.proposed_end = None
    db_session.commit()

    assert _as_support(client, w)["status"] == "reserved"


def test_ur_an_event_still_to_come_keeps_its_reservation(client, db_session):
    w = _world(client, db_session, needed=4)
    _reserved(client, w.tech, w.rid, w.mic.id)

    assert _as_support(client, w)["status"] == "reserved"


def test_ur_nothing_can_be_reserved_or_updated_once_it_is_available(client, db_session):
    w = _world(client, db_session, needed=4)
    _reserved(client, w.tech, w.rid, w.mic.id)
    _event_has_ended(db_session, w)

    assert _reserve(client, w.tech, w.rid, w.pa.id, quantity=1).status_code == 409
    assert _update(client, w.tech, w.rid, quantity_needed=9).status_code == 409
    assert _update(client, w.tech, w.rid, status="unavailable", reason="x").status_code == 409
    assert _as_support(client, w)["quantity_needed"] == 4


def test_ur_a_freed_requirement_can_be_removed_and_retyped_by_the_coordinator(client, db_session):
    """It holds nothing any more, so the protections that stop equipment being
    orphaned no longer apply."""
    w = _world(client, db_session, needed=4)
    _reserved(client, w.tech, w.rid, w.mic.id)
    _event_has_ended(db_session, w)

    assert _edit(client, w, category="Projection").status_code == 200
    assert client.delete(f"/equipment-requirements/{w.rid}", headers=w.headers).status_code == 204


# ---------------------------------------------------------------------------
# The Activity Log (DoD 11: every status change, with who and when)
# ---------------------------------------------------------------------------


def _history(db_session, w):
    db_session.expire_all()
    return list(
        db_session.query(EventStatusHistory)
        .filter_by(event_id=w.event.id)
        .order_by(EventStatusHistory.id)
    )


def test_ur_marking_unavailable_is_logged_with_who_what_and_why(client, db_session):
    w = _world(client, db_session)

    _update(client, w.tech, w.rid, status="unavailable", reason="Under maintenance")

    [entry] = _history(db_session, w)
    assert entry.changed_by == w.tech.id
    assert entry.created_at is not None
    assert "Audio" in entry.note and "Requested" in entry.note and "Unavailable" in entry.note
    assert "Under maintenance" in entry.note


def test_ur_the_log_line_leaves_the_events_status_as_it_was(client, db_session):
    w = _world(client, db_session)

    _update(client, w.tech, w.rid, status="unavailable", reason="Damaged")

    [entry] = _history(db_session, w)
    assert entry.from_status == entry.to_status == EventStatus.event_approved


def test_ur_going_back_to_requested_is_logged(client, db_session):
    w = _world(client, db_session)
    _update(client, w.tech, w.rid, status="unavailable", reason="Damaged")

    _update(client, w.tech, w.rid, status="requested")

    notes = [h.note for h in _history(db_session, w)]
    assert len(notes) == 2
    assert "Unavailable" in notes[1] and "Requested" in notes[1]


def test_ur_fully_reserving_is_logged_as_reserved(client, db_session):
    w = _world(client, db_session, needed=4)

    _reserved(client, w.tech, w.rid, w.mic.id)

    [entry] = _history(db_session, w)
    assert entry.changed_by == w.tech.id
    assert "Requested" in entry.note and "Reserved" in entry.note


def test_ur_a_part_reservation_changes_no_status_so_is_not_logged(client, db_session):
    w = _world(client, db_session, needed=5)

    _reserved(client, w.tech, w.rid, w.mic.id, quantity=3)

    assert _history(db_session, w) == []


def test_ur_raising_the_quantity_over_what_is_reserved_is_logged_as_back_to_requested(client, db_session):
    w = _world(client, db_session, needed=4)
    _reserved(client, w.tech, w.rid, w.mic.id)

    _update(client, w.tech, w.rid, quantity_needed=6)

    notes = [h.note for h in _history(db_session, w)]
    assert len(notes) == 2
    assert "Reserved" in notes[1] and "Requested" in notes[1]


def test_ur_the_coordinator_raising_the_quantity_is_logged_too(client, db_session):
    w = _world(client, db_session, needed=4)
    _reserved(client, w.tech, w.rid, w.mic.id)

    assert _edit(client, w, quantity_needed=7).status_code == 200

    entries = _history(db_session, w)
    assert entries[-1].changed_by == w.coordinator.id
    assert "Reserved" in entries[-1].note and "Requested" in entries[-1].note


def test_ur_a_refused_update_is_not_logged(client, db_session):
    w = _world(client, db_session, needed=5)
    _reserved(client, w.tech, w.rid, w.mic.id, quantity=2)

    assert _update(client, w.tech, w.rid, status="unavailable", reason="No").status_code == 409
    assert _update(client, w.tech, w.rid, status="reserved").status_code == 422

    assert _history(db_session, w) == []


def test_ur_a_change_that_leaves_the_status_alone_is_not_logged(client, db_session):
    w = _world(client, db_session, needed=5)

    assert _update(client, w.tech, w.rid, quantity_needed=8).status_code == 200

    assert _history(db_session, w) == []
