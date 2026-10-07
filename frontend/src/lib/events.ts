// Mirror of backend/app/schemas/event.py and models/enums.py EventStatus --
// keep the string values byte-identical. The backend is the authority on
// what a request may contain; nothing here is a security boundary.

import { apiFetch } from './api'

export const EventStatus = {
  DRAFT: 'draft',
  SUBMITTED_AWAITING_COORDINATOR: 'submitted_awaiting_coordinator',
  UNDER_REVIEW: 'under_review',
  AWAITING_ORGANISER_REPLY: 'awaiting_organiser_reply',
  EVENT_APPROVED: 'event_approved',
  PLANNING_EVENT: 'planning_event',
  AWAITING_SAFETY_CHECK: 'awaiting_safety_check',
  SAFETY_CHECK_PASSED: 'safety_check_passed',
  EVENT_COMPLETED: 'event_completed',
  EVENT_REJECTED: 'event_rejected',
  EVENT_CANCELLED: 'event_cancelled',
} as const
export type EventStatus = (typeof EventStatus)[keyof typeof EventStatus]

/** The ONLY wording for an Event's status anywhere in the UI, for every role.
 *  These are the names in dod.md section 11a, spelled exactly as written there.
 *  The stored slugs (the keys) are the database's own and differ for a few
 *  (`changes_requested` is "Awaiting Organiser Reply", `confirmed` is "Safety
 *  Check Passed (Event Confirmed)"). Add no label here that dod.md lacks. */
export const EVENT_STATUS_LABELS: Record<EventStatus, string> = {
  [EventStatus.DRAFT]: 'Draft',
  [EventStatus.SUBMITTED_AWAITING_COORDINATOR]: 'Submitted – Awaiting Coordinator',
  [EventStatus.UNDER_REVIEW]: 'Under Review',
  [EventStatus.AWAITING_ORGANISER_REPLY]: 'Awaiting Organiser Reply',
  [EventStatus.EVENT_APPROVED]: 'Event Approved',
  [EventStatus.PLANNING_EVENT]: 'Planning Event',
  [EventStatus.AWAITING_SAFETY_CHECK]: 'Awaiting Safety Check',
  [EventStatus.SAFETY_CHECK_PASSED]: 'Safety Check Passed (Event Confirmed)',
  [EventStatus.EVENT_COMPLETED]: 'Event Completed',
  [EventStatus.EVENT_REJECTED]: 'Event Rejected',
  [EventStatus.EVENT_CANCELLED]: 'Event Cancelled',
}

/** One line explaining what a status actually means -- shown next to the
 *  badge so "Submitted" reads as a stage in a process, not just a word. */
export const EVENT_STATUS_DESCRIPTIONS: Record<EventStatus, string> = {
  [EventStatus.DRAFT]: 'The Organiser is still filling this request in. It has not been submitted yet.',
  [EventStatus.SUBMITTED_AWAITING_COORDINATOR]: 'Submitted by the Organiser and waiting for a Coordinator to begin reviewing it.',
  [EventStatus.UNDER_REVIEW]: 'A Coordinator is reviewing the request against venue, equipment and accessibility requirements.',
  [EventStatus.AWAITING_ORGANISER_REPLY]: 'A Coordinator has asked the Organiser to revise the request before it can proceed.',
  [EventStatus.EVENT_APPROVED]: 'The request has been approved and is ready to move into planning.',
  [EventStatus.PLANNING_EVENT]: 'Approved and being planned -- venue, equipment and other logistics are being arranged.',
  [EventStatus.AWAITING_SAFETY_CHECK]: 'Submitted to the Safety Officer. Waiting for the safety check before the event can be confirmed.',
  [EventStatus.SAFETY_CHECK_PASSED]: 'The Safety Officer approved the event. It is confirmed to go ahead and registration can open.',
  [EventStatus.EVENT_COMPLETED]: 'The event has taken place.',
  [EventStatus.EVENT_REJECTED]: 'The request was not approved. It will not proceed.',
  [EventStatus.EVENT_CANCELLED]: 'The event has been cancelled and will not proceed.',
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
  EventStatus.SUBMITTED_AWAITING_COORDINATOR,
  EventStatus.UNDER_REVIEW,
  EventStatus.EVENT_APPROVED,
  EventStatus.PLANNING_EVENT,
  EventStatus.AWAITING_SAFETY_CHECK,
  EventStatus.SAFETY_CHECK_PASSED,
  EventStatus.EVENT_COMPLETED,
]

/** Visual severity for a status that leaves the main pipeline rather than
 *  advancing along it. Absent for every status that IS on the pipeline. */
export const EVENT_STATUS_BRANCH_TONE: Partial<Record<EventStatus, 'warning' | 'danger'>> = {
  [EventStatus.AWAITING_ORGANISER_REPLY]: 'warning',
  [EventStatus.EVENT_REJECTED]: 'danger',
  [EventStatus.EVENT_CANCELLED]: 'danger',
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
  has_pending_change_request?: boolean
}

/** Who a Coordinator or Organiser contacts about the other side of an
 *  event. `users` carries no phone number, so `email` is the whole of
 *  "contact details" today. Reused for both directions -- an Organiser's
 *  contact and an assigned Coordinator's -- since the shape is identical. */
