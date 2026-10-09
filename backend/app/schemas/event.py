from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import BookingStatus, ChangeRequestStatus, EquipmentStatus, EventStatus

# The fields an event request must carry before it can be SUBMITTED, in the
# order the form presents them. Drafts are exempt -- see EventIn below.
#
# This list is the single source of truth for "is this request complete?".
# The submit endpoint reports exactly which of these are still empty so the
# UI can flag them, rather than failing with a generic "invalid request".
#
# `registration_enabled` is deliberately NOT here: it is a non-null boolean
# defaulting to false, so "no registration needed" is itself a complete
# answer and it can never be missing.
MANDATORY_FIELDS: tuple[tuple[str, str], ...] = (
    ("name", "Event name"),
    ("purpose", "Purpose"),
    ("event_type", "Event type"),
    ("proposed_start", "Proposed start"),
    ("proposed_end", "Proposed end"),
    ("expected_attendance", "Expected attendance"),
    ("venue_requirements", "Venue requirements"),
    ("accessibility_needs", "Accessibility needs"),
)

# `equipment_requirements` is deliberately NOT here any more. It used to be
# the only way to state equipment needs, so it had to be filled in; now the
# structured `equipment_items` carry that, and the text box is just a note
# for anything not in the catalogue.
#
# Nor does `equipment_items` replace it in this tuple: plenty of events need
# no equipment at all, and _missing_mandatory() reads scalar attributes --
# an empty list is neither None nor a blank string, so it would never be
# flagged even if it were listed here.


class EquipmentLineIn(BaseModel):
    """One piece of equipment the Organiser is asking for."""

    equipment_id: int
    # gt=0 mirrors the database CHECK. Validating here turns what would be
    # an IntegrityError (a 500) into a clean 422 naming the field. Defaults
    # to 1 because a row the Organiser added but never typed a number into
    # plainly means "one of these".
    quantity_requested: int = Field(default=1, gt=0)
    technical_requirements: str | None = None


class EquipmentLineOut(BaseModel):
    """One requested line, with enough of the catalogue to read it.

    `equipment_name` and `equipment_category` are flattened passthroughs
    (see app/models/equipment.py) rather than a nested Equipment object.
    Nesting the whole item would drip storage location, operational
    condition and stock levels into every event response -- and an Event
    Organiser is an external client.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    equipment_id: int
    equipment_name: str
    equipment_category: str | None
    quantity_requested: int
    technical_requirements: str | None
    # Always 'requested' when the Organiser creates it; Technical Support
    # moves it on. Exposed so the same markup can show a review outcome
    # later without a schema change.
    status: EquipmentStatus


class EventIn(BaseModel):
    """Create/update payload for an event request.

    EVERY field is optional. That is the whole point of a draft: an
    Organiser may save after typing nothing but a purpose, and come back
    to it later. Completeness is checked only at submit time, against
    MANDATORY_FIELDS above.
    """

    name: str | None = Field(default=None, max_length=200)
    purpose: str | None = None
    event_type: str | None = Field(default=None, max_length=100)
    description: str | None = None
    programme: str | None = None
    proposed_start: datetime | None = None
    proposed_end: datetime | None = None
    # gt=0 mirrors the database CHECK. Validating here turns what would be
    # an IntegrityError (a 500) into a clean 422 naming the field.
    expected_attendance: int | None = Field(default=None, gt=0)
    venue_requirements: str | None = None
    room_layout_preference: str | None = Field(default=None, max_length=100)
    accessibility_needs: str | None = None
    equipment_requirements: str | None = None
    # Omitted entirely -> leave existing lines alone (consistent with every
    # other field under exclude_unset). An explicit [] clears them.
    equipment_items: list[EquipmentLineIn] | None = None
    special_arrangements: str | None = None
    registration_enabled: bool | None = None

    @model_validator(mode="after")
    def _end_after_start(self) -> "EventIn":
        """Mirror of the `proposed_end > proposed_start` database CHECK.

        Without this, a backwards date range reaches postgres and comes
        back as an IntegrityError -> 500. Only enforced when BOTH are
        present, so a half-filled draft still saves.
        """
        if (
            self.proposed_start is not None
            and self.proposed_end is not None
            and self.proposed_end <= self.proposed_start
        ):
            raise ValueError("proposed_end must be after proposed_start")
        return self


class EventChangeRequestIn(BaseModel):
    description: str = Field(..., min_length=1, max_length=2000)
    proposed_changes: EventIn

    @field_validator("description")
    @classmethod
    def description_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Change request description cannot be blank")
        return value.strip()

    @model_validator(mode="after")
    def _require_changes(self) -> "EventChangeRequestIn":
        if not self.proposed_changes.model_fields_set:
            raise ValueError("At least one proposed change is required")
        return self


class EventChangeDecisionIn(BaseModel):
    review_notes: str | None = Field(default=None, max_length=2000)


class VenueBookingImpact(BaseModel):
    id: int
    venue_name: str
    start_time: datetime
    end_time: datetime
    status: BookingStatus


class EquipmentReservationImpact(BaseModel):
    id: int
    equipment_name: str
    quantity_requested: int
    status: EquipmentStatus


class EventChangeRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int
    requested_by: int
    description: str
    proposed_changes: dict
    status: ChangeRequestStatus
    review_notes: str | None
    created_at: datetime
    reviewed_at: datetime | None
    important_change: bool
    safety_check_required: bool = False
    venue_bookings_to_reconsider: list[VenueBookingImpact]
    equipment_reservations_to_reconsider: list[EquipmentReservationImpact]


class OrganiserContact(BaseModel):
    """A projection of `users` down to what one party needs to know about
    another: who they are, and how to reach them.

    Named for its original use (an Organiser's contact details, as seen by
    the Coordinator assigned to their event) but reused as-is for the
    reverse direction -- `EventOut.coordinator` below -- since the shape a
    Coordinator's contact details need is identical. The `users` table
    carries a name and an email and nothing else, so `email` is the whole
    of "contact details" today.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str


