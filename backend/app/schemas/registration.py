from datetime import datetime

from pydantic import BaseModel

from app.models.enums import RegistrationStatus


class RegistrableEvent(BaseModel):
    """One event as an Attendee sees it: enough to recognise it, whether
    registration is open right now, and where the caller stands.

    `my_status` is null when the caller has never registered. Both flags
    are computed server-side so the UI never re-derives the "is it open?"
    rule -- see `registration_open` in routers/registrations.py.
    """

    id: int
    name: str | None
    proposed_start: datetime | None
    proposed_end: datetime | None
    registration_open: bool
    my_status: RegistrationStatus | None
