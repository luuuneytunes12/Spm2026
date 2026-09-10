from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

# Import for its side effect: widens EmailStr's accepted domains.
import app.schemas.types  # noqa: F401

from app.core.roles import Permission, Role


class UserOut(BaseModel):
    """Public user representation. Never include `password_hash` here."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    # Deliberately `str`, not `Role`: a role value in the database that is
    # not (or is no longer) a Role member must still serialize. Typing it
    # as the enum turns a renamed/removed label into a 500 on /auth/me.
    # Permission resolution already fails closed -- see permissions_for().
    role: str
    created_at: datetime


class MeOut(BaseModel):
    user: UserOut
    permissions: list[Permission]


class UserRoleUpdate(BaseModel):
    # Deliberately `str`, not `Role`: a role value in the database that is
    # not (or is no longer) a Role member must still serialize. Typing it
    # as the enum turns a renamed/removed label into a 500 on /auth/me.
    # Permission resolution already fails closed -- see permissions_for().
    role: str
