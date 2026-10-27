from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.db import Base
from app.models.events import Event
from app.models.user import User


class EventClarification(Base):
    """One message in the clarification exchange on an Event: the
    Coordinator's request, or the Organiser's reply to it."""

    __tablename__ = "event_clarifications"
    __table_args__ = (CheckConstraint("kind in ('request', 'reply')", name="ck_event_clarifications_kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("events.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    author_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    event: Mapped[Event] = relationship()
    author: Mapped[User] = relationship(foreign_keys=[author_id])
