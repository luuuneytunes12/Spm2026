"""Whether an event's arrangements are ready to go ahead.

Shared by the Coordinator's "Submit for Safety Check" and the Safety
Officer's approval, so both refuse for the same reasons and name the same
outstanding items.
"""

from sqlalchemy.orm import Session

from app.models.enums import BookingStatus, EquipmentStatus, EventStatus
from app.models.events import Event
from app.models.venues import VenueBooking

# The planning stage an event is in while its venue and equipment are being
# arranged -- `event_approved` on first pass, `planning_event` once a Safety Officer has
# sent it back.
PLANNING_STATUSES = (EventStatus.event_approved, EventStatus.planning_event)


def outstanding_arrangements(db: Session, event: Event) -> list[str]:
    """What still stands between this event and going ahead.

    It needs an APPROVED venue booking and every equipment line RESERVED.
    Cancelled lines are ignored -- the Organiser withdrew them, so there is
    nothing left to arrange. An event that asked for no equipment has no
    equipment to wait on. A booking or line a Safety Officer has flagged for
    re-review is outstanding until its staff clear the flag.
    """
    outstanding: list[str] = []

    booking = (
        db.query(VenueBooking)
        .filter(
            VenueBooking.event_id == event.id,
            VenueBooking.status == BookingStatus.approved,
        )
        .first()
    )
    if booking is None:
        outstanding.append("Venue booking is not approved")
    elif booking.safety_recheck_reason:
        outstanding.append("Venue booking is awaiting safety re-review by Venue Staff")

    for line in event.equipment_items:
        if line.status is EquipmentStatus.cancelled:
            continue
        if line.status is not EquipmentStatus.reserved:
            outstanding.append(f"Equipment '{line.equipment.name}' is not reserved (status: {line.status})")
        elif line.safety_recheck_reason:
            outstanding.append(
                f"Equipment '{line.equipment.name}' is awaiting safety re-review by Technical Support"
            )
    return outstanding


def can_enter_preparation(event: Event) -> bool:
    """Only an event that has passed its Safety Check may move to preparation."""
    return event.status == EventStatus.safety_check_passed