export interface EventContact {
  id: number
  name: string
  email: string
}

/** One piece of equipment requested for an event, as the API returns it.
 *
 *  `equipment_name`/`equipment_category` are flattened off the catalogue
 *  item so a line can be rendered without a second request. */
export interface EquipmentLine {
  id: number
  equipment_id: number
  equipment_name: string
  equipment_category: string | null
  quantity_requested: number
  technical_requirements: string | null
  status: string
}

/** One line as SENT. The server assigns id and status. */
export interface EquipmentLineInput {
  equipment_id: number
  quantity_requested: number
  technical_requirements?: string | null
}

export interface EventDetail extends EventSummary {
  organiser_id: number
  coordinator_id: number | null
  /** None until the system (or a reassignment) has picked someone --
   *  see AC2 of "Mark myself unavailable": this is what lets the Organiser
   *  see who is coordinating their event, right on the event page. */
  coordinator: EventContact | null
  purpose: string | null
  description: string | null
  programme: string | null
  venue_requirements: string | null
  room_layout_preference: string | null
  accessibility_needs: string | null
  equipment_requirements: string | null
  equipment_items: EquipmentLine[]
  special_arrangements: string | null
  registration_enabled: boolean
  /** The window Attendees may register in; null until a Coordinator opens
   *  registration and sets it. */
  registration_opens_at?: string | null
  registration_closes_at?: string | null
  created_at: string
}

/** Who a Coordinator contacts about an event assigned to them. Same shape
 *  as EventContact above -- kept as a named alias since this is what the
 *  AssignedEventDetail response calls the field. */
export type OrganiserContact = EventContact

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
  change_requests: EventChangeRequest[]
  /** What still blocks submitting a planned event for its Safety Check;
   *  empty when it is ready. */
  confirmation_outstanding?: string[]
}

export interface EventChangeRequest {
  id: number
  event_id: number
  requested_by: number
  description: string
  proposed_changes: EventInput & {
    equipment_items?: (EquipmentLineInput & { equipment_name?: string })[] | null
  }
  status: 'pending' | 'approved' | 'rejected'
  review_notes: string | null
  created_at: string
  reviewed_at: string | null
  important_change: boolean
  venue_bookings_to_reconsider: {
    id: number
    venue_name: string
    start_time: string
    end_time: string
    status: string
  }[]
  equipment_reservations_to_reconsider: {
    id: number
    equipment_name: string
    quantity_requested: number
    status: string
  }[]
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
  /** Omit to leave existing lines alone; [] clears them; a list replaces. */
  equipment_items?: EquipmentLineInput[]
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

/** Activity history for an event owned by the signed-in Organiser. */
export function getOwnEventActivity(id: number): Promise<ActivityEntry[]> {
  return apiFetch(`/events/${id}/activity`) as Promise<ActivityEntry[]>
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

/** Approve an event assigned to the signed-in Coordinator. */
export function approveEvent(id: number): Promise<EventDetail> {
  return apiFetch(`/events/${id}/approve`, { method: 'POST' }) as Promise<EventDetail>
}

/** Submit a planned event whose venue and equipment are arranged for its
 *  Safety Check. Rejects with a 409 ApiError naming the outstanding items
 *  when it is not ready. */
export function submitForSafetyCheck(id: number): Promise<EventDetail> {
  return apiFetch(`/events/${id}/confirm`, { method: 'POST' }) as Promise<EventDetail>
}

export interface RegistrationSettings {
  registration_enabled: boolean
  registration_opens_at: string | null
  registration_closes_at: string | null
}

/** Open or close registration on a confirmed event and set its dates.
 *  A 422 ApiError carries `fields` naming the date inputs to flag. */
export function setEventRegistration(id: number, settings: RegistrationSettings): Promise<EventDetail> {
  return apiFetch(`/events/assigned/${id}/registration`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  }) as Promise<EventDetail>
}

/** Reject an assigned event and retain the reason for the Organiser. */
export function rejectEvent(id: number, reason: string): Promise<EventDetail> {
  return apiFetch(`/events/${id}/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  }) as Promise<EventDetail>
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

export function listOwnChangeRequests(id: number): Promise<EventChangeRequest[]> {
  return apiFetch(`/events/${id}/change-requests`) as Promise<EventChangeRequest[]>
}

export function requestEventChanges(
  id: number,
  description: string,
  proposedChanges: EventInput,
): Promise<EventChangeRequest> {
  return apiFetch(`/events/${id}/change-requests`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ description, proposed_changes: proposedChanges }),
  }) as Promise<EventChangeRequest>
}

export function approveEventChangeRequest(id: number, reviewNotes?: string): Promise<EventChangeRequest> {
  return apiFetch(`/events/change-requests/${id}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ review_notes: reviewNotes || null }),
  }) as Promise<EventChangeRequest>
}

export function rejectEventChangeRequest(id: number, reviewNotes?: string): Promise<EventChangeRequest> {
  return apiFetch(`/events/change-requests/${id}/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ review_notes: reviewNotes || null }),
  }) as Promise<EventChangeRequest>
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
