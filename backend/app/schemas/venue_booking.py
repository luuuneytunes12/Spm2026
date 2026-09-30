"""Schemas for venue booking requests (Coordinator -> Venue Staff)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import BookingStatus


class VenueBookingCreate(BaseModel):
    """What a Coordinator sends. The venue is the only choice they make: the
    timing and requirements come from the event itself, so the request can
    never disagree with what the Organiser asked for.

    `venue_id` is optional here so that "no venue selected" reaches the
    router and is refused with a message, rather than as a bare schema error.
    """

    venue_id: int | None = None


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
    accessibility or facility needs."""

    id: int
    status: BookingStatus
    created_at: datetime
    event: BookingEventRef
    venue: BookingVenueRef
    start_time: datetime
    end_time: datetime
    expected_attendance: int | None
    room_layout_preference: str | None
    accessibility_needs: str | None
    venue_requirements: str | None
    requested_by: BookingPerson
