// Mirror of backend/app/routers/venue_bookings.py and schemas/venue_booking.py
// -- keep field names byte-identical. The backend decides who may submit or
// review; nothing here is a security boundary.

import { apiFetch } from './api'
import { EventStatus, fromDateTimeLocal } from './events'

export const BookingStatus = {
  PENDING: 'pending',
  TENTATIVE_HOLD: 'tentative_hold',
  APPROVED: 'approved',
  REJECTED: 'rejected',
  CANCELLED: 'cancelled',
  /** A tentative hold whose expiry passed before approval: not a booking. */
  HOLD_EXPIRED: 'hold_expired',
  /** Superseded by an approved replacement (SCRUM-95); kept as history. */
  REPLACED: 'replaced',
} as const
export type BookingStatus = (typeof BookingStatus)[keyof typeof BookingStatus]

export const BOOKING_STATUS_LABELS: Record<BookingStatus, string> = {
  pending: 'Pending review',
  tentative_hold: 'Tentative Hold',
  approved: 'Approved',
  rejected: 'Rejected',
  cancelled: 'Cancelled',
  hold_expired: 'Hold Expired',
  replaced: 'Replaced',
}

/** Event statuses from which a venue can be requested. Mirrors
 *  BOOKABLE_EVENT_STATUSES on the server. */
export const BOOKABLE_EVENT_STATUSES: readonly EventStatus[] = [
  EventStatus.EVENT_APPROVED,
  EventStatus.PLANNING_EVENT,
] as const

export interface VenueBooking {
  id: number
  status: BookingStatus
  created_at: string
  event: { id: number; name: string | null }
  venue: { id: number; name: string; location: string; capacity: number }
  start_time: string
  end_time: string
  /** Effective whole minutes of setup before / turnaround after the Event
   *  (0 when the venue has none saved). */
  setup_minutes: number
  turnaround_minutes: number
  /** The venue is held from `occupied_start` (start minus setup) to
   *  `occupied_end` (end plus turnaround). */
  occupied_start: string
  occupied_end: string
  expires_at: string | null
  /** Tentative holds only: what the Coordinator must complete before
   *  `expires_at`. Null for anything else. */
  hold_action?: string | null
  /** Effective attendance for this venue; falls back to the Event's total. */
  expected_attendance: number | null
  /** True when this booking has its own attendance override. */
  attendance_is_overridden?: boolean
  /** What was asked of THIS venue; the Event's own needs where nothing was
   *  entered for it. */
  room_layout_preference: string | null
  accessibility_needs: string | null
  facilities_needs: string | null
  venue_requirements: string | null
  requested_by: { name: string; email: string }
  /** The outcome, all null while pending. `decision_notes` is the reason
   *  Venue Staff gave for a rejection; `suggested_alternative` what they
   *  offer instead. A rejection carries one or both. */
  decision_notes: string | null
  suggested_alternative: string | null
  /** Set when a Safety Officer sent an approved booking back for review.
   *  The venue stays held; deciding again clears it. */
  safety_recheck_reason?: string | null
  reviewed_by: { name: string; email: string } | null
  reviewed_at: string | null
  /** Other bookings that hold this venue at an overlapping time. Only filled
   *  for a pending booking seen by Venue Staff; absent or empty otherwise. */
  conflicts?: BookingConflict[]
  /** An approved booking whose venue's setup/turnaround change made it
   *  overlap another. It is not counted as approved (e.g. for Safety Check
   *  submit) until the flag is cleared. Absent means not flagged. */
  conflict_flagged?: boolean
  /** Kept but flagged after the venue's capacity was cut or a layout removed. */
  review_flagged?: boolean
  review_reason?: string | null
  /** Set on a replacement request: the booking it replaces (SCRUM-95). */
  replaces?: { id: number; status: BookingStatus; venue: { id: number; name: string } } | null
}

/** One booking whose occupied window overlaps this request's. All ISO 8601.
 *  Windows that merely touch (one ends as the other starts) are not
 *  conflicts; the server decides, so none is listed then. */
