import enum

class EventStatus(enum.StrEnum):
    """The Event statuses of dod.md section 11a -- those names, and no others.

    Each stored value is the DoD name in snake_case, so the UI label, the
    database enum, the activity log and the tests all spell it the same way.
    """

    draft = "draft"
    submitted_awaiting_coordinator = "submitted_awaiting_coordinator"
    under_review = "under_review"
    awaiting_organiser_reply = "awaiting_organiser_reply"
    event_approved = "event_approved"
    planning_event = "planning_event"
    awaiting_safety_check = "awaiting_safety_check"
    safety_check_passed = "safety_check_passed"  # "Safety Check Passed (Event Confirmed)"
    event_completed = "event_completed"
    event_rejected = "event_rejected"
    event_cancelled = "event_cancelled"


# An event that has been approved and has not yet finished: the window in
# which resources (a venue, equipment) are committed to it. Anything earlier
# is not yet a plan, and a rejected, completed or cancelled event has nothing
# left to hold resources for.
PLANNED_EVENT_STATUSES = (
    EventStatus.event_approved,
    EventStatus.planning_event,
    EventStatus.safety_check_passed,
)


class BookingStatus(enum.StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"


class EquipmentStatus(enum.StrEnum):
    """Lifecycle of an equipment REQUEST (on equipment_requests)."""

    requested = "requested"
    reviewing = "reviewing"
    reserved = "reserved"
    rejected = "rejected"
    cancelled = "cancelled"


class EquipmentOperationalStatus(enum.StrEnum):
    """Condition of a physical equipment ITEM (on equipment).

    Separate from EquipmentStatus above, which describes a request. An item
    that is not `available` must not be treated as freely usable for an
    event -- `retired` items stay in the catalogue so historical
    reservations still resolve, but are never offered again.
    """

    available = "available"
    maintenance = "maintenance"
    damaged = "damaged"
    retired = "retired"


class RegistrationStatus(enum.StrEnum):
    registered = "registered"
    withdrawn = "withdrawn"


class NotificationType(enum.StrEnum):
    event_assigned = "event_assigned"
    event_reassigned_away = "event_reassigned_away"
    event_coordinator_assigned = "event_coordinator_assigned"
    event_approved = "event_approved"
    event_rejected = "event_rejected"
    event_confirmed = "event_confirmed"
    event_submitted = "event_submitted"


class ChangeRequestStatus(enum.StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
