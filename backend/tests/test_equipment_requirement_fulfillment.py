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

"Unavailable" is the stored `rejected`; "Reserved" is never stored, it is
what the reservations add up to.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.core.roles import Role
from app.models.enums import EquipmentStatus, EventStatus
from app.models.equipment import (
    CoordinatorEquipmentRequirement,
    EquipmentRequest,
    RequirementReservationLink,
)
from app.models.events import Event
from app.services.equipment_lines import replace_equipment_lines
from tests.test_equipment_requirements import (
    INACTIVE,
    _added,
    _equipment,
    _event,
    _organiser_line,
    _user,
)

START = datetime(2026, 11, 2, 9, tzinfo=timezone.utc)
END = datetime(2026, 11, 2, 17, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _world(client, db_session, needed=5, status=EventStatus.approved, **event_overrides):
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
        {"equipment_id": w.mic.id, "equipment_name": "Shure BLX24", "quantity": 4}
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
    assert body["status"] == "reviewing"  # in progress, not "reserved"


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

    assert body["reserved_quantity"] == 4 and body["status"] == "reviewing"
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


def test_ur_ac1_reserving_clears_an_unavailable_outcome(client, db_session):
    w = _world(client, db_session, needed=4)
    assert _update(client, w.tech, w.rid, status="rejected").status_code == 200

    body = _reserved(client, w.tech, w.rid, w.mic.id, quantity=2)

    assert body["status"] == "reviewing"


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


@pytest.mark.parametrize("status", ["requested", "reviewing", "rejected"])
def test_ur_ac1_technical_support_can_set_a_status_they_own(client, db_session, status):
    w = _world(client, db_session)

    res = _update(client, w.tech, w.rid, status=status)

    assert res.status_code == 200
    assert res.json()["status"] == status
    db_session.expire_all()
    assert db_session.get(CoordinatorEquipmentRequirement, w.rid).status.value == status


def test_ur_ac1_unavailable_is_the_stored_rejected_value(client, db_session):
    """No new value in the shared enum: Unavailable is how this feature
    shows `rejected`."""
    w = _world(client, db_session)
    _update(client, w.tech, w.rid, status="rejected")

    row = db_session.get(CoordinatorEquipmentRequirement, w.rid)
    db_session.refresh(row)
    assert row.status is EquipmentStatus.rejected


@pytest.mark.parametrize("status", ["reserved", "cancelled"])
def test_ur_ac1_reserved_and_cancelled_cannot_be_set_by_hand(client, db_session, status):
    """Reserved has to be backed by a real reservation, so it cannot be
    chosen."""
    w = _world(client, db_session)

    res = _update(client, w.tech, w.rid, status=status)

    assert res.status_code == 422
    assert _flagged(res) == {"status"}
    assert _as_support(client, w)["status"] == "requested"


def test_ur_ac1_an_unknown_status_is_refused(client, db_session):
    w = _world(client, db_session)

    assert _update(client, w.tech, w.rid, status="unavailable").status_code == 422


def test_ur_ac1_unavailable_cannot_be_set_once_something_is_reserved(client, db_session):
    w = _world(client, db_session, needed=5)
    _reserved(client, w.tech, w.rid, w.mic.id, quantity=2)

    res = _update(client, w.tech, w.rid, status="rejected")

    assert res.status_code == 409
    assert _as_support(client, w)["status"] == "reviewing"


def test_ur_ac1_a_status_set_by_hand_does_not_hide_what_is_reserved(client, db_session):
    """Setting Requested on a requirement that is part-reserved changes the
    stored value, not the truth: it still reads as in progress."""
    w = _world(client, db_session, needed=5)
    _reserved(client, w.tech, w.rid, w.mic.id, quantity=2)

    body = _update(client, w.tech, w.rid, status="requested").json()

    assert body["status"] == "reviewing" and body["reserved_quantity"] == 2


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

    assert body["status"] == "reviewing"
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

    _update(client, w.tech, w.rid, status="rejected")

    assert _as_coordinator(client, w)["status"] == "rejected"


def test_ur_ac3_a_quantity_changed_by_technical_support_is_visible_to_the_coordinator(client, db_session):
    w = _world(client, db_session, needed=5)

    _update(client, w.tech, w.rid, quantity_needed=8)

    assert _as_coordinator(client, w)["quantity_needed"] == 8


def test_ur_ac3_the_coordinator_sees_what_is_reserved_and_how_far_it_has_got(client, db_session):
    w = _world(client, db_session, needed=5)
    _reserved(client, w.tech, w.rid, w.mic.id, quantity=3)

    seen = _as_coordinator(client, w)

    assert seen["status"] == "reviewing"
    assert seen["quantity_needed"] == 5 and seen["reserved_quantity"] == 3
    assert seen["reservations"] == [
        {"equipment_id": w.mic.id, "equipment_name": "Shure BLX24", "quantity": 3}
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
        "reserved_quantity", "reservations",
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

    assert edited["status"] == "reviewing" and edited["reserved_quantity"] == 3
    added = _added(client, w.headers, w.event.id)
    assert added["reserved_quantity"] == 0 and added["reservations"] == [] and added["status"] == "requested"
