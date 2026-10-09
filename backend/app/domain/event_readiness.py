"""Whether an event's arrangements are ready to go ahead.

Shared by the Coordinator's "Submit for Safety Check" and the Safety
Officer's approval, so both refuse for the same reasons and name the same
outstanding items.
"""

from datetime import datetime, timezone

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, joinedload

from app.domain.requirement_progress import RequirementReservationLinks
from app.models.equipment import CoordinatorEquipmentRequirement
from app.models.enums import (
    BookingStatus,
    EquipmentStatus,
    EventStatus,
    PLANNING_STATUSES,
)
from app.models.events import Event
from app.models.venues import VenueBooking


def outstanding_arrangements(db: Session, event: Event) -> list[str]:
    """What still stands between this event and going ahead -- every item,
    each with its status, so the Coordinator sees the whole list at once.

    Venue: the event needs at least one booking that is not cancelled, and
    EVERY such booking must be approved -- a pending one (a tentative hold) or
    a rejected one is outstanding, named with its status. A cancelled booking
    is withdrawn, so it is ignored. A booking a Safety Officer has flagged for
    re-review is outstanding until its staff clear the flag.

    Equipment: every line and every Coordinator requirement must be RESERVED.
    Cancelled lines are ignored -- the Organiser withdrew them, so there is
    nothing left to arrange. An event that asked for no equipment has no
    equipment to wait on.
    """
    outstanding: list[str] = []

    now = datetime.now(timezone.utc)
    in_play = (
        db.query(VenueBooking)
        .options(joinedload(VenueBooking.venue))
        .filter(
            VenueBooking.event_id == event.id,
            VenueBooking.status != BookingStatus.cancelled,
            or_(
                VenueBooking.status != BookingStatus.tentative_hold,
                and_(
                    VenueBooking.expires_at.is_not(None),
                    VenueBooking.expires_at > now,
                ),
            ),
        )
        .order_by(VenueBooking.id)
        .all()
    )
    if not in_play:
        outstanding.append(
            "The event has no venue: no venue booking has been requested, or all were cancelled"
        )
    for booking in in_play:
        if booking.status is not BookingStatus.approved:
            outstanding.append(
                f"Venue booking '{booking.venue.name}' is not approved (status: {booking.status})"
            )
        elif booking.safety_recheck_reason:
            outstanding.append(
                f"Venue booking '{booking.venue.name}' is awaiting safety re-review by Venue Staff"
            )

    for line in event.equipment_items:
        if line.status is EquipmentStatus.cancelled:
            continue
        if line.status is not EquipmentStatus.reserved:
            outstanding.append(f"Equipment '{line.equipment.name}' is not reserved (status: {line.status})")
        elif line.safety_recheck_reason:
            outstanding.append(
                f"Equipment '{line.equipment.name}' is awaiting safety re-review by Technical Support"
            )

    requirements = (
        db.query(CoordinatorEquipmentRequirement)
        .filter(CoordinatorEquipmentRequirement.event_id == event.id)
        .order_by(CoordinatorEquipmentRequirement.id)
        .all()
    )
    progress = RequirementReservationLinks(db).progress_of(requirements)
    for requirement in requirements:
        requirement_status = progress[requirement.id].status
        if requirement_status is not EquipmentStatus.reserved:
            outstanding.append(
                f"Equipment requirement '{requirement.category}' is not reserved "
                f"(status: {requirement_status})"
            )
    return outstanding


def can_enter_preparation(event: Event) -> bool:
    """Only an event that has passed its Safety Check may move to preparation."""
    return event.status == EventStatus.safety_check_passed
