from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator, model_validator

# Import for its side effect: widens EmailStr's accepted domains.
import app.schemas.types  # noqa: F401

from app.core.communication import CommunicationPreference
from app.core.phone import PHONE_DIGIT_RANGE
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
    organisation: str | None
    phone_country_code: str | None
    phone_number: str | None
    communication_preference: str | None
    # Meaningful for a Coordinator; every other role carries it too (one
    # shared table) but never acts on it. See PATCH /coordinators/me/availability.
    is_available: bool
    created_at: datetime


class UserProfileUpdate(BaseModel):
    """Fields a signed-in user may change about themself via
    PATCH /users/me. Every field is optional so the client can send only
    what it means to change -- see the exclude_unset handling in the
    router. Sending an explicit null clears an optional field.

    Validation here is the single source of truth: it runs before the
    request handler ever touches the database, so an invalid value is
    rejected with nothing written, and no separate check is needed there.
    """

    name: str | None = None
    organisation: str | None = None
    email: EmailStr | None = None
    phone_country_code: str | None = None
    phone_number: str | None = None
    communication_preference: str | None = None

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Name cannot be blank.")
        return v

    @field_validator("phone_country_code")
    @classmethod
    def _known_country_code(cls, v: str | None) -> str | None:
        if v is not None and v not in PHONE_DIGIT_RANGE:
            raise ValueError("Unsupported country code.")
        return v

    @field_validator("phone_number")
    @classmethod
    def _valid_phone_number(cls, v: str | None, info) -> str | None:
        if v is None:
            return v
        if not v.isdigit():
            raise ValueError("Phone number must contain digits only.")
        # Declared after phone_country_code, so a code that passed its own
        # validation is already in `info.data`. If the code itself failed
        # (or was never sent), there is nothing to check the length
        # against -- that half of the error is reported on that field.
        country_code = info.data.get("phone_country_code")
        if country_code is None:
            return v
        low, high = PHONE_DIGIT_RANGE[country_code]
        if not (low <= len(v) <= high):
            expected = f"{low}" if low == high else f"{low}-{high}"
            raise ValueError(f"Phone number must have {expected} digits for this country code.")
        return v

    @field_validator("communication_preference")
    @classmethod
    def _known_preference(cls, v: str | None) -> str | None:
        if v is not None and v not in {p.value for p in CommunicationPreference}:
            raise ValueError("Unsupported communication preference.")
        return v

    @model_validator(mode="after")
    def _phone_fields_together(self) -> "UserProfileUpdate":
        has_code = self.phone_country_code is not None
        has_number = self.phone_number is not None
        if has_code != has_number:
            raise ValueError(
                "Provide both a country code and a phone number, or leave both blank."
            )
        return self


class MeOut(BaseModel):
    user: UserOut
    permissions: list[Permission]


class UserRoleUpdate(BaseModel):
    # Deliberately `str`, not `Role`: a role value in the database that is
    # not (or is no longer) a Role member must still serialize. Typing it
    # as the enum turns a renamed/removed label into a 500 on /auth/me.
    # Permission resolution already fails closed -- see permissions_for().
    role: str


class AvailabilityUpdate(BaseModel):
    """Body for PATCH /coordinators/me/availability."""

    is_available: bool


class AvailabilityHistoryEntry(BaseModel):
    """One row of GET /coordinators/me/availability-history."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    is_available: bool
    created_at: datetime
