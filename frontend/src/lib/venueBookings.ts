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

/** Place a pending request on the server's default 24-hour tentative hold. */
export function holdVenueBooking(id: number): Promise<VenueBooking> {
  return apiFetch(`/venue-bookings/${id}/hold`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  }) as Promise<VenueBooking>
}
