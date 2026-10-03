"""Tests for the "View Equipment Catalogue" story (Technical Support Staff).

    As a Technical Support Staff member, I want to view the equipment
    catalogue, so that I can see what equipment exists and in what quantity
    when assessing an event's requirements.

Each test name states the acceptance criterion it covers, so a criterion can
be traced to the test that proves it (see the S4 AC markers in the
docstrings, and docs/test-cases-tech-support-equipment-catalogue.md).
"""

from datetime import datetime, timedelta, timezone

from app.core.roles import Role
from app.models.enums import EquipmentOperationalStatus, EquipmentStatus
from app.models.equipment import Equipment, EquipmentRequest
from app.models.events import Event
from app.models.user import User


def _user(client, db_session, role, email, name="Test User"):
    """Register a user, promote them to `role`, and return auth headers.

    Registration always assigns `attendee` (by design -- a client can never
    pick its own role), so the role is set directly here -- the same way a
    non-attendee is bootstrapped against a real database, with an UPDATE.
    The re-login is what makes the returned token reflect the new role.
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
    return {"Authorization": f"Bearer {token}"}


def _equipment(db_session, name, **overrides) -> Equipment:
    """Insert one catalogue item directly.

    There is no endpoint that creates equipment -- that is EQUIPMENT_MANAGE
    and a separate story -- so these go in through the model, exactly as the
    seed migration does.
    """
    item = Equipment(
        name=name,
        category=overrides.pop("category", "Audio"),
        description=overrides.pop("description", "A description."),
        total_quantity=overrides.pop("total_quantity", 10),
        location=overrides.pop("location", "Marina Bay Facility"),
        operational_status=overrides.pop(
            "operational_status", EquipmentOperationalStatus.available
        ),
        technical_specs=overrides.pop("technical_specs", None),
        **overrides,
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item


def _reserve(db_session, item, quantity, status=EquipmentStatus.reserved, ends=None):
    """Attach an equipment request to a throwaway event.

    equipment_requests.event_id is NOT NULL, so a request needs an event to
    hang off. The event ends in the future unless `ends` says otherwise --
    reserved stock is freed at its event's end time.
    """
    organiser = User(
        name="Organiser",
        email=f"org{item.id}-{quantity}-{status.value}@cs.local",
        password_hash="x",
        role=Role.ORGANISER.value,
    )
    db_session.add(organiser)
    db_session.flush()

    event = Event(
        name="Some event",
        organiser_id=organiser.id,
        proposed_end=ends or datetime.now(timezone.utc) + timedelta(days=1),
    )
    db_session.add(event)
    db_session.flush()

    db_session.add(
        EquipmentRequest(
            event_id=event.id,
            equipment_id=item.id,
            quantity_requested=quantity,
            status=status,
        )
    )
    db_session.commit()


def _tech_support(client, db_session, email="tech@cs.local"):
    return _user(client, db_session, Role.TECH_SUPPORT, email, name="Tech Support")


# ---------------------------------------------------------------------------
# AC1 -- I can open the catalogue and see every item held by ConnectSphere.
# ---------------------------------------------------------------------------


def test_catalogue_returns_every_item_held(client, db_session):
    """S4 AC1: every row in the table comes back."""
    headers = _tech_support(client, db_session)
    for name in ("Projector", "Microphone", "Stage Deck"):
        _equipment(db_session, name)

    res = client.get("/equipment", headers=headers)

    assert res.status_code == 200
    assert {item["name"] for item in res.json()["items"]} == {
        "Projector",
        "Microphone",
        "Stage Deck",
    }


def test_catalogue_still_lists_items_that_cannot_be_used(client, db_session):
    """S4 AC1: damaged, under-maintenance and retired items are still listed.

    "Every item held by ConnectSphere" means every item. Whether a given one
    can be used is what operational_status and available_quantity report --
    filtering them out of the catalogue would hide exactly the kit
    Technical Support most needs to know about.
    """
    headers = _tech_support(client, db_session)
    _equipment(db_session, "Working Mixer")
    _equipment(db_session, "Broken Mixer", operational_status=EquipmentOperationalStatus.damaged)
    _equipment(db_session, "Old Projector", operational_status=EquipmentOperationalStatus.retired)
    _equipment(
        db_session, "Serviced Lamp", operational_status=EquipmentOperationalStatus.maintenance
    )

    names = {item["name"] for item in client.get("/equipment", headers=headers).json()["items"]}

    assert names == {"Working Mixer", "Broken Mixer", "Old Projector", "Serviced Lamp"}


def test_empty_catalogue_returns_an_empty_list_not_an_error(client, db_session):
    """S4 AC1 boundary: nothing recorded yet is an empty catalogue, not a 404."""
    headers = _tech_support(client, db_session)

    res = client.get("/equipment", headers=headers)

    assert res.status_code == 200
    assert res.json() == {"items": [], "types": []}


# ---------------------------------------------------------------------------
# AC2 -- type, description, total quantity, location, availability, status.
# ---------------------------------------------------------------------------


def test_each_item_shows_every_field_named_in_the_criterion(client, db_session):
    """S4 AC2: all six fields the acceptance criterion names are present."""
    headers = _tech_support(client, db_session)
    _equipment(
        db_session,
        "Shure BLX24",
        category="Audio",
        description="Wireless handheld microphone.",
        total_quantity=16,
        location="Marina Bay Facility - AV Store 2",
    )

    item = client.get("/equipment", headers=headers).json()["items"][0]

    assert item["category"] == "Audio"
    assert item["description"] == "Wireless handheld microphone."
    assert item["total_quantity"] == 16
    assert item["location"] == "Marina Bay Facility - AV Store 2"
    assert item["available_quantity"] == 16
    assert item["operational_status"] == "available"


def test_availability_subtracts_reserved_units(client, db_session):
    """S4 AC2: availability is total quantity minus units already reserved."""
    headers = _tech_support(client, db_session)
    item = _equipment(db_session, "Projector", total_quantity=6)
    _reserve(db_session, item, 2)
    _reserve(db_session, item, 1)

    row = client.get("/equipment", headers=headers).json()["items"][0]

    assert row["total_quantity"] == 6
    assert row["available_quantity"] == 3


def test_only_reserved_requests_reduce_availability(client, db_session):
    """S4 AC2 boundary: requests that were never granted do not hold stock.

    A `requested` or `reviewing` request has not been granted yet, and a
    `rejected`/`cancelled` one never will be. Counting any of them would
    hide stock that is in fact free.
    """
    headers = _tech_support(client, db_session)
    item = _equipment(db_session, "Projector", total_quantity=6)
    _reserve(db_session, item, 1, status=EquipmentStatus.requested)
    _reserve(db_session, item, 1, status=EquipmentStatus.reviewing)
    _reserve(db_session, item, 1, status=EquipmentStatus.rejected)
    _reserve(db_session, item, 1, status=EquipmentStatus.cancelled)

    row = client.get("/equipment", headers=headers).json()["items"][0]

    assert row["available_quantity"] == 6


def test_stock_reserved_for_an_event_that_has_ended_is_available_again(client, db_session):
    """S4 AC2: reserved stock is freed at its event's end time."""
    headers = _tech_support(client, db_session)
    item = _equipment(db_session, "Projector", total_quantity=6)
    _reserve(db_session, item, 2)
    _reserve(db_session, item, 3, ends=datetime.now(timezone.utc) - timedelta(hours=1))

    row = client.get("/equipment", headers=headers).json()["items"][0]

    assert row["available_quantity"] == 4


