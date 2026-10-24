from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.event import EventIn


def _not_blank(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("A message is required.")
    return v


class ClarificationIn(BaseModel):
    """A Coordinator's clarification request."""

    message: str

    _clean = field_validator("message")(_not_blank)


class ClarificationReplyIn(BaseModel):
    """An Organiser's reply, optionally with amended Event Request fields
    (validated exactly like the draft form)."""

    message: str
    updates: EventIn | None = None

    _clean = field_validator("message")(_not_blank)


class ClarificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int
    kind: str
    message: str
    author_id: int
    author_name: str
    created_at: datetime
