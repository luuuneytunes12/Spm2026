import enum

class EventStatus(enum.StrEnum):
    draft = "draft"
    submitted = "submitted"
    under_review = "under_review"
    changes_requested = "changes_requested"
    approved = "approved"
    rejected = "rejected"
    planning = "planning"
    # Venue and equipment are arranged; a Safety Officer must pass the event
    # before it is confirmed (see routers/safety_checks.py).
    awaiting_safety_check = "awaiting_safety_check"
    confirmed = "confirmed"
    completed = "completed"
    cancelled = "cancelled"


# An event that has been approved and has not yet finished: the window in
# which resources (a venue, equipment) are committed to it. Anything earlier
# is not yet a plan, and a rejected, completed or cancelled event has nothing
# left to hold resources for.
PLANNED_EVENT_STATUSES = (
    EventStatus.approved,
    EventStatus.planning,
    EventStatus.confirmed,
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
    safety_check_passed = "safety_check_passed"
    safety_changes_requested = "safety_changes_requested"
    safety_check_rejected = "safety_check_rejected"


class ChangeRequestStatus(enum.StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
