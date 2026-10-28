// Mirror of backend/app/core/departments.py -- keep slugs byte-identical.
// Rendering only; the backend rejects anything outside this list.

export const Department = {
  EVENTS_COORDINATION: 'events_coordination',
  VENUE_OPERATIONS: 'venue_operations',
  TECHNICAL_SUPPORT: 'technical_support',
  SAFETY_COMPLIANCE: 'safety_compliance',
} as const
export type Department = (typeof Department)[keyof typeof Department]

export const DEPARTMENT_LABELS: Record<Department, string> = {
  [Department.EVENTS_COORDINATION]: 'Events Coordination',
  [Department.VENUE_OPERATIONS]: 'Venue Operations',
  [Department.TECHNICAL_SUPPORT]: 'Technical Support',
  [Department.SAFETY_COMPLIANCE]: 'Safety & Compliance',
}

export const RESPONSIBILITIES_MAX_LENGTH = 1000

export function departmentLabel(value: string | null): string {
  return value && value in DEPARTMENT_LABELS ? DEPARTMENT_LABELS[value as Department] : '—'
}
