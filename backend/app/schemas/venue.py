"""Schemas for viewing venues.

Read-only: this module describes what an internal user *sees* about a
venue. Creating and editing venues is VENUE_MANAGE and a separate story.
"""

from pydantic import BaseModel, ConfigDict


class VenueSummary(BaseModel):
    """One row of the venue list: enough to pick the right venue."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    location: str
    capacity: int
    is_active: bool


class VenueDetail(VenueSummary):
    """Everything needed to judge whether a venue suits an event.

    The three lists are returned as recorded, never null -- the columns
    default to an empty array, and "none recorded" is the UI's call.
    """

    supported_layouts: list[str]
    facilities: list[str]
    accessibility_features: list[str]
    operating_hours: str | None
