"""Schemas for venue booking requests (Coordinator -> Venue Staff)."""

from datetime import datetime
from typing import Literal

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


class VenueBookingChange(BaseModel):
    """What a Coordinator may change on one booking: its venue, and what they
    need of it. Every field is optional and only those sent are changed.

    There is no time: a booking has the Event's, so one sent anyway is ignored,
    not applied. A need sent blank goes back to what the Event says.
    """

    venue_id: int | None = None
    room_layout_preference: str | None = Field(default=None, max_length=2000)
    accessibility_needs: str | None = Field(default=None, max_length=2000)
    facilities_needs: str | None = Field(default=None, max_length=2000)

    @field_validator("room_layout_preference", "accessibility_needs", "facilities_needs")
    @classmethod
    def blank_is_not_given(cls, value: str | None) -> str | None:
        return (value or "").strip() or None


class VenueBookingCancel(BaseModel):
    """Cancel one booking. The reason is optional; blank counts as none."""

    reason: str | None = Field(default=None, max_length=2000)

    @field_validator("reason")
    @classmethod
    def blank_is_not_given(cls, value: str | None) -> str | None:
        return (value or "").strip() or None


class VenueBookingCancelAll(BaseModel):
    """Cancel every live booking of an event: exactly the ones the Coordinator
    was shown. The ids are what makes the second confirmation real -- a
    request without them cancels nothing."""

    booking_ids: list[int] = Field(min_length=1)
    reason: str | None = Field(default=None, max_length=2000)

    @field_validator("reason")
    @classmethod
    def blank_is_not_given(cls, value: str | None) -> str | None:
        return (value or "").strip() or None


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


class ConflictCancel(BaseModel):
    """Why Venue Staff cancel a flagged booking. Required, like keeping one."""

    reason: str = Field(max_length=2000)

    @field_validator("reason")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Give a reason for cancelling the conflicting booking.")
        return value


class ConflictKeep(BaseModel):
    """Why Venue Staff keep a flagged booking as it is. Required: blank is
    refused with a message by the router (422), not stored."""

    reason: str = Field(max_length=2000)

    @field_validator("reason")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Give a reason for keeping the conflicting booking.")
        return value


class VenueHoldIn(BaseModel):
    """What Venue Staff enter to place a tentative hold: when it lapses and
    what the Coordinator must complete before then. Both are required, so a
    missing one is a 422 naming its field; a past expiry is refused by the
    router the same way."""

    expires_at: datetime
    required_action: str = Field(max_length=2000)

    @field_validator("required_action")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Give the action the Event Coordinator must complete.")
        return value


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


class BookingConflict(BaseModel):
    """What a booking request clashes with: an approved booking of the same
    venue whose occupied period (event plus setup/turnaround) overlaps, or
    (kind "unavailability", SCRUM-93) a period Venue Staff marked the venue
    unavailable -- then there is no booking or event, and `reason` says why."""

    kind: Literal["booking", "unavailability"] = "booking"
    booking_id: int | None = None
    event_id: int | None = None
    event_name: str | None = None
    event_start: datetime
    event_end: datetime
    occupied_start: datetime
    occupied_end: datetime
    overlap_start: datetime
    overlap_end: datetime
    reason: str | None = None
    # Of the booking this clashes with: "approved" or "tentative_hold".
    status: str | None = None


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
    expires_at: datetime | None = None
    # Tentative holds only: what the Coordinator must complete before expiry.
    hold_action: str | None = None
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
    # The venue's setup / turnaround as of now (0 when not set) and the
    # resulting occupied period: start - setup .. end + turnaround.
    setup_minutes: int = 0
    turnaround_minutes: int = 0
    occupied_start: datetime
    occupied_end: datetime
    # True while a venue setup/turnaround change has left this approved
    # booking overlapping another (SCRUM-92); it stays approved.
    conflict_flagged: bool = False
    # Only filled for Venue Staff looking at a pending request, or at a
    # flagged approved booking: the other approved bookings it overlaps.
    # [] for everyone else and once decided.
    conflicts: list[BookingConflict] = []
