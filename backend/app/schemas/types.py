"""Shared Pydantic field types.

`EmailStr` delegates to the `email_validator` package, which by default
rejects RFC 6762 / RFC 2606 special-use domains -- including `.local`,
which is exactly what a LAN or campus address like `admin@cs.local` uses.
That is correct for a public signup form but wrong for an internal
deployment, so we narrow the blocklist to the names that can never be a
real mailbox and leave the rest addressable.

`email_validator` exposes this list as a module-level global and documents
overriding it as the supported knob; there is no per-call parameter as of
2.3.0. Mutating it here (once, at import) applies process-wide, which is
the intent -- every schema should agree on what a valid address is.
"""

import email_validator

# Kept blocked: `invalid` (reserved as permanently unresolvable), `onion`
# (Tor hidden services), `arpa` (reverse-DNS infrastructure).
# Unblocked: `local`, `localhost`, `test` -- routine in LAN, container and
# test-fixture addresses.
_ALLOWED_SPECIAL_USE = {"local", "localhost", "test"}

email_validator.SPECIAL_USE_DOMAIN_NAMES = [
    name for name in email_validator.SPECIAL_USE_DOMAIN_NAMES if name not in _ALLOWED_SPECIAL_USE
]
