// Mirror of backend/app/core/roles.py — keep string values byte-identical.
// This map is for *rendering* only; the backend is the real gate on every
// request. When a role/permission is renamed, edit both files (plus the
// SQL CHECK constraint / UPDATE for any stored `role` values, see
// backend/sql/001_role_constraint.sql).

export const Role = {
  ORGANISER: 'organiser',
  COORDINATOR: 'coordinator',
  VENUE_STAFF: 'venue_staff',
  TECH_SUPPORT: 'tech_support',
  ATTENDEE: 'attendee',
  COORDINATOR_LEAD: 'event_coordinator_lead',
  SAFETY_OFFICER: 'safety_officer',
} as const
export type Role = (typeof Role)[keyof typeof Role]

// Human-readable label for each role — the slugs above are not
// presentable as-is (e.g. "venue_staff" -> "Venue Staff").
export const ROLE_LABELS: Record<Role, string> = {
  [Role.ORGANISER]: 'Event Organiser',
  [Role.COORDINATOR]: 'Event Coordinator',
  [Role.VENUE_STAFF]: 'Venue Staff',
  [Role.TECH_SUPPORT]: 'Technical Support Staff',
  [Role.ATTENDEE]: 'Attendee',
  [Role.COORDINATOR_LEAD]: 'Event Coordinator Lead',
  [Role.SAFETY_OFFICER]: 'Safety Officer',
}

export const Permission = {
  EVENT_READ: 'event:read',
  EVENT_WRITE: 'event:write',
  EVENT_APPROVE: 'event:approve',
  VENUE_READ: 'venue:read',
  VENUE_BOOK: 'venue:book',
  VENUE_MANAGE: 'venue:manage',
  EQUIPMENT_READ: 'equipment:read',
  EQUIPMENT_MANAGE: 'equipment:manage',
  REGISTRATION_READ: 'registration:read',
  REGISTRATION_MANAGE: 'registration:manage',
  USER_READ: 'user:read',
  ROLE_ASSIGN: 'role:assign',
  ASSIGNMENT_MANAGE: 'assignment:manage',
  ASSIGNMENT_VIEW_ALL: 'assignment:view_all',
} as const
export type Permission = (typeof Permission)[keyof typeof Permission]

export const ROLE_PERMISSIONS: Record<Role, readonly Permission[]> = {
  [Role.ORGANISER]: Object.values(Permission),
  [Role.COORDINATOR]: [
    Permission.EVENT_READ,
    Permission.EVENT_WRITE,
    Permission.VENUE_READ,
    Permission.VENUE_BOOK,
    Permission.EQUIPMENT_READ,
    Permission.REGISTRATION_READ,
    Permission.REGISTRATION_MANAGE,
  ],
  [Role.VENUE_STAFF]: [Permission.VENUE_READ, Permission.VENUE_MANAGE, Permission.EVENT_READ],
  [Role.TECH_SUPPORT]: [Permission.EQUIPMENT_READ, Permission.EQUIPMENT_MANAGE, Permission.EVENT_READ],
  [Role.ATTENDEE]: [Permission.EVENT_READ, Permission.VENUE_READ, Permission.REGISTRATION_READ],
  // A Coordinator's grants plus assignment powers (mirrors CoordinatorLeadProfile).
  [Role.COORDINATOR_LEAD]: [
    ...[
      Permission.EVENT_READ,
      Permission.EVENT_WRITE,
      Permission.VENUE_READ,
      Permission.VENUE_BOOK,
      Permission.EQUIPMENT_READ,
      Permission.REGISTRATION_READ,
      Permission.REGISTRATION_MANAGE,
    ],
    Permission.ASSIGNMENT_MANAGE,
    Permission.ASSIGNMENT_VIEW_ALL,
  ],
  // Mirrors the backend: a Safety Officer may only read events for now.
  [Role.SAFETY_OFFICER]: [Permission.EVENT_READ],
}

export function roleHas(role: Role, permission: Permission): boolean {
  return ROLE_PERMISSIONS[role]?.includes(permission) ?? false
}

// Single source of truth for "which page does this role land on" — used by
// the /my redirect route and by Dashboard's link to the user's own page.
export const ROLE_HOME_PATH: Record<Role, string> = {
  [Role.ORGANISER]: '/organiser',
  [Role.COORDINATOR]: '/coordinator',
  [Role.VENUE_STAFF]: '/venue-staff',
  [Role.TECH_SUPPORT]: '/tech-support',
  [Role.ATTENDEE]: '/attendee',
  [Role.COORDINATOR_LEAD]: '/coordinator-lead',
  [Role.SAFETY_OFFICER]: '/safety-checks',
}

// Where a notification's `event_id` should link to for the signed-in
// role's own event detail page (the one with that event's Activity Log).
// Only Organiser and Coordinator have one today — everyone else gets no
// link rather than a guess that would 404 or hit RequireRole's /forbidden.
const EVENT_DETAIL_PATH: Partial<Record<Role, (eventId: number) => string>> = {
  [Role.ORGANISER]: (eventId) => `/organiser/events/${eventId}`,
  [Role.COORDINATOR]: (eventId) => `/coordinator/events/${eventId}`,
}

export function eventDetailPath(role: Role, eventId: number): string | null {
  return EVENT_DETAIL_PATH[role]?.(eventId) ?? null
}