class EventOut(BaseModel):
    """Full event request, as returned when opening one for editing."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    organiser_id: int
    coordinator_id: int | None
    # None until the system (or a reassignment) has picked someone -- see
    # app/services/assignment.py. This is what lets an Organiser see who is
    # coordinating their event, straight off GET /events/{id}.
    coordinator: OrganiserContact | None
    name: str | None
    purpose: str | None
    event_type: str | None
    description: str | None
    programme: str | None
    proposed_start: datetime | None
    proposed_end: datetime | None
    expected_attendance: int | None
    venue_requirements: str | None
    room_layout_preference: str | None
    accessibility_needs: str | None
    equipment_requirements: str | None
    # Empty rather than absent for an event with no equipment, so the client
    # never has to handle a missing key.
    equipment_items: list[EquipmentLineOut] = []
    special_arrangements: str | None
    registration_enabled: bool
    registration_opens_at: datetime | None = None
    registration_closes_at: datetime | None = None
    status: EventStatus
    submitted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ActivityEntry(BaseModel):
    """One line of an event's activity log, from `event_status_history`.

    The actor is flattened to `changed_by_name` rather than nested as a
    whole user: the log only ever renders a name, and nesting
    OrganiserContact here would hand out the email address of everyone who
    has ever touched the row, which no acceptance criterion asks for.
    """

    from_status: str | None
    to_status: str
    note: str | None
    changed_by_name: str | None
    created_at: datetime


class AssignedEventDetail(EventOut):
    """Everything a Coordinator needs to plan an event assigned to them.

    Extends the Organiser-facing EventOut with the two things this story
    adds -- who to contact, and what has happened so far. Both are
    assembled by the router; neither is a plain column on `events`.
    """

    organiser: OrganiserContact
    activity: list[ActivityEntry]
    change_requests: list[EventChangeRequestOut] = []
    # What still stands between an Approved event and "Confirmed": an empty
    # list means the Coordinator may confirm it now.
    confirmation_outstanding: list[str] = []


class RegistrationSettingsIn(BaseModel):
    """What a Coordinator sets to open (or close) registration on an event.

    Dates are only mandatory when enabling -- checked by the router, which
    reports each offending field the same way the submit endpoint does.
    """

    registration_enabled: bool
    registration_opens_at: datetime | None = None
    registration_closes_at: datetime | None = None


class EventSummary(BaseModel):
    """Lighter shape for the Drafts / Submitted Requests lists.

    `name` is nullable here for the same reason it is nullable in the
    database: a draft may not have been named yet, and the UI renders
    those as "Untitled draft".
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None
    event_type: str | None
    proposed_start: datetime | None
    proposed_end: datetime | None
    expected_attendance: int | None
    status: EventStatus
    submitted_at: datetime | None
    updated_at: datetime
    has_pending_change_request: bool = False


class LeadEventOut(EventSummary):
    """An EventSummary plus the two people on it, for the Coordinator Lead's
    views. `coordinator` is null for an unassigned request."""

    organiser: OrganiserContact
    coordinator: OrganiserContact | None = None


class LeadEventDetail(EventOut):
    """A queued request as the Coordinator Lead reviews it: everything the
    Organiser entered (EventOut) plus who the Organiser is. Read-only."""

    organiser: OrganiserContact


class LeadCoordinatorOut(BaseModel):
    """A Coordinator and how many active Events they hold (Lead's filter)."""

    id: int
    name: str
    email: str
    active_events: int


class LeadAssignIn(BaseModel):
    """Which Coordinator the Lead is assigning or reassigning an Event to."""

    coordinator_id: int
