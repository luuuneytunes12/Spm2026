from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.db import Base
from app.models.user import User


class CoordinatorAvailabilityHistory(Base):
    """One row per real change of a Coordinator's own availability.

    Written by PATCH /coordinators/me/availability whenever the value
    actually flips -- unlike EventStatusHistory (which needs an event_id
    and only gets written as a side effect of reassigning an event), this
    fires even when the Coordinator had zero active events at the time.
    """

    __tablename__ = "coordinator_availability_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    coordinator_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    is_available: Mapped[bool] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    coordinator: Mapped[User] = relationship(foreign_keys=[coordinator_id])
