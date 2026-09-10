from datetime import datetime

from sqlalchemy import BigInteger, Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.db import Base
from app.models.enums import RegistrationStatus
from app.models.events import Event
from app.models.users import User


class Registration(Base):
    __tablename__ = "registrations"
    __table_args__ = (UniqueConstraint("event_id", "attendee_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("events.id", ondelete="CASCADE")
    )
    attendee_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT")
    )
    status: Mapped[RegistrationStatus] = mapped_column(
        Enum(RegistrationStatus, name="registration_status", create_type=False),
        default=RegistrationStatus.registered,
    )
    registered_at: Mapped[datetime] = mapped_column(server_default=func.now())
    withdrawn_at: Mapped[datetime | None]

    event: Mapped[Event] = relationship()
    attendee: Mapped[User] = relationship(foreign_keys=[attendee_id])
