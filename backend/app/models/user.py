from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.communication import CommunicationPreference
from app.core.db import Base
from app.core.roles import DEFAULT_ROLE, Role

# This model is intentionally a thin mirror of the *existing* live
# `users` table (verified by introspection) -- do not "improve" its
# shape here. In particular: `id` is a bigint identity column (not a
# UUID), there is no `is_active` column, and there is no `updated_at`
# column. Any query touching either non-existent column will fail
# against the real database.
#
# `is_available` is a deliberate addition beyond that mirror -- see
# sql/004_coordinator_availability.sql. It backs the Coordinator's "mark
# myself unavailable" toggle; every other role's row carries it too (one
# shared table) but never reads or writes it.
#
# `organisation`, `phone_country_code`, `phone_number` and
# `communication_preference` were added for the "Edit User Profile" story
# -- see sql/009_user_profile_fields.sql for the live-database migration.
# All four are nullable: every existing user row predates them.


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
    is_available: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    organisation: Mapped[str | None] = mapped_column(String, nullable=True)
    # National number only, digits, no dial code -- paired with
    # `phone_country_code` (e.g. "+65"). Kept as two plain string columns
    # rather than one E.164 value so the UI can re-populate the country
    # <select> and the number input independently.
    phone_country_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    communication_preference: Mapped[str | None] = mapped_column(
        PGEnum(
            *(p.value for p in CommunicationPreference),
            name="communication_preference",
            create_type=False,
        ).with_variant(String(32), "sqlite"),
        nullable=True,
    )
