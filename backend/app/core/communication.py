"""How a user prefers to be contacted.

Mirrored (identical string values) in `frontend/src/lib/communication.ts`.
A small, fixed list -- unlike Role, this gates nothing, so a plain enum
with no permission table is enough.
"""

from enum import StrEnum


class CommunicationPreference(StrEnum):
    EMAIL = "email"
    SMS = "sms"
    PHONE_CALL = "phone_call"