export interface BookingConflict {
  /** "unavailability" (SCRUM-93): the venue was marked temporarily
   *  unavailable then; there is no booking or event, and `reason` says why. */
  kind?: 'booking' | 'unavailability'
  booking_id: number | null
  event_id: number | null
  event_name: string | null
  event_start: string
  event_end: string
  occupied_start: string
  occupied_end: string
  overlap_start: string
  overlap_end: string
  reason?: string | null
  /** Of the booking this clashes with: approved or tentative_hold. */
  status?: 'approved' | 'tentative_hold' | null
}

/** One venue being asked for, and what is needed of it. A need left out (or
 *  blank) means "as the Event says". */
export interface VenueRequest {
  venue_id: number
  /** Attendance for this venue; omitted/null uses the Event's attendance. */
  expected_attendance?: number | null
  room_layout_preference?: string
  accessibility_needs?: string
  facilities_needs?: string
}

/** The Venue Search address for finding a replacement of a flagged booking
 *  (SCRUM-95 AC1): the booking's date and time and the needs it was made with
 *  are already filled in. */
export function findReplacementPath(booking: VenueBooking): string {
  const params = new URLSearchParams({
    replaces: String(booking.id),
    event: String(booking.event.id),
    replacesVenue: booking.venue.name,
    from: booking.start_time,
    until: booking.end_time,
  })
  if (booking.expected_attendance) params.set('attendance', String(booking.expected_attendance))
  if (booking.room_layout_preference) params.set('layout', booking.room_layout_preference)
  return `/venues?${params.toString()}`
}

/** Ask for a venue to replace a booking marked "Venue Unavailable - Action
 *  Required". The new request has the original's date and time. */
export function requestReplacementVenue(bookingId: number, request: VenueRequest): Promise<VenueBooking> {
  return apiFetch(`/venue-bookings/${bookingId}/replacement`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  }) as Promise<VenueBooking>
}

/** Ask for one or more venues. A separate booking is made for each, under the
 *  same event. The timing comes from the event itself. An empty list is
 *  allowed on purpose: the server refuses it with a message the form shows. */
export function submitVenueBookings(eventId: number, venues: VenueRequest[]): Promise<VenueBooking[]> {
  return apiFetch(`/venue-bookings/events/${eventId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ venues }),
  }) as Promise<VenueBooking[]>
}

/** Booking requests already made for an event the caller coordinates. */
export function listEventVenueBookings(eventId: number): Promise<VenueBooking[]> {
  return apiFetch(`/venue-bookings/events/${eventId}`) as Promise<VenueBooking[]>
}

/** Pending requests for Venue Staff to review, oldest first. */
export function listVenueBookingQueue(): Promise<VenueBooking[]> {
  return apiFetch('/venue-bookings/queue') as Promise<VenueBooking[]>
}

/** Venue Staff: upcoming approved bookings (read-only view). */
export function listApprovedBookings(): Promise<VenueBooking[]> {
  return apiFetch('/venue-bookings/approved') as Promise<VenueBooking[]>
}

/** Approve a pending request. Refused (409) if it was already decided, or
 *  if the venue is no longer free for that time. */
export function approveVenueBooking(id: number): Promise<VenueBooking> {
  return apiFetch(`/venue-bookings/${id}/approve`, { method: 'POST' }) as Promise<VenueBooking>
}

export interface VenueBookingRejection {
  reason: string
  suggested_alternative: string
}

/** Reject a pending request with a reason, an alternative, or both. Blank
 *  is allowed for either; the server refuses it when both are. */
export function rejectVenueBooking(
  id: number,
  rejection: VenueBookingRejection,
): Promise<VenueBooking> {
  return apiFetch(`/venue-bookings/${id}/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(rejection),
  }) as Promise<VenueBooking>
}

/** Approved bookings flagged as conflicting, soonest first (Venue Staff). */
export function listFlaggedBookings(): Promise<VenueBooking[]> {
  return apiFetch('/venue-bookings/flagged') as Promise<VenueBooking[]>
}

/** Keep a flagged booking as it is, with a reason. 422 on a blank reason,
 *  409 when it is not flagged. */
export function keepFlaggedBooking(id: number, reason: string): Promise<VenueBooking> {
  return apiFetch(`/venue-bookings/${id}/keep-conflict`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  }) as Promise<VenueBooking>
}

