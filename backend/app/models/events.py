from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, BigInteger, Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.db import Base
from app.models.enums import ChangeRequestStatus, EventStatus
from app.models.user import User

if TYPE_CHECKING:  # pragma: no cover - import cycle; models.equipment imports Event
    from app.models.equipment import EquipmentRequest


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    organiser_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT")
    )
    coordinator_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    # Nullable so an INCOMPLETE request can be saved as a draft -- an
    # Organiser may save before choosing a name or date. Mandatory-field
    # validation lives in the submit endpoint, not here, so that it can
    # report *which* fields are missing (see sql/003_events_draft_fields.sql).
    name: Mapped[str | None] = mapped_column(Text)
    purpose: Mapped[str | None] = mapped_column(Text)
    event_type: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    programme: Mapped[str | None] = mapped_column(Text)
    proposed_start: Mapped[datetime | None]
    proposed_end: Mapped[datetime | None]
    expected_attendance: Mapped[int | None]
    venue_requirements: Mapped[str | None] = mapped_column(Text)
    # The layout the event *asks for*; compared against
    # venues.supported_layouts during venue suitability checking.
    room_layout_preference: Mapped[str | None] = mapped_column(Text)
    accessibility_needs: Mapped[str | None] = mapped_column(Text)
    equipment_requirements: Mapped[str | None] = mapped_column(Text)
    special_arrangements: Mapped[str | None] = mapped_column(Text)
    registration_enabled: Mapped[bool] = mapped_column(default=False)
    # The window in which Attendees may register, set by the Coordinator when
    # they open registration on a confirmed event (sql/015). Null until then.
    registration_opens_at: Mapped[datetime | None]
    registration_closes_at: Mapped[datetime | None]
    status: Mapped[EventStatus] = mapped_column(
        Enum(EventStatus, name="event_status", create_type=False), default=EventStatus.draft
    )
    submitted_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    organiser: Mapped[User] = relationship(foreign_keys=[organiser_id])
    coordinator: Mapped[User | None] = relationship(foreign_keys=[coordinator_id])

    # The equipment the Organiser asked for, one row per catalogue item.
    #
    # `lazy="selectin"` rather than the default: EventOut.model_validate()
    # is called from six places in routers/events.py, and a lazy collection
    # would mean either six joinedload() calls to remember or an N+1 on
    # every event read. Declaring it here means no router has to know.
    #
    # `delete-orphan` makes "replace this event's lines" a plain assignment
    # -- PATCH sets the list and SQLAlchemy issues the DELETEs. The DB also
    # cascades on event deletion, but that only covers dropping the whole
    # event, not swapping one line for another.
    #
    # The class is named as a string because models.equipment imports Event;
    # a real import here would be a cycle.
    equipment_items: Mapped[list["EquipmentRequest"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        order_by="EquipmentRequest.id",
        lazy="selectin",
    )


class EventStatusHistory(Base):
    __tablename__ = "event_status_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("events.id", ondelete="CASCADE")
    )
    changed_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT")
    )
    from_status: Mapped[str | None] = mapped_column(Text)
    to_status: Mapped[str] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    event: Mapped[Event] = relationship()
    changed_by_user: Mapped[User] = relationship(foreign_keys=[changed_by])


class EventChangeRequest(Base):
    __tablename__ = "event_change_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("events.id", ondelete="CASCADE")
    )
    requested_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT")
    )
    reviewed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    description: Mapped[str] = mapped_column(Text)
    proposed_changes: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON, "sqlite")
    )
    status: Mapped[ChangeRequestStatus] = mapped_column(
        Enum(ChangeRequestStatus, name="change_request_status", create_type=False),
        default=ChangeRequestStatus.pending,
    )
    review_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    reviewed_at: Mapped[datetime | None]

    event: Mapped[Event] = relationship()
    requested_by_user: Mapped[User] = relationship(foreign_keys=[requested_by])
    reviewed_by_user: Mapped[User | None] = relationship(foreign_keys=[reviewed_by])
