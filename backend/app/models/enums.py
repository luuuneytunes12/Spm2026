import enum


class UserRole(enum.StrEnum):
    organiser = "organiser"
    coordinator = "coordinator"
    venue_staff = "venue_staff"
    tech_support = "tech_support"
    attendee = "attendee"


class EventStatus(enum.StrEnum):
    draft = "draft"
    submitted = "submitted"
    under_review = "under_review"
    changes_requested = "changes_requested"
    approved = "approved"
    rejected = "rejected"
    planning = "planning"
    confirmed = "confirmed"
    completed = "completed"
    cancelled = "cancelled"


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


class ChangeRequestStatus(enum.StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
