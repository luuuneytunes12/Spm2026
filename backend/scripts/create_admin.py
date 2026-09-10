"""Seed the first Event Organiser.

Registration (`POST /auth/register`) always assigns `DEFAULT_ROLE`
(attendee), so there is no way to bootstrap the first Organiser (the
admin-equivalent role -- see `app/core/roles.py`) through the API. Run
this once against your Supabase database:

    cd backend
    uv run python scripts/create_admin.py "Jane Doe" jane@example.com

You'll be prompted for a password (or set ADMIN_PASSWORD to skip the
prompt, useful for CI/scripted setups).
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.db import SessionLocal  # noqa: E402
from app.core.roles import Role  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.user import User  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name")
    parser.add_argument("email")
    args = parser.parse_args()

    name = args.name.strip()
    email = args.email.strip().lower()
    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Organiser password: ")
    if len(password) < 8:
        print("Password must be at least 8 characters.", file=sys.stderr)
        raise SystemExit(1)

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == email).first()
        if existing is not None:
            existing.name = name
            existing.role = Role.ORGANISER.value
            existing.password_hash = hash_password(password)
            db.commit()
            print(f"Updated existing user {email} to role=organiser.")
            return

        user = User(name=name, email=email, password_hash=hash_password(password), role=Role.ORGANISER.value)
        db.add(user)
        db.commit()
        print(f"Created organiser user {email}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
