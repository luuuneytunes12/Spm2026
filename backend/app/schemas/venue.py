"""Schemas for viewing, searching and filtering venues.

Read-only: this module describes what an internal user *sees* about a
venue. Creating and editing venues is VENUE_MANAGE and a separate story.
"""

from pydantic import BaseModel, ConfigDict


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