def test_a_non_operational_item_reports_nothing_available(client, db_session):
    """S4 AC2: condition overrides arithmetic -- two damaged mixers are not
    two available mixers, even with no reservations against them."""
    headers = _tech_support(client, db_session)
    _equipment(
        db_session,
        "Broken Mixer",
        total_quantity=2,
        operational_status=EquipmentOperationalStatus.damaged,
    )

    row = client.get("/equipment", headers=headers).json()["items"][0]

    assert row["total_quantity"] == 2
    assert row["available_quantity"] == 0


def test_over_reservation_reports_none_left_rather_than_a_negative(client, db_session):
    """S4 AC2 boundary: more reserved than owned (stock reduced after the
    fact) reads as zero available, never as a negative count."""
    headers = _tech_support(client, db_session)
    item = _equipment(db_session, "Projector", total_quantity=2)
    _reserve(db_session, item, 5)

    row = client.get("/equipment", headers=headers).json()["items"][0]

    assert row["available_quantity"] == 0


# ---------------------------------------------------------------------------
# AC3 -- I can search or filter the catalogue by equipment type.
# ---------------------------------------------------------------------------


def test_filtering_by_type_returns_only_that_type(client, db_session):
    """S4 AC3: ?type= narrows the catalogue to one equipment type."""
    headers = _tech_support(client, db_session)
    _equipment(db_session, "Microphone", category="Audio")
    _equipment(db_session, "Projector", category="Projection")

    items = client.get("/equipment?type=Audio", headers=headers).json()["items"]

    assert [item["name"] for item in items] == ["Microphone"]


