from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationOut(BaseModel):
    """One notification belonging to the caller."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int | None
    type: str
    message: str
    is_read: bool
    created_at: datetime