/** Venue Staff cancel a flagged booking so it no longer overlaps. A reason is
 *  required. 409 when it is not flagged. The Event is not cancelled. */
export function cancelFlaggedBooking(id: number, reason: string): Promise<VenueBooking> {
  return apiFetch(`/venue-bookings/${id}/cancel-flagged`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  }) as Promise<VenueBooking>
}

/** Text of the marker shown on a flagged booking. */
export const CONFLICT_FLAG_LABEL = 'Conflict flagged - not counted as approved until resolved'

type Timing = Pick<
  VenueBooking,
  'start_time' | 'end_time' | 'setup_minutes' | 'turnaround_minutes'
> &
  Partial<Pick<VenueBooking, 'occupied_start' | 'occupied_end'>>

const hhmm = (d: Date) =>
  `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`

/** The three periods a booking holds a venue for, as labelled parts, e.g.
 *  `[{Event, 10:00-12:00}, {Setup, 09:30-10:00}, {Turnaround, 12:00-12:45}]`.
 *  When the event spans days, its ends carry short dates. Times are local,
 *  24-hour. Setup starts at `occupied_start` and turnaround ends at
 *  `occupied_end`; when the server omits them they are worked out from the
 *  minutes. */
export function bookingPeriodParts(b: Timing): { label: string; text: string }[] {
  const start = new Date(b.start_time)
  const end = new Date(b.end_time)
  const setupStart = b.occupied_start
    ? new Date(b.occupied_start)
    : new Date(start.getTime() - b.setup_minutes * 60_000)
  const turnaroundEnd = b.occupied_end
    ? new Date(b.occupied_end)
    : new Date(end.getTime() + b.turnaround_minutes * 60_000)
  const sameDay = (x: Date, y: Date) => x.toDateString() === y.toDateString()
  const md = (d: Date) => d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  // Time, prefixed with a short date when it falls on a different day than `ref`.
  const t = (d: Date, ref: Date) => (sameDay(d, ref) ? hhmm(d) : `${md(d)} ${hhmm(d)}`)
  const eventText = !sameDay(start, end)
    ? `${md(start)} ${hhmm(start)} – ${md(end)} ${hhmm(end)}`
    : `${hhmm(start)}-${hhmm(end)}`
  return [
    { label: 'Event', text: eventText },
    { label: 'Setup', text: `${t(setupStart, start)}-${hhmm(start)}` },
    { label: 'Turnaround', text: `${hhmm(end)}-${t(turnaroundEnd, end)}` },
  ]
}

/** The same parts as a single line: `Event 10:00-12:00 | Setup ... | ...`. */
export function formatBookingPeriods(b: Timing): string {
  return bookingPeriodParts(b)
    .map((p) => `${p.label} ${p.text}`)
    .join(' | ')
}

const shortDate = (d: Date) =>
  d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })

/** A period as one readable string. Same day: `2 Nov 2026, 09:30-12:45`.
 *  Across days both ends carry their date. Local time, 24-hour. */
export function formatPeriod(startIso: string, endIso: string): string {
  const start = new Date(startIso)
  const end = new Date(endIso)
  if (start.toDateString() === end.toDateString()) {
    return `${shortDate(start)}, ${hhmm(start)}-${hhmm(end)}`
  }
  return `${shortDate(start)} ${hhmm(start)} to ${shortDate(end)} ${hhmm(end)}`
}

/** What Venue Staff read for one conflict: the event it belongs to, the time
 *  it holds the venue, and where that overlaps this request. */
export function describeConflict(c: BookingConflict): {
  name: string
  occupied: string
  overlap: string
  unavailable: boolean
  reason: string | null
} {
  return {
    unavailable: c.kind === 'unavailability',
    reason: c.reason ?? null,
    name: c.event_name ?? 'Another event',
    occupied: formatPeriod(c.occupied_start, c.occupied_end),
    overlap: formatPeriod(c.overlap_start, c.overlap_end),
  }
}

/** What Venue Staff enter to place a tentative hold. Both are required. */
export interface VenueHoldInput {
  /** ISO 8601 with a zone; must be in the future. */
  expires_at: string
  /** What the Event Coordinator must complete before the hold expires. */
  required_action: string
}

