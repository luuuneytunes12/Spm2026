"""Schemas for viewing, searching and filtering venues.

Read-only: this module describes what an internal user *sees* about a
venue. Creating and editing venues is VENUE_MANAGE and a separate story.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from app.models.enums import UnavailabilityReason


class VenueSummary(BaseModel):
    """One row of the venue list or a search result: enough to decide
    whether a venue is worth opening."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    location: str
    capacity: int
    # Shown on every search result (Search and Filter Venues, AC4), so a
    # Coordinator can rule a venue in or out without opening it.
    facilities: list[str]
    is_active: bool


class VenueDetail(VenueSummary):
    """Everything needed to judge whether a venue suits an event.

    The lists are returned as recorded, never null -- the columns default to
    an empty array, and "none recorded" is the UI's call.
    """

    supported_layouts: list[str]
    accessibility_features: list[str]
    operating_hours: str | None
    # Whole minutes of preparation before / reset after an Event. Null means
    # "not set": 0 is used when working out availability.
    setup_minutes: int | None = None
    turnaround_minutes: int | None = None
    # Only in the response to saving setup/turnaround: how many future
    # bookings that save newly flagged as conflicting, and how many earlier
    # flags it cleared. Null everywhere else.
    recheck: "RecheckSummary | None" = None


class RecheckSummary(BaseModel):
    flagged: int
    cleared: int


class SetupTurnaroundUpdate(BaseModel):
    """What Venue Staff save: both values, whole minutes, zero or more.

    Strict: a float such as 10.5 or the string "10" is refused, not rounded
    or coerced, and so is null/empty -- a partial or guessed value would
    silently change availability.
    """

    model_config = ConfigDict(extra="forbid")

    setup_minutes: StrictInt = Field(ge=0)
    turnaround_minutes: StrictInt = Field(ge=0)


class VenueFilterOptions(BaseModel):
    """The values the search filters can offer.

    Layouts, facilities and accessibility features are free text typed by
    Venue Staff, not a fixed vocabulary, so the choices are whatever has
    actually been recorded -- each value once, ignoring capitalisation, and
    sorted. A hard-coded list would drift from the data the moment someone
    recorded a new facility.
    """

    layouts: list[str]
    facilities: list[str]
    accessibility_features: list[str]


class BusyPeriod(BaseModel):
    """A time the venue cannot be booked: an approved booking's occupied
    period (event widened by setup/turnaround) or a recorded closure.

    event_* are set for bookings; event_name only for Venue Staff."""

    kind: Literal["booking", "tentative_hold", "closure"]
    start: datetime
    end: datetime
    event_start: datetime | None = None
    event_end: datetime | None = None
    event_name: str | None = None
    # Closures only (SCRUM-93): why, and Venue Staff's optional details.
    reason_category: str | None = None
    reason: str | None = None
    # Tentative holds only: when the hold lapses.
    expires_at: datetime | None = None
    # Tentative holds only, Venue Staff only: what the Coordinator must do.
    hold_action: str | None = None


class UnavailabilityIn(BaseModel):
    """What Venue Staff save: a period and a reason category (SCRUM-93).

    The end is checked against the start in the router so the 422 can name
    the date field. `reason` is optional details.
    """

    model_config = ConfigDict(extra="forbid")

    start_time: datetime
    end_time: datetime
    reason_category: UnavailabilityReason
    reason: str | None = Field(default=None, max_length=2000)

    @field_validator("reason")
    @classmethod
    def blank_is_not_given(cls, value: str | None) -> str | None:
        return (value or "").strip() or None


class AffectedBooking(BaseModel):
    """A future booking inside an unavailability period. Identified only:
    its status and its Event are untouched."""

    booking_id: int
    event_id: int
    event_name: str
    status: str
    start_time: datetime
    end_time: datetime
    flagged: bool


class VenueAvailabilityItem(BaseModel):
    id: int
    kind: Literal["confirmed_booking", "tentative_hold", "unavailability"]
    start_time: datetime
    end_time: datetime
    event_id: int | None = None
    event_name: str | None = None
    # The period it holds the venue for: the event widened by the venue's
    # setup and turnaround (equal to start/end_time for a closure).
    occupied_start: datetime | None = None
    occupied_end: datetime | None = None
    reason_category: str | None = None
    reason: str | None = None
    expires_at: datetime | None = None
    # Tentative holds only, Venue Staff only: what the Coordinator must do.
    hold_action: str | None = None
    conflicts_with_unavailability: bool = False


class VenueAvailabilityOut(BaseModel):
    venue_id: int
    start: datetime
    end: datetime
    busy: list[BusyPeriod]
    items: list[VenueAvailabilityItem]


class VenueSuitabilityCheck(BaseModel):
    category: Literal["capacity", "layout", "accessibility", "facility", "operating_hours"]
    requirement: str
    available: str
    met: bool
    message: str


class VenueSuitabilityOut(BaseModel):
    venue_id: int
    event_id: int
    event_name: str | None
    suitable: bool
    checks: list[VenueSuitabilityCheck]


class EventVenueSuitabilityItem(BaseModel):
    booking_id: int
    venue_id: int
    venue_name: str
    expected_attendance: int | None
    suitable: bool
    checks: list[VenueSuitabilityCheck]


class CombinedVenueCapacityCheck(BaseModel):
    required_capacity: int | None
    available_capacity: int
    met: bool
    message: str


class EventVenueSuitabilityOut(BaseModel):
    event_id: int
    event_name: str | None
    suitable: bool
    venues: list[EventVenueSuitabilityItem]
    combined_capacity: CombinedVenueCapacityCheck


class UnavailabilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    venue_id: int
    start_time: datetime
    end_time: datetime
    reason_category: str
    reason: str | None
    updated_at: datetime | None = None
    # Venue Staff only; empty for anyone else.
    affected_bookings: list[AffectedBooking] = []
    # Only in the response to a save / end: bookings newly flagged and earlier
    # flags cleared by it.
    recheck: RecheckSummary | None = None
