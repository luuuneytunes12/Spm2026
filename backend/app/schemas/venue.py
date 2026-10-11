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

    kind: Literal["booking", "closure"]
    start: datetime
    end: datetime
    event_start: datetime | None = None
    event_end: datetime | None = None
    event_name: str | None = None
    # Closures only (SCRUM-93): why, and Venue Staff's optional details.
    reason_category: str | None = None
    reason: str | None = None


class VenueAvailability(BaseModel):
    venue_id: int
    busy: list[BusyPeriod]


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
