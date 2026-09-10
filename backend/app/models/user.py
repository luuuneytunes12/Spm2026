from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.roles import DEFAULT_ROLE, Role

# This model is intentionally a thin mirror of the *existing* live
# `users` table (verified by introspection) -- do not "improve" its
# shape here. In particular: `id` is a bigint identity column (not a
# UUID), there is no `is_active` column, and there is no `updated_at`
# column. Any query touching either non-existent column will fail
# against the real database.


class User(Base):
    __tablename__ = "users"

    # GENERATED ALWAYS AS IDENTITY on the live table -- an explicit id can
    # never be supplied on insert, so let the database assign it.
    # BigInteger on Postgres (matches the live column); SQLite has no
    # true bigint and only auto-increments a rowid-aliased INTEGER
    # primary key, hence the per-dialect variant (needed for tests).
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    # `role` is a NATIVE postgres enum type (`user_role`), not a varchar --
    # binding a plain string makes postgres reject the INSERT with
    # "column role is of type user_role but expression is of type character
    # varying". create_type=False because the type already exists and is
    # owned by the database, not by this model; adding a role means
    # `ALTER TYPE user_role ADD VALUE ...` (see sql/001_role_enum.sql).
    # SQLite (tests) has no enum type, so it falls back to a plain string.
    role: Mapped[str] = mapped_column(
        PGEnum(*(r.value for r in Role), name="user_role", create_type=False).with_variant(
            String(32), "sqlite"
        ),
        nullable=False,
        default=DEFAULT_ROLE.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
