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
    requested = "requested"
    reviewing = "reviewing"
    reserved = "reserved"
    rejected = "rejected"
    cancelled = "cancelled"


class RegistrationStatus(enum.StrEnum):
    registered = "registered"
    withdrawn = "withdrawn"


class ChangeRequestStatus(enum.StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
