// Mirror of backend/app/schemas/event.py and models/enums.py EventStatus --
// keep the string values byte-identical. The backend is the authority on
// what a request may contain; nothing here is a security boundary.

import { apiFetch } from './api'

export const EventStatus = {
  DRAFT: 'draft',
  SUBMITTED: 'submitted',
  UNDER_REVIEW: 'under_review',
  CHANGES_REQUESTED: 'changes_requested',
  APPROVED: 'approved',
  REJECTED: 'rejected',
  PLANNING: 'planning',
  CONFIRMED: 'confirmed',
  COMPLETED: 'completed',
  CANCELLED: 'cancelled',
} as const
export type EventStatus = (typeof EventStatus)[keyof typeof EventStatus]

export const EVENT_STATUS_LABELS: Record<EventStatus, string> = {
  [EventStatus.DRAFT]: 'Draft',
  [EventStatus.SUBMITTED]: 'Submitted',
  [EventStatus.UNDER_REVIEW]: 'Under review',
  [EventStatus.CHANGES_REQUESTED]: 'Changes requested',
  [EventStatus.APPROVED]: 'Approved',
  [EventStatus.REJECTED]: 'Rejected',
  [EventStatus.PLANNING]: 'Planning',
  [EventStatus.CONFIRMED]: 'Confirmed',
  [EventStatus.COMPLETED]: 'Completed',
  [EventStatus.CANCELLED]: 'Cancelled',
}

/** Row shape for the Drafts / Submitted Requests lists. `name` is nullable
 *  for the same reason it is nullable in the database -- a draft may not
 *  have been named yet. */
export interface EventSummary {
  id: number
  name: string | null
  event_type: string | null
  proposed_start: string | null
  proposed_end: string | null
  expected_attendance: number | null
  status: EventStatus
  submitted_at: string | null
  updated_at: string
}

export interface EventDetail extends EventSummary {
  organiser_id: number
  coordinator_id: number | null
  purpose: string | null
  description: string | null
  programme: string | null
  venue_requirements: string | null
  room_layout_preference: string | null
  accessibility_needs: string | null
  equipment_requirements: string | null
  special_arrangements: string | null
  registration_enabled: boolean
  created_at: string
}

/** Every field optional -- a draft is allowed to be incomplete. */
export interface EventInput {
  name?: string | null
  purpose?: string | null
  event_type?: string | null
  description?: string | null
  programme?: string | null
  proposed_start?: string | null
  proposed_end?: string | null
  expected_attendance?: number | null
  venue_requirements?: string | null
  room_layout_preference?: string | null
  accessibility_needs?: string | null
  equipment_requirements?: string | null
  special_arrangements?: string | null
  registration_enabled?: boolean
}

export function listMyEvents(status?: EventStatus): Promise<EventSummary[]> {
  const query = status ? `?status=${status}` : ''
  return apiFetch(`/events${query}`) as Promise<EventSummary[]>
}

export function getEvent(id: number): Promise<EventDetail> {
  return apiFetch(`/events/${id}`) as Promise<EventDetail>
}

export function createEvent(input: EventInput): Promise<EventDetail> {
  return apiFetch('/events', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  }) as Promise<EventDetail>
}

export function updateEvent(id: number, input: EventInput): Promise<EventDetail> {
  return apiFetch(`/events/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  }) as Promise<EventDetail>
}

/** Submit for review. Rejects with an ApiError carrying `fields` when
 *  mandatory information is still missing. */
export function submitEvent(id: number): Promise<EventDetail> {
  return apiFetch(`/events/${id}/submit`, { method: 'POST' }) as Promise<EventDetail>
}

// --- date helpers -------------------------------------------------------
// <input type="datetime-local"> speaks "YYYY-MM-DDTHH:mm" in the viewer's
// own timezone, while the API speaks ISO-8601 with an offset. These two
// convert between them; both tolerate empty input, since a draft may have
// no date yet.

export function toDateTimeLocal(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function fromDateTimeLocal(value: string): string | null {
  if (!value) return null
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? null : d.toISOString()
}

/** Human-readable range for a list row, e.g. "2 Nov 2026, 09:00 – 17:00". */
export function formatRange(start: string | null, end: string | null): string {
  if (!start) return 'No date yet'
  const s = new Date(start)
  const date = s.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
  const time = (d: Date) => d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
  return end ? `${date}, ${time(s)} – ${time(new Date(end))}` : `${date}, ${time(s)}`
}