def test_search_matches_name_and_description_case_insensitively(client, db_session):
    """S4 AC3: ?q= searches both the name and the description."""
    headers = _tech_support(client, db_session)
    _equipment(db_session, "Shure BLX24", description="Wireless handheld microphone.")
    _equipment(db_session, "Stage Deck", description="Interlocking platform.")

    by_name = client.get("/equipment?q=shure", headers=headers).json()["items"]
    by_description = client.get("/equipment?q=MICROPHONE", headers=headers).json()["items"]

    assert [item["name"] for item in by_name] == ["Shure BLX24"]
    assert [item["name"] for item in by_description] == ["Shure BLX24"]


def test_type_and_search_combine(client, db_session):
    """S4 AC3: the two filters are AND, not OR."""
    headers = _tech_support(client, db_session)
    _equipment(db_session, "Audio Mixer", category="Audio")
    _equipment(db_session, "Audio Splitter", category="Audio")
    _equipment(db_session, "Video Mixer", category="Video")

    items = client.get("/equipment?type=Audio&q=mixer", headers=headers).json()["items"]

    assert [item["name"] for item in items] == ["Audio Mixer"]


def test_the_type_list_covers_the_whole_catalogue_even_while_filtered(client, db_session):
    """S4 AC3: `types` is never narrowed by the active filter.

    The type dropdown is built from this. If it shrank to the selected type,
    there would be no way to pick a different one or clear the filter.
    """
    headers = _tech_support(client, db_session)
    _equipment(db_session, "Microphone", category="Audio")
    _equipment(db_session, "Projector", category="Projection")
    _equipment(db_session, "Stage Deck", category="Staging")

    body = client.get("/equipment?type=Audio", headers=headers).json()

    assert [item["name"] for item in body["items"]] == ["Microphone"]
    assert body["types"] == ["Audio", "Projection", "Staging"]


def test_an_unknown_type_returns_an_empty_list(client, db_session):
    """S4 AC3 boundary: a type nothing matches is an empty result, not a 404."""
    headers = _tech_support(client, db_session)
    _equipment(db_session, "Microphone", category="Audio")

    res = client.get("/equipment?type=Pyrotechnics", headers=headers)

    assert res.status_code == 200
    assert res.json()["items"] == []
    assert res.json()["types"] == ["Audio"]


# ---------------------------------------------------------------------------
# Beyond the acceptance criteria -- who may read the catalogue.
# ---------------------------------------------------------------------------


def test_an_attendee_cannot_read_the_catalogue(client, db_session):
    """An attendee holds no equipment permission, so this is 403."""
    headers = _user(client, db_session, Role.ATTENDEE, "attendee@cs.local")

    assert client.get("/equipment", headers=headers).status_code == 403


def test_an_anonymous_caller_cannot_read_the_catalogue(client, db_session):
    """No credentials is unauthenticated (401), not forbidden (403)."""
    assert client.get("/equipment").status_code == 401


def test_a_coordinator_can_read_the_catalogue(client, db_session):
    """The endpoint is gated on EQUIPMENT_READ, not on the tech_support role.

    A Coordinator holds that permission -- they have to know what exists
    before requesting it -- so they must be able to read the catalogue. This
    test is what stops someone "tightening" the endpoint to a single role
    and silently breaking the Coordinator's equipment-request story.
    """
    headers = _user(client, db_session, Role.COORDINATOR, "coord@cs.local")
    _equipment(db_session, "Microphone")

    res = client.get("/equipment", headers=headers)

    assert res.status_code == 200
    assert [item["name"] for item in res.json()["items"]] == ["Microphone"]
