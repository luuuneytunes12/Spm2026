// Mirror of backend/app/routers/venue_bookings.py and schemas/venue_booking.py
// -- keep field names byte-identical. The backend decides who may submit or
// review; nothing here is a security boundary.

import { apiFetch } from './api'
import { EventStatus } from './events'

export const BookingStatus = {
  PENDING: 'pending',
  TENTATIVE_HOLD: 'tentative_hold',
  APPROVED: 'approved',
  REJECTED: 'rejected',
  CANCELLED: 'cancelled',
} as const
export type BookingStatus = (typeof BookingStatus)[keyof typeof BookingStatus]

export const BOOKING_STATUS_LABELS: Record<BookingStatus, string> = {
  pending: 'Pending review',
  tentative_hold: 'Tentative hold',
  approved: 'Approved',
  rejected: 'Rejected',
  cancelled: 'Cancelled',
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
  expected_attendance: number | null
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
  room_layout_preference?: string
  accessibility_needs?: string
  facilities_needs?: string
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

/** Place a pending request on the server's default 24-hour tentative hold. */
export function holdVenueBooking(id: number): Promise<VenueBooking> {
  return apiFetch(`/venue-bookings/${id}/hold`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  }) as Promise<VenueBooking>
}
