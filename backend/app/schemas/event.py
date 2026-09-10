from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import EventStatus

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
    ("equipment_requirements", "Equipment requirements"),
)


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


class EventOut(BaseModel):
    """Full event request, as returned when opening one for editing."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    organiser_id: int
    coordinator_id: int | None
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
    special_arrangements: str | None
    registration_enabled: bool
    status: EventStatus
    submitted_at: datetime | None
    created_at: datetime
    updated_at: datetime


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
