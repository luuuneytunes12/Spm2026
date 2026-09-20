"""Tests for structured equipment line-items on an event request.

    As an Event Organiser, I want to pick the equipment I need from
    ConnectSphere's catalogue and say how many of each, so that my request
    says exactly what I need instead of a sentence somebody has to
    interpret.

The lines live on the existing `equipment_requests` table, one row per
catalogue item. They are written at status `requested` -- Technical Support
decides later whether they can be reserved.

See docs/test-cases-organiser-event-equipment.md for the AC mapping.
"""

from app.core.roles import Role
from app.models.enums import EquipmentOperationalStatus, EquipmentStatus
from app.models.equipment import Equipment, EquipmentRequest
from app.models.user import User

# A request with every mandatory field filled in, so a test about equipment
# can reach the submit endpoint without tripping unrelated validation.
COMPLETE = {
    "name": "Regional Partner Conference",
    "purpose": "Annual partner briefing",
    "event_type": "conference",
    "proposed_start": "2026-11-02T09:00:00Z",
    "proposed_end": "2026-11-02T17:00:00Z",
    "expected_attendance": 120,
    "venue_requirements": "Main hall, stage, podium",
    "accessibility_needs": "Step-free access, hearing loop",
}


def _user(client, db_session, role, email, name="Test User"):
    """Register a user, promote them to `role`, and return auth headers.

    Registration always assigns `attendee` (by design -- a client can never
    pick its own role), so the role is set directly here. The re-login is
    what makes the returned token reflect the new role.
    """
    password = "password123"
    assert (
        client.post(
            "/auth/register", json={"name": name, "email": email, "password": password}
        ).status_code
        == 201
    )
    user = db_session.query(User).filter(User.email == email).one()
    user.role = role.value
    db_session.commit()

    token = client.post("/auth/login", json={"email": email, "password": password}).json()[
        "access_token"
    ]
    return user, {"Authorization": f"Bearer {token}"}


def _organiser(client, db_session, email="org@example.com"):
    return _user(client, db_session, Role.ORGANISER, email, name="Org User")


