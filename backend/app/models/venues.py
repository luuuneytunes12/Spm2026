from datetime import datetime

from sqlalchemy import (
    ARRAY,
    JSON,
    BigInteger,
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.db import Base
from app.models.enums import BookingStatus
from app.models.events import Event
from app.models.user import User


class Venue(Base):
    __tablename__ = "venues"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(Text)
    capacity: Mapped[int]
    facilities: Mapped[list[str]] = mapped_column(
        ARRAY(Text).with_variant(JSON, "sqlite"), default=list
    )
    accessibility_features: Mapped[list[str]] = mapped_column(
        ARRAY(Text).with_variant(JSON, "sqlite"), default=list
    )
    supported_layouts: Mapped[list[str]] = mapped_column(
        ARRAY(Text).with_variant(JSON, "sqlite"), default=list
    )
    operating_hours: Mapped[str | None] = mapped_column(Text)
    # Shown to the Safety Officer when judging an event's arrangement
    # (see sql/017_safety_check.sql).
    emergency_access: Mapped[str | None] = mapped_column(Text)
    known_restrictions: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True)


class VenueBooking(Base):
    __tablename__ = "venue_bookings"
    __table_args__ = (
        CheckConstraint(
            "status != 'tentative_hold' OR expires_at IS NOT NULL",
            name="ck_venue_booking_hold_requires_expiry",
        ),
        # An event may hold several live requests, but only one per venue,
        # enforced by the database as well as the API (see
        # sql/019_venue_bookings_many_per_event.sql).
        Index(
            "uq_venue_bookings_one_live_per_event_venue",
            "event_id",
            "venue_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'approved')"),
            sqlite_where=text("status IN ('pending', 'approved')"),
        ),
    )

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
    expires_at: Mapped[datetime | None]
    decision_notes: Mapped[str | None] = mapped_column(Text)
    # What Venue Staff offer instead when rejecting -- another venue, another
    # time (see sql/014_venue_bookings_suggested_alternative.sql).
    suggested_alternative: Mapped[str | None] = mapped_column(Text)
    # Set by a Safety Officer who wants this booking looked at again. The
    # booking stays approved -- and keeps the venue held -- until Venue Staff
    # re-approve (clearing it) or reject it. Null means nothing outstanding.
    safety_recheck_reason: Mapped[str | None] = mapped_column(Text)
    # What the Coordinator asked of THIS venue (sql/019). Null means "as the
    # Event says", which is how bookings made before 019 read.
    room_layout_preference: Mapped[str | None] = mapped_column(Text)
    accessibility_needs: Mapped[str | None] = mapped_column(Text)
    facilities_needs: Mapped[str | None] = mapped_column(Text)
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
