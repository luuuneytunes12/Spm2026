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

    @property
    def label(self) -> str:
        """The dod.md name, for messages a person reads."""
        return _EVENT_STATUS_LABELS[self]


_EVENT_STATUS_LABELS = {
    EventStatus.draft: "Draft",
    EventStatus.submitted_awaiting_coordinator: "Submitted – Awaiting Coordinator",
    EventStatus.under_review: "Under Review",
    EventStatus.awaiting_organiser_reply: "Awaiting Organiser Reply",
    EventStatus.event_approved: "Event Approved",
    EventStatus.planning_event: "Planning Event",
    EventStatus.awaiting_safety_check: "Awaiting Safety Check",
    EventStatus.safety_check_passed: "Safety Check Passed (Event Confirmed)",
    EventStatus.event_completed: "Event Completed",
    EventStatus.event_rejected: "Event Rejected",
    EventStatus.event_cancelled: "Event Cancelled",
}


# Shared status groups keep workflow decisions aligned across routers and
# services. Individual Event rows still store exactly one EventStatus value.
TERMINAL_EVENT_STATUSES = (
    EventStatus.event_completed,
    EventStatus.event_cancelled,
    EventStatus.event_rejected,
)

EQUIPMENT_RELEASE_EVENT_STATUSES = (
    EventStatus.event_completed,
    EventStatus.event_cancelled,
)

ACTIVE_ASSIGNMENT_STATUSES = (
    EventStatus.submitted_awaiting_coordinator,
    EventStatus.under_review,
    EventStatus.awaiting_organiser_reply,
    EventStatus.event_approved,
    EventStatus.planning_event,
    EventStatus.awaiting_safety_check,
    EventStatus.safety_check_passed,
)

PLANNING_STATUSES = (EventStatus.event_approved, EventStatus.planning_event)

CHANGE_REQUEST_DISALLOWED_STATUSES = (
    EventStatus.draft,
    *TERMINAL_EVENT_STATUSES,
)

# TODO(confirm): Organisers may request changes while an event awaits a safety check.
CHANGE_REQUEST_ALLOWED_STATUSES = tuple(
    event_status
    for event_status in EventStatus
    if event_status not in CHANGE_REQUEST_DISALLOWED_STATUSES
)


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
    tentative_hold = "tentative_hold"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"
    # A tentative hold whose expiry passed before it was approved: the venue
    # is free again for that window (sql/027). Never counts as a booking.
    hold_expired = "hold_expired"
    # Superseded by an approved replacement booking (sql/029). Kept as history.
    replaced = "replaced"
    # Freed because its Event was cancelled or completed (sql/033). Kept as history.
    released = "released"


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
    safety_check_passed = "safety_check_passed"
    safety_changes_requested = "safety_changes_requested"
    safety_check_rejected = "safety_check_rejected"
    venue_booking_conflict = "venue_booking_conflict"
    safety_check_requested = "safety_check_requested"
    # The event left the Safety Officer's queue: back to planning because its
    # arrangements changed, so a check of it now would be of outdated plans.
    safety_check_withdrawn = "safety_check_withdrawn"
    venue_unavailability_recorded = "venue_unavailability_recorded"
    venue_hold_expiring = "venue_hold_expiring"
    venue_hold_expired = "venue_hold_expired"
    venue_booking_changed = "venue_booking_changed"
    venue_booking_cancelled = "venue_booking_cancelled"
    event_returned_to_planning = "event_returned_to_planning"
    clarification_requested = "clarification_requested"
    clarification_replied = "clarification_replied"
    event_details_changed = "event_details_changed"
    registration_status_changed = "registration_status_changed"
    venue_booking_released = "venue_booking_released"
    # Technical Support: equipment to review or reserve, and Events that moved.
    equipment_required = "equipment_required"
    equipment_requirement_changed = "equipment_requirement_changed"
    equipment_requirement_removed = "equipment_requirement_removed"
    equipment_event_rescheduled = "equipment_event_rescheduled"
    # Event Organiser: their Event's status, a Venue Booking decision, an
    # equipment outcome.
    event_status_changed = "event_status_changed"
    venue_booking_decided = "venue_booking_decided"
    equipment_outcome = "equipment_outcome"


class ChangeRequestStatus(enum.StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class UnavailabilityReason(enum.StrEnum):
    """Why Venue Staff took a venue out of use for a period (SCRUM-93)."""

    maintenance = "Maintenance"
    equipment_failure = "Equipment failure"
    renovation = "Renovation"
    safety_concern = "Safety concern"
    other = "Other"
