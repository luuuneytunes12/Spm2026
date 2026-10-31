"""SCRUM-59: equipment availability after an event is completed early.

Jira AC1 releases reservations on cancellation or completion; AC2 reflects
released stock in the catalogue; AC3 permits a normal later reservation. This
file exercises the early-completion stock/reuse scenario through the API and
an isolated database. It does not alone cover every cancellation scenario.
SCRUM-59 is outside SCRUM-1–55, but relates to SCRUM-45/46 availability and
reservation. Test data and credentials are synthetic.
"""

from datetime import datetime, timedelta, timezone

from app.core.roles import Role
from app.models.enums import EquipmentStatus, EventStatus
from app.domain.requirement_progress import RequirementReservationLinks, RequirementStatus
from app.models.equipment import (
    CoordinatorEquipmentRequirement,
    Equipment,
    EquipmentRequest,
    RequirementReservationLink,
)
from app.models.events import Event
from event_review_test_helpers import user


def test_event_completed_releases_reserved_stock_before_its_scheduled_end(client, db_session):
    """SCRUM-59 AC1–AC3: completion frees stock for an overlapping new event.

    The finished event previously reserved five of eight projectors. The new
    event overlaps its scheduled time, so successfully reserving five checks
    that the completed event no longer consumes the stock.
    """
    _, tech_headers = user(
        client, db_session, Role.TECH_SUPPORT, "tech@example.com", "Tess Tech"
    )
    organiser, _ = user(
        client, db_session, Role.ORGANISER, "organiser@example.com", "Olivia Org"
    )
    item = Equipment(name="Projector", category="Projection", total_quantity=8)
    db_session.add(item)
    db_session.flush()

    start = datetime.now(timezone.utc) + timedelta(days=1)
    event = Event(
        name="Completed early",
        organiser_id=organiser.id,
        status=EventStatus.event_completed,
        proposed_start=start,
        proposed_end=start + timedelta(hours=8),
    )
    requirement = CoordinatorEquipmentRequirement(
        event_id=event.id,
        category="Projection",
        quantity_needed=5,
        status=EquipmentStatus.requested,
        created_by=organiser.id,
    )
    replacement = Event(
        name="New event",
        organiser_id=organiser.id,
        status=EventStatus.event_approved,
        proposed_start=start,
        proposed_end=start + timedelta(hours=8),
    )
    db_session.add(event)
    db_session.flush()
    requirement.event_id = event.id
    db_session.add(requirement)
    db_session.add(replacement)
    db_session.flush()
    db_session.add_all(
        (
            EquipmentRequest(
                event_id=event.id,
                equipment_id=item.id,
                quantity_requested=5,
                status=EquipmentStatus.reserved,
            ),
            EquipmentRequest(
                event_id=replacement.id,
                equipment_id=item.id,
                quantity_requested=5,
                status=EquipmentStatus.requested,
            ),
        )
    )
    db_session.add(
        RequirementReservationLink(
            requirement_id=requirement.id,
            event_id=event.id,
            equipment_id=item.id,
        )
    )
    db_session.commit()

    progress = RequirementReservationLinks(db_session).progress_for(requirement)
    assert progress.status is RequirementStatus.AVAILABLE
    assert progress.was_reserved == 5
    assert progress.reserved == 0

    response = client.get("/equipment", headers=tech_headers)

    assert response.status_code == 200
    projector = next(row for row in response.json()["items"] if row["id"] == item.id)
    assert projector["available_quantity"] == 8
    reservation = client.post(
        "/equipment-reservations",
        json={"event_id": replacement.id, "equipment_id": item.id},
        headers=tech_headers,
    )
    assert reservation.status_code == 200
    assert reservation.json()["quantity"] == 5
