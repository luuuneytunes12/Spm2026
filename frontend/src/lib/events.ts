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

/** One line explaining what a status actually means -- shown next to the
 *  badge so "Submitted" reads as a stage in a process, not just a word. */
export const EVENT_STATUS_DESCRIPTIONS: Record<EventStatus, string> = {
  [EventStatus.DRAFT]: 'The Organiser is still filling this request in. It has not been submitted yet.',
  [EventStatus.SUBMITTED]: 'Submitted by the Organiser and waiting for a Coordinator to begin reviewing it.',
  [EventStatus.UNDER_REVIEW]: 'A Coordinator is reviewing the request against venue, equipment and accessibility requirements.',
  [EventStatus.CHANGES_REQUESTED]: 'A Coordinator has asked the Organiser to revise the request before it can proceed.',
  [EventStatus.APPROVED]: 'The request has been approved and is ready to move into planning.',
  [EventStatus.REJECTED]: 'The request was not approved. It will not proceed.',
  [EventStatus.PLANNING]: 'Approved and being planned -- venue, equipment and other logistics are being arranged.',
  [EventStatus.CONFIRMED]: 'Planning is complete. The event is confirmed to go ahead.',
  [EventStatus.COMPLETED]: 'The event has taken place.',
  [EventStatus.CANCELLED]: 'The event has been cancelled and will not proceed.',
}

/** The lifecycle a request moves through from a Coordinator's point of view,
 *  used to draw the progress timeline on the assigned-event screen.
 *
 *  DRAFT is deliberately excluded, even though it is the request's real
 *  first status. A Coordinator is only ever handed a request once it has
 *  left the Organiser's hands -- drafting is something that happens
 *  *before* their involvement starts, not a stage of the process they are
 *  tracking. Showing it as an achieved step would suggest it is part of
 *  what the Coordinator watches over, when it is really the Organiser's
 *  business alone. (The activity log lower on the page still shows the
 *  real Draft -> Submitted transition -- that is a factual record of what
 *  happened, which is a different thing from "where is this in the
 *  Coordinator's process".)
 *
 *  Three further statuses are deliberately NOT on this list --
 *  CHANGES_REQUESTED, REJECTED and CANCELLED are exits from the path, not
 *  stages of it, and each can branch off from more than one point (a
 *  cancellation can happen from Submitted just as easily as from Planning).
 *  Rendering them as a fixed step would claim an order they don't actually
 *  have -- see EVENT_STATUS_BRANCH_TONE and AssignedEventView's
 *  StatusTimeline, which instead reads where a branch departed from off the
 *  event's own activity log. */
export const EVENT_STATUS_PIPELINE: readonly EventStatus[] = [
  EventStatus.SUBMITTED,
  EventStatus.UNDER_REVIEW,
  EventStatus.APPROVED,
  EventStatus.PLANNING,
  EventStatus.CONFIRMED,
  EventStatus.COMPLETED,
]

/** Visual severity for a status that leaves the main pipeline rather than
 *  advancing along it. Absent for every status that IS on the pipeline. */
export const EVENT_STATUS_BRANCH_TONE: Partial<Record<EventStatus, 'warning' | 'danger'>> = {
  [EventStatus.CHANGES_REQUESTED]: 'warning',
  [EventStatus.REJECTED]: 'danger',
  [EventStatus.CANCELLED]: 'danger',
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

/** Who a Coordinator contacts about an event assigned to them. `users`
 *  carries no phone number, so `email` is the whole of "contact details". */
export interface OrganiserContact {
  id: number
  name: string
  email: string
}

/** One line of an event's activity log, from `event_status_history`.
 *  `from_status`/`to_status` are plain strings rather than EventStatus: they
 *  are a historical record, and a status renamed tomorrow must not make
 *  yesterday's log unrenderable. */
export interface ActivityEntry {
  from_status: string | null
  to_status: string
  note: string | null
  changed_by_name: string | null
  created_at: string
}

/** What GET /events/assigned/{id} returns -- the whole request, plus the two
 *  things a Coordinator needs that an Organiser viewing their own draft does
 *  not: who to contact, and what has happened to it so far. */
export interface AssignedEventDetail extends EventDetail {
  organiser: OrganiserContact
  activity: ActivityEntry[]
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

/** The events the signed-in Coordinator has been assigned. Scoped server-side
 *  to `coordinator_id == me`, so there is no "whose events?" parameter. */
export function listAssignedEvents(): Promise<EventSummary[]> {
  return apiFetch('/events/assigned') as Promise<EventSummary[]>
}

/** Full detail of one assigned event. Rejects with a 404 ApiError when the
 *  event is not assigned to the caller -- deliberately the same response as
 *  an event id that does not exist. */
export function getAssignedEvent(id: number): Promise<AssignedEventDetail> {
  return apiFetch(`/events/assigned/${id}`) as Promise<AssignedEventDetail>
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

/** Absolute date and time, e.g. "10 Sep 2026, 14:32". Used wherever an exact
 *  moment matters more than a range -- activity log lines, "submitted on". */
export function formatTimestamp(iso: string | null): string | null {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

/** Human-readable range for a list row, e.g. "2 Nov 2026, 09:00 – 17:00". */
export function formatRange(start: string | null, end: string | null): string {
  if (!start) return 'No date yet'
  const s = new Date(start)
  const date = s.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
  const time = (d: Date) => d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
  return end ? `${date}, ${time(s)} – ${time(new Date(end))}` : `${date}, ${time(s)}`
}
