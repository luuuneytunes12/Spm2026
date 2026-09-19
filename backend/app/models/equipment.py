from datetime import datetime

from sqlalchemy import BigInteger, Enum, ForeignKey, Text
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

    event: Mapped[Event] = relationship()
    equipment: Mapped[Equipment] = relationship()
    reviewed_by_user: Mapped[User | None] = relationship(foreign_keys=[reviewed_by])