def _equipment(db_session, name, category="Audio", **overrides) -> Equipment:
    """Insert one catalogue item. There is no endpoint that creates
    equipment -- that is EQUIPMENT_MANAGE and a separate story."""
    item = Equipment(
        name=name,
        category=category,
        description=overrides.pop("description", "A description."),
        total_quantity=overrides.pop("total_quantity", 10),
        location=overrides.pop("location", "Marina Bay Facility"),
        operational_status=overrides.pop(
            "operational_status", EquipmentOperationalStatus.available
        ),
        **overrides,
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item


def _create(client, headers, **body):
    res = client.post("/events", json=body, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


# ---------------------------------------------------------------------------
# Creating a request with equipment lines
# ---------------------------------------------------------------------------


def test_a_draft_can_be_created_with_equipment_lines(client, db_session):
    """The Organiser picks items and quantities; both are stored."""
    _, headers = _organiser(client, db_session)
    mic = _equipment(db_session, "Shure BLX24")
    projector = _equipment(db_session, "Epson EB-L200SW", category="Projection")

    body = _create(
        client,
        headers,
        purpose="Annual briefing",
        equipment_items=[
            {"equipment_id": mic.id, "quantity_requested": 6},
            {"equipment_id": projector.id, "quantity_requested": 2},
        ],
    )

    lines = {line["equipment_id"]: line["quantity_requested"] for line in body["equipment_items"]}
    assert lines == {mic.id: 6, projector.id: 2}


def test_lines_carry_the_catalogue_name_and_type(client, db_session):
    """A line has to be readable without a second request to the catalogue."""
    _, headers = _organiser(client, db_session)
    mic = _equipment(db_session, "Shure BLX24 Handheld Microphone", category="Audio")

    body = _create(
        client, headers, equipment_items=[{"equipment_id": mic.id, "quantity_requested": 4}]
    )

    line = body["equipment_items"][0]
    assert line["equipment_name"] == "Shure BLX24 Handheld Microphone"
    assert line["equipment_category"] == "Audio"


def test_new_lines_start_as_requested_not_reserved(client, db_session):
    """Asking for equipment is not being granted it.

    This is what keeps the catalogue's availability honest: GET /equipment
    subtracts only `reserved` units, so an Organiser cannot reduce advertised
    stock simply by asking for it.
    """
    _, headers = _organiser(client, db_session)
    mic = _equipment(db_session, "Shure BLX24", total_quantity=10)

    _create(client, headers, equipment_items=[{"equipment_id": mic.id, "quantity_requested": 6}])

    row = db_session.query(EquipmentRequest).one()
    assert row.status == EquipmentStatus.requested
    assert row.reviewed_by is None and row.reviewed_at is None


def test_equipment_lines_do_not_reduce_catalogue_availability(client, db_session):
    """The end-to-end version of the test above, through the catalogue API."""
    _, org_headers = _organiser(client, db_session)
    _, tech_headers = _user(client, db_session, Role.TECH_SUPPORT, "tech@example.com")
    mic = _equipment(db_session, "Shure BLX24", total_quantity=10)

    _create(client, org_headers, equipment_items=[{"equipment_id": mic.id, "quantity_requested": 6}])

    item = client.get("/equipment", headers=tech_headers).json()["items"][0]
    assert item["available_quantity"] == 10


def test_a_request_without_equipment_reports_an_empty_list(client, db_session):
    """Empty rather than absent -- not every event needs equipment, and the
    client should not have to handle a missing key."""
    _, headers = _organiser(client, db_session)

    body = _create(client, headers, purpose="A talk, nothing more")

    assert body["equipment_items"] == []


# ---------------------------------------------------------------------------
# Editing the lines on a draft
# ---------------------------------------------------------------------------


def test_patching_equipment_lines_replaces_them(client, db_session):
    """The form always sends the full current list, so a PATCH is a replace."""
    _, headers = _organiser(client, db_session)
    mic = _equipment(db_session, "Shure BLX24")
    projector = _equipment(db_session, "Epson EB-L200SW", category="Projection")
    event_id = _create(
        client, headers, equipment_items=[{"equipment_id": mic.id, "quantity_requested": 6}]
    )["id"]

    body = client.patch(
        f"/events/{event_id}",
        json={"equipment_items": [{"equipment_id": projector.id, "quantity_requested": 2}]},
        headers=headers,
    ).json()

    assert [line["equipment_id"] for line in body["equipment_items"]] == [projector.id]
    # The replaced row is gone, not orphaned.
    assert db_session.query(EquipmentRequest).count() == 1


def test_changing_the_quantity_of_an_existing_line_works(client, db_session):
    """Replacing a line with the SAME item at a different quantity.

    The obvious edit -- "actually make that 3" -- and the one that breaks
    if the replace inserts before it deletes: both rows carry the same
    (event_id, equipment_id), so the new INSERT collides with the old row
    that has not been removed yet.
    """
    _, headers = _organiser(client, db_session)
    mic = _equipment(db_session, "Shure BLX24")
    projector = _equipment(db_session, "Epson EB-L200SW", category="Projection")
    event_id = _create(
        client, headers, equipment_items=[{"equipment_id": mic.id, "quantity_requested": 1}]
    )["id"]

    res = client.patch(
        f"/events/{event_id}",
        json={
            "equipment_items": [
                {"equipment_id": mic.id, "quantity_requested": 3},
                {"equipment_id": projector.id, "quantity_requested": 2},
            ]
        },
        headers=headers,
    )

    assert res.status_code == 200, res.text
    lines = {
        line["equipment_id"]: line["quantity_requested"] for line in res.json()["equipment_items"]
    }
    assert lines == {mic.id: 3, projector.id: 2}


def test_patch_omitting_equipment_does_not_clear_it(client, db_session):
    """Consistent with every other field: omitted means "leave alone"."""
    _, headers = _organiser(client, db_session)
    mic = _equipment(db_session, "Shure BLX24")
    event_id = _create(
        client,
        headers,
        purpose="Annual briefing",
        equipment_items=[{"equipment_id": mic.id, "quantity_requested": 6}],
    )["id"]

    body = client.patch(f"/events/{event_id}", json={"name": "Renamed"}, headers=headers).json()

    assert body["name"] == "Renamed"
    assert [line["equipment_id"] for line in body["equipment_items"]] == [mic.id]


def test_patching_an_empty_list_clears_the_lines(client, db_session):
    """Removing the last row on the form has to be expressible."""
    _, headers = _organiser(client, db_session)
    mic = _equipment(db_session, "Shure BLX24")
    event_id = _create(
        client, headers, equipment_items=[{"equipment_id": mic.id, "quantity_requested": 6}]
    )["id"]

    body = client.patch(
        f"/events/{event_id}", json={"equipment_items": []}, headers=headers
    ).json()

    assert body["equipment_items"] == []
    assert db_session.query(EquipmentRequest).count() == 0


def test_equipment_lines_survive_a_reopen(client, db_session):
    """The draft story, applied to equipment: save, come back, still there."""
    _, headers = _organiser(client, db_session)
    mic = _equipment(db_session, "Shure BLX24")
    event_id = _create(
        client, headers, equipment_items=[{"equipment_id": mic.id, "quantity_requested": 6}]
    )["id"]

    body = client.get(f"/events/{event_id}", headers=headers).json()

    assert body["equipment_items"][0]["quantity_requested"] == 6


# ---------------------------------------------------------------------------
# Validation -- every one of these must be a clean 422, never a 500
# ---------------------------------------------------------------------------


def test_the_same_item_twice_is_rejected(client, db_session):
    """Quantity is how you ask for more, so two lines for one item is a
    mistake. Rejected in the API before the unique constraint has to."""
    _, headers = _organiser(client, db_session)
    mic = _equipment(db_session, "Shure BLX24")

    res = client.post(
        "/events",
        json={
            "equipment_items": [
                {"equipment_id": mic.id, "quantity_requested": 2},
                {"equipment_id": mic.id, "quantity_requested": 3},
            ]
        },
        headers=headers,
    )

    assert res.status_code == 422
    assert {item["loc"][-1] for item in res.json()["detail"]} == {"equipment_items"}


def test_an_unknown_equipment_id_is_rejected_cleanly(client, db_session):
    """equipment_id is ON DELETE RESTRICT, so an unknown id would otherwise
    surface as an IntegrityError and a 500."""
    _, headers = _organiser(client, db_session)

    res = client.post(
        "/events",
        json={"equipment_items": [{"equipment_id": 9999, "quantity_requested": 1}]},
        headers=headers,
    )

    assert res.status_code == 422
    assert {item["loc"][-1] for item in res.json()["detail"]} == {"equipment_items"}


def test_a_retired_item_cannot_be_requested(client, db_session):
    """Retired means permanently withdrawn -- a request for one could never
    be fulfilled, so it is refused rather than left for Technical Support."""
    _, headers = _organiser(client, db_session)
    old = _equipment(
        db_session,
        "Panasonic PT-VW360",
        category="Projection",
        operational_status=EquipmentOperationalStatus.retired,
    )

    res = client.post(
        "/events",
        json={"equipment_items": [{"equipment_id": old.id, "quantity_requested": 1}]},
        headers=headers,
    )

    assert res.status_code == 422


def test_a_damaged_item_can_still_be_requested(client, db_session):
    """Repairs finish, and the event may be months away. Whether the kit can
    actually be provided is Technical Support's call, not the form's."""
    _, headers = _organiser(client, db_session)
    broken = _equipment(
        db_session, "Behringer X32", operational_status=EquipmentOperationalStatus.damaged
    )

    body = _create(
        client, headers, equipment_items=[{"equipment_id": broken.id, "quantity_requested": 1}]
    )

    assert body["equipment_items"][0]["equipment_id"] == broken.id


def test_a_quantity_of_zero_is_rejected_cleanly(client, db_session):
    """Mirrors the database CHECK (quantity_requested > 0)."""
    _, headers = _organiser(client, db_session)
    mic = _equipment(db_session, "Shure BLX24")

    res = client.post(
        "/events",
        json={"equipment_items": [{"equipment_id": mic.id, "quantity_requested": 0}]},
        headers=headers,
    )

    assert res.status_code == 422


def test_asking_for_more_than_exists_is_accepted(client, db_session):
    """Deliberate: the briefing makes judging sufficiency Technical Support's
    job, and stock can change between request and event."""
    _, headers = _organiser(client, db_session)
    projector = _equipment(db_session, "Epson EB-L200SW", category="Projection", total_quantity=6)

    body = _create(
        client, headers, equipment_items=[{"equipment_id": projector.id, "quantity_requested": 99}]
    )

    assert body["equipment_items"][0]["quantity_requested"] == 99


# ---------------------------------------------------------------------------
# Ownership and lifecycle
# ---------------------------------------------------------------------------


def test_another_organiser_cannot_add_equipment_to_someone_elses_draft(client, db_session):
    """404 rather than 403 -- "no such event" and "not yours" stay
    indistinguishable, so ids cannot be probed."""
    _, a_headers = _organiser(client, db_session, "a@example.com")
    _, b_headers = _organiser(client, db_session, "b@example.com")
    mic = _equipment(db_session, "Shure BLX24")
    event_id = _create(client, a_headers, purpose="A's event")["id"]

    res = client.patch(
        f"/events/{event_id}",
        json={"equipment_items": [{"equipment_id": mic.id, "quantity_requested": 1}]},
        headers=b_headers,
    )

    assert res.status_code == 404


def test_equipment_cannot_be_changed_after_submitting(client, db_session):
    """A submitted request is under review; changing what it asks for behind
    the Coordinator's back would make the review meaningless."""
    _, headers = _organiser(client, db_session)
    mic = _equipment(db_session, "Shure BLX24")
    event_id = _create(
        client,
        headers,
        **COMPLETE,
        equipment_items=[{"equipment_id": mic.id, "quantity_requested": 6}],
    )["id"]
    assert client.post(f"/events/{event_id}/submit", headers=headers).status_code == 200

    res = client.patch(f"/events/{event_id}", json={"equipment_items": []}, headers=headers)

    assert res.status_code == 409
    assert db_session.query(EquipmentRequest).count() == 1


def test_submitting_is_not_blocked_by_having_no_equipment(client, db_session):
    """Not every event needs equipment, so it is not a mandatory field."""
    _, headers = _organiser(client, db_session)
    event_id = _create(client, headers, **COMPLETE)["id"]

    res = client.post(f"/events/{event_id}/submit", headers=headers)

    assert res.status_code == 200, res.text


def test_the_coordinator_sees_the_requested_equipment(client, db_session):
    """The whole point of structuring this: the Coordinator reads a list,
    not a sentence."""
    organiser, org_headers = _organiser(client, db_session)
    coordinator, _ = _user(client, db_session, Role.COORDINATOR, "coord@example.com")
    mic = _equipment(db_session, "Shure BLX24 Handheld Microphone")
    event_id = _create(
        client,
        org_headers,
        **COMPLETE,
        equipment_items=[{"equipment_id": mic.id, "quantity_requested": 6}],
    )["id"]
    client.post(f"/events/{event_id}/submit", headers=org_headers)

    # Assignment is automatic on submit; point it at our coordinator either way.
    from app.models.events import Event

    db_session.get(Event, event_id).coordinator_id = coordinator.id
    db_session.commit()
    coord_headers = {
        "Authorization": "Bearer "
        + client.post(
            "/auth/login", json={"email": "coord@example.com", "password": "password123"}
        ).json()["access_token"]
    }

    body = client.get(f"/events/assigned/{event_id}", headers=coord_headers).json()

    line = body["equipment_items"][0]
    assert line["equipment_name"] == "Shure BLX24 Handheld Microphone"
    assert line["quantity_requested"] == 6


# ---------------------------------------------------------------------------
# GET /equipment/options -- the picker's data source
# ---------------------------------------------------------------------------


def test_options_lists_items_for_the_picker(client, db_session):
    _, headers = _organiser(client, db_session)
    _equipment(db_session, "Shure BLX24", category="Audio")
    _equipment(db_session, "Epson EB-L200SW", category="Projection")

    res = client.get("/equipment/options", headers=headers)

    assert res.status_code == 200
    assert {item["name"] for item in res.json()} == {"Shure BLX24", "Epson EB-L200SW"}


def test_options_omits_retired_items(client, db_session):
    """Offering one would guarantee a request nobody can fulfil."""
    _, headers = _organiser(client, db_session)
    _equipment(db_session, "Shure BLX24")
    _equipment(
        db_session,
        "Panasonic PT-VW360",
        operational_status=EquipmentOperationalStatus.retired,
    )

    names = {item["name"] for item in client.get("/equipment/options", headers=headers).json()}

    assert names == {"Shure BLX24"}


def test_options_exposes_only_what_the_picker_needs(client, db_session):
    """The leak test, and the reason this endpoint exists separately from
    GET /equipment.

    An Event Organiser is an EXTERNAL client. The catalogue endpoint returns
    storage locations, operational condition and live stock levels; a picker
    that merely declines to render those would still ship them over the
    wire. This response carries three keys and nothing else.
    """
    _, headers = _organiser(client, db_session)
    _equipment(db_session, "Shure BLX24", location="Marina Bay - AV Store 2", total_quantity=16)

    option = client.get("/equipment/options", headers=headers).json()[0]

    assert set(option) == {"id", "name", "category"}


def test_options_can_be_searched(client, db_session):
    _, headers = _organiser(client, db_session)
    _equipment(db_session, "Shure BLX24 Handheld Microphone", category="Audio")
    _equipment(db_session, "Epson EB-L200SW Projector", category="Projection")

    found = client.get("/equipment/options?q=micro", headers=headers).json()

    assert [item["name"] for item in found] == ["Shure BLX24 Handheld Microphone"]


def test_an_attendee_cannot_read_the_picker_options(client, db_session):
    """Gated on EVENT_WRITE -- you get this because you are filling in an
    event request, not because you may browse the inventory."""
    _, headers = _user(client, db_session, Role.ATTENDEE, "attendee@example.com")

    assert client.get("/equipment/options", headers=headers).status_code == 403
