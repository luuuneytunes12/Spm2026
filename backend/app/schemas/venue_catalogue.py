"""Schemas for adding and editing Venues in the catalogue (SCRUM-108)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from app.schemas.venue import RecheckSummary, VenueDetail  # noqa: F401  (resolves VenueDetail's forward ref)


def _clean_list(values: list[str]) -> list[str]:
    """Trim, drop blanks and repeats (ignoring capitalisation), keep order."""
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = (value or "").strip()
        if text and text.casefold() not in seen:
            seen.add(text.casefold())
            out.append(text)
    return out


class VenueIn(BaseModel):
    """The whole of a Venue's catalogue details, as Venue Staff save them.

    Required: name, location, capacity (a whole number above zero), operating
    hours and at least one supported room layout. Facilities and accessibility
    features may be empty ("none"). Strict about capacity: 10.5 or "10" is
    refused rather than coerced.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    location: str = Field(min_length=1, max_length=500)
    capacity: StrictInt = Field(gt=0)
    facilities: list[str] = []
    accessibility_features: list[str] = []
    supported_layouts: list[str] = Field(min_length=1)
    operating_hours: str = Field(min_length=1, max_length=2000)

    @field_validator("name", "location", "operating_hours", mode="before")
    @classmethod
    def trimmed_not_blank(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("This detail is required.")
        return value

    @field_validator("facilities", "accessibility_features", mode="after")
    @classmethod
    def clean_optional_list(cls, value: list[str]) -> list[str]:
        return _clean_list(value)

    @field_validator("supported_layouts", mode="after")
    @classmethod
    def clean_layouts(cls, value: list[str]) -> list[str]:
        cleaned = _clean_list(value)
        if not cleaned:
            raise ValueError("At least one supported room layout is required.")
        return cleaned


class FlaggedBookingOut(BaseModel):
    booking_id: int
    event_id: int
    event_name: str | None
    reason: str


class VenueSaved(VenueDetail):
    """A saved Venue, plus the Venue Bookings this save flagged for review
    (kept, never removed)."""

    flagged_bookings: list[FlaggedBookingOut] = []


VenueSaved.model_rebuild()


class VenueActivityOut(BaseModel):
    id: int
    venue_id: int
    venue_name: str
    note: str
    changed_by: str | None
    created_at: datetime
