"""Schemas for venue booking requests (Coordinator -> Venue Staff)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import BookingStatus


class VenueRequest(BaseModel):
    """One venue a Coordinator is asking for, and what they need of it.

    The three needs are optional: left out, the booking shows the Event's own
    layout, accessibility and facilities needs. Blank counts as left out.
    """

    venue_id: int
    room_layout_preference: str | None = Field(default=None, max_length=2000)
    accessibility_needs: str | None = Field(default=None, max_length=2000)
    facilities_needs: str | None = Field(default=None, max_length=2000)

    @field_validator("room_layout_preference", "accessibility_needs", "facilities_needs")
    @classmethod
    def blank_is_not_given(cls, value: str | None) -> str | None:
        return (value or "").strip() or None


class VenueBookingCreate(BaseModel):
    """What a Coordinator sends: one or more venues, each with its own needs.
    The event's timing comes from the event itself, so the request can never
    disagree with what the Organiser asked for.

    `venues` may be empty or missing so that "no venue selected" reaches the
    router and is refused with a message, rather than as a bare schema error.
    """

    venues: list[VenueRequest] = []


class VenueBookingRejection(BaseModel):
    """What Venue Staff send when rejecting: a reason, an alternative, or
    both. Each is optional on its own, so "neither given" reaches the router
    and is refused with a message, rather than as a bare schema error.
    """

    reason: str | None = Field(default=None, max_length=2000)
    suggested_alternative: str | None = Field(default=None, max_length=2000)

    @field_validator("reason", "suggested_alternative")
    @classmethod
    def blank_is_not_given(cls, value: str | None) -> str | None:
        return (value or "").strip() or None


class BookingEventRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None


class BookingVenueRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    location: str
    capacity: int


class BookingPerson(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    email: str


class VenueBookingOut(BaseModel):
    """A booking request as Venue Staff open it: the selected venue, the
    event's date and time, expected attendance, layout requirements and
    accessibility or facility needs.

    Once decided it also carries the outcome as the Coordinator reads it:
    who decided and when, and for a rejection the reason and/or alternative.
    All four are null while the request is pending."""

    id: int
    status: BookingStatus
    created_at: datetime
    event: BookingEventRef
    venue: BookingVenueRef
    start_time: datetime
    end_time: datetime
    expected_attendance: int | None
    # What was asked of THIS venue; where the Coordinator gave nothing, the
    # Event's own needs.
    room_layout_preference: str | None
    accessibility_needs: str | None
    facilities_needs: str | None
    venue_requirements: str | None
    requested_by: BookingPerson
    decision_notes: str | None
    suggested_alternative: str | None
    # A Safety Officer's reason for sending an approved booking back for
    # review; null when nothing is outstanding.
    safety_recheck_reason: str | None = None
    reviewed_by: BookingPerson | None
    reviewed_at: datetime | None
