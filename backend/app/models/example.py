from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Item(Base):
    """Example model. Swap for your real schema, or drop this
    file entirely if you're managing the schema via Supabase
    migrations/SQL editor instead of SQLAlchemy models."""

    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