/** The two inputs of the hold form, named as the server names them so a
 *  client-side check and a 422 flag the same fields. */
export type HoldField = keyof VenueHoldInput

export const HOLD_FIELD_ERRORS = {
  missingExpiry: 'Enter the date and time the hold expires.',
  pastExpiry: 'The expiry must be in the future.',
  required_action: 'Enter the action the Event Coordinator must complete.',
} as const

/** What is wrong with the hold form, per field; empty when it can be sent.
 *  `expiresLocal` is the `datetime-local` value, read in the viewer's zone. */
export function holdFormErrors(
  expiresLocal: string,
  action: string,
  now: Date = new Date(),
): Partial<Record<HoldField, string>> {
  const errors: Partial<Record<HoldField, string>> = {}
  const iso = fromDateTimeLocal(expiresLocal)
  if (!iso) errors.expires_at = HOLD_FIELD_ERRORS.missingExpiry
  else if (new Date(iso) <= now) errors.expires_at = HOLD_FIELD_ERRORS.pastExpiry
  if (!action.trim()) errors.required_action = HOLD_FIELD_ERRORS.required_action
  return errors
}

/** Place a pending request on a tentative hold until `expires_at`. A 422
 *  names `expires_at` or `required_action` in `ApiError.fields`. */
export function holdVenueBooking(id: number, body: VenueHoldInput): Promise<VenueBooking> {
  return apiFetch(`/venue-bookings/${id}/hold`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }) as Promise<VenueBooking>
}

// --- Change or cancel one booking (SCRUM-96) --------------------------------

/** Bookings that can still be changed or cancelled. Rejected and cancelled
 *  are history: another venue is asked for with a new request. Mirrors
 *  LIVE_BOOKING_STATUSES on the server. */
export const LIVE_BOOKING_STATUSES: readonly BookingStatus[] = [
  BookingStatus.PENDING,
  BookingStatus.TENTATIVE_HOLD,
  BookingStatus.APPROVED,
]

export function isLiveBooking(status: BookingStatus): boolean {
  return LIVE_BOOKING_STATUSES.includes(status)
}

/** What a Coordinator may change on one booking: its venue, and what they need
 *  of it. Only what is sent changes. A need sent as null goes back to what the
 *  event says. There is no time: a booking has the event's. */
export interface VenueBookingChanges {
  venue_id?: number
  /** Null returns to the Event's attendance. */
  expected_attendance?: number | null
  room_layout_preference?: string | null
  accessibility_needs?: string | null
  facilities_needs?: string | null
}

const JSON_HEADERS = { 'Content-Type': 'application/json' }

/** Change one booking. It goes back to Pending for Venue Staff; the event's
 *  other bookings are untouched. */
export function changeVenueBooking(id: number, changes: VenueBookingChanges): Promise<VenueBooking> {
  return apiFetch(`/venue-bookings/${id}`, {
    method: 'PATCH',
    headers: JSON_HEADERS,
    body: JSON.stringify(changes),
  }) as Promise<VenueBooking>
}

/** Cancel one booking. The reason is optional. */
export function cancelVenueBooking(id: number, reason?: string): Promise<VenueBooking> {
  const why = reason?.trim()
  return apiFetch(`/venue-bookings/${id}/cancel`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(why ? { reason: why } : {}),
  }) as Promise<VenueBooking>
}

/** What "cancel all" would cancel, from the server: the list to be shown
 *  before the Coordinator confirms. */
export function listCancellableVenueBookings(eventId: number): Promise<VenueBooking[]> {
  return apiFetch(`/venue-bookings/events/${eventId}/cancellable`) as Promise<VenueBooking[]>
}

/** Cancel the listed bookings. The ids are what was shown, and the server
 *  cancels nothing if the event's live bookings are no longer exactly those
 *  (409): the second confirmation is theirs to enforce, not just the page's. */
export function cancelAllVenueBookings(
  eventId: number,
  bookingIds: number[],
  reason?: string,
): Promise<VenueBooking[]> {
  const why = reason?.trim()
  return apiFetch(`/venue-bookings/events/${eventId}/cancel-all`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(why ? { booking_ids: bookingIds, reason: why } : { booking_ids: bookingIds }),
  }) as Promise<VenueBooking[]>
}
