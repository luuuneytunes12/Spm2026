"""Single source of truth for role and permission names.

Mirrored (identical string values) in `frontend/src/lib/roles.ts`. When you
rename or add a role/permission here, update that file too, plus the
native postgres `user_role` enum type in the database (see
`backend/sql/001_role_enum.sql` for how to add/rename a label -- it cannot
just be widened like a varchar). Nothing else in the backend should
reference these strings literally.
"""

from enum import StrEnum


class Role(StrEnum):
    ORGANISER = "organiser"  # Event Organiser -- highest privilege, admin-equivalent
    COORDINATOR = "coordinator"  # Event Coordinator
    VENUE_STAFF = "venue_staff"  # Venue Staff
    TECH_SUPPORT = "tech_support"  # Technical Support Staff (12 chars -- exactly at the limit)
    ATTENDEE = "attendee"  # Attendee


# Human-readable label for each role, since the slugs above are not
# presentable as-is (e.g. "venue_staff" -> "Venue Staff"). Used by the UI;
# never compared against or stored.
ROLE_LABELS: dict[Role, str] = {
    Role.ORGANISER: "Event Organiser",
    Role.COORDINATOR: "Event Coordinator",
    Role.VENUE_STAFF: "Venue Staff",
    Role.TECH_SUPPORT: "Technical Support Staff",
    Role.ATTENDEE: "Attendee",
}


class Permission(StrEnum):
    # One member per capability, grouped by domain.
    EVENT_READ = "event:read"
    EVENT_WRITE = "event:write"
    EVENT_APPROVE = "event:approve"
    VENUE_READ = "venue:read"
    VENUE_BOOK = "venue:book"
    VENUE_MANAGE = "venue:manage"
    EQUIPMENT_READ = "equipment:read"
    EQUIPMENT_MANAGE = "equipment:manage"
    REGISTRATION_READ = "registration:read"
    REGISTRATION_MANAGE = "registration:manage"


# Explicit per-role permission table. ORGANISER gets every permission (it
# is the admin-equivalent -- there is no separate admin role); each lower
# tier is written out explicitly rather than inheriting implicitly from
# the tier above it, so the whole grant surface for a role is visible in
# one place and easy to audit.
ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ORGANISER: frozenset(Permission),
    Role.COORDINATOR: frozenset(
        {
            Permission.EVENT_READ,
            Permission.EVENT_WRITE,
            Permission.VENUE_READ,
            Permission.VENUE_BOOK,
            Permission.EQUIPMENT_READ,
            Permission.REGISTRATION_READ,
            Permission.REGISTRATION_MANAGE,
        }
    ),
    Role.VENUE_STAFF: frozenset(
        {
            Permission.VENUE_READ,
            Permission.VENUE_MANAGE,
            Permission.EVENT_READ,
        }
    ),
    Role.TECH_SUPPORT: frozenset(
        {
            Permission.EQUIPMENT_READ,
            Permission.EQUIPMENT_MANAGE,
            Permission.EVENT_READ,
        }
    ),
    Role.ATTENDEE: frozenset(
        {
            Permission.EVENT_READ,
            Permission.VENUE_READ,
            Permission.REGISTRATION_READ,
        }
    ),
}

# Public registration must only ever create attendees; every other role is
# granted by an ORGANISER via PATCH /users/{id}/role.
DEFAULT_ROLE = Role.ATTENDEE


def role_has(role: Role, permission: Permission) -> bool:
    """Return whether `role` grants `permission`."""
    return permission in ROLE_PERMISSIONS.get(role, frozenset())
