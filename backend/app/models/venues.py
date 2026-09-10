from datetime import datetime

from sqlalchemy import ARRAY, BigInteger, Enum, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.db import Base
from app.models.enums import BookingStatus
from app.models.events import Event
from app.models.users import User


class Venue(Base):
    __tablename__ = "venues"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(Text)
    capacity: Mapped[int]
    facilities: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    accessibility_features: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    supported_layouts: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    operating_hours: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True)


class VenueBooking(Base):
    __tablename__ = "venue_bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("events.id", ondelete="CASCADE")
    )
    venue_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("venues.id", ondelete="RESTRICT")
    )
    requested_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT")
    )
    reviewed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    start_time: Mapped[datetime]
    end_time: Mapped[datetime]
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus, name="booking_status", create_type=False),
        default=BookingStatus.pending,
    )
    decision_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    reviewed_at: Mapped[datetime | None]

    event: Mapped[Event] = relationship()
    venue: Mapped[Venue] = relationship()
    requested_by_user: Mapped[User] = relationship(foreign_keys=[requested_by])
    reviewed_by_user: Mapped[User | None] = relationship(foreign_keys=[reviewed_by])


class VenueUnavailability(Base):
    __tablename__ = "venue_unavailability"

    id: Mapped[int] = mapped_column(primary_key=True)
    venue_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("venues.id", ondelete="CASCADE")
    )
    start_time: Mapped[datetime]
    end_time: Mapped[datetime]
    reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT")
    )

    venue: Mapped[Venue] = relationship()
    created_by_user: Mapped[User] = relationship(foreign_keys=[created_by])
