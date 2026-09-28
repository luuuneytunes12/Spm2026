from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NotificationOut(BaseModel):
    """One notification for the signed-in user, newest first."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int | None
    type: str
    message: str
    is_read: bool
    created_at: datetime


class MarkReadIn(BaseModel):
    """Ids to mark as read -- one, a hand-picked few, or every one on screen.

    Capped so a single request cannot ask for an unbounded UPDATE; "mark
    everything" has its own endpoint that needs no ids at all.
    """

    ids: list[int] = Field(min_length=1, max_length=500)


class MarkReadOut(BaseModel):
    """How many notifications actually changed from unread to read."""

    updated: int
