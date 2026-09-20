from datetime import datetime

from sqlalchemy import BigInteger, Enum, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.db import Base
from app.models.enums import EquipmentOperationalStatus, EquipmentStatus
from app.models.events import Event
from app.models.user import User


class Equipment(Base):
    __tablename__ = "equipment"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    # The equipment "type" the catalogue is filtered by.
    category: Mapped[str | None] = mapped_column(Text)
    # What the item is, in plain language. Distinct from technical_specs,
    # which holds model numbers, wattage and connector types.
    description: Mapped[str | None] = mapped_column(Text)
    total_quantity: Mapped[int]
    # Where the item is physically stored -- equipment held at another
    # venue may not be usable for a given event.
    location: Mapped[str | None] = mapped_column(Text)
    operational_status: Mapped[EquipmentOperationalStatus] = mapped_column(
        Enum(
            EquipmentOperationalStatus,
            name="equipment_operational_status",
            create_type=False,
        ),
        default=EquipmentOperationalStatus.available,
    )
    technical_specs: Mapped[str | None] = mapped_column(Text)


class EquipmentRequest(Base):
    __tablename__ = "equipment_requests"

    # Mirrors sql/007. Declared on the model as well as in the migration so
    # the in-memory SQLite database the tests build from this metadata has
    # it too -- otherwise a constraint violation is something only
    # production can discover.
    __table_args__ = (
        UniqueConstraint(
            "event_id", "equipment_id", name="equipment_requests_event_equipment_key"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("events.id", ondelete="CASCADE")
    )
    equipment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("equipment.id", ondelete="RESTRICT")
    )
    reviewed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    quantity_requested: Mapped[int]
    technical_requirements: Mapped[str | None] = mapped_column(Text)
    status: Mapped[EquipmentStatus] = mapped_column(
        Enum(EquipmentStatus, name="equipment_status", create_type=False),
        default=EquipmentStatus.requested,
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    reviewed_at: Mapped[datetime | None]

    event: Mapped[Event] = relationship(back_populates="equipment_items")
    # Eager: every read of a line wants the item's name to show a person,
    # and lines are always read as a set. Lazy here would be an N+1 behind
    # Event.equipment_items.
    equipment: Mapped[Equipment] = relationship(lazy="joined")
    reviewed_by_user: Mapped[User | None] = relationship(foreign_keys=[reviewed_by])

    # Catalogue fields, flattened onto the line.
    #
    # A line is only ever shown as "<name> -- <category> x <qty>", and
    # pydantic's from_attributes resolves plain properties, so exposing
    # these two saves every response schema from nesting a whole Equipment
    # object -- which would also drip location, condition and stock levels
    # into replies that have no business carrying them.
    @property
    def equipment_name(self) -> str:
        return self.equipment.name

    @property
    def equipment_category(self) -> str | None:
        return self.equipment.category
