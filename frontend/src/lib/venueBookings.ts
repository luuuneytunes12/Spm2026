// Mirror of backend/app/routers/venue_bookings.py and schemas/venue_booking.py
// -- keep field names byte-identical. The backend decides who may submit or
// review; nothing here is a security boundary.

import { apiFetch } from './api'

export const BookingStatus = {
  PENDING: 'pending',
  APPROVED: 'approved',
  REJECTED: 'rejected',
  CANCELLED: 'cancelled',
} as const
export type BookingStatus = (typeof BookingStatus)[keyof typeof BookingStatus]

export const BOOKING_STATUS_LABELS: Record<BookingStatus, string> = {
  pending: 'Pending review',
  approved: 'Approved',
  rejected: 'Rejected',
  cancelled: 'Cancelled',
}

/** Event statuses from which a venue can be requested. Mirrors
 *  BOOKABLE_EVENT_STATUSES on the server. */
export const BOOKABLE_EVENT_STATUSES: readonly string[] = ['approved', 'planning', 'confirmed']

export interface VenueBooking {
  id: number
  status: BookingStatus
  created_at: string
  event: { id: number; name: string | null }
  venue: { id: number; name: string; location: string; capacity: number }
  start_time: string
  end_time: string
  expected_attendance: number | null
  room_layout_preference: string | null
  accessibility_needs: string | null
  venue_requirements: string | null
  requested_by: { name: string; email: string }
}

/** Ask for a venue. The timing and requirements come from the event itself,
 *  so the venue is the only thing sent. `null` is allowed on purpose: the
 *  server refuses it with a message the form shows. */
export function submitVenueBooking(eventId: number, venueId: number | null): Promise<VenueBooking> {
  return apiFetch(`/venue-bookings/events/${eventId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ venue_id: venueId }),
  }) as Promise<VenueBooking>
}

/** Booking requests already made for an event the caller coordinates. */
export function listEventVenueBookings(eventId: number): Promise<VenueBooking[]> {
  return apiFetch(`/venue-bookings/events/${eventId}`) as Promise<VenueBooking[]>
}

/** Pending requests for Venue Staff to review, oldest first. */
export function listVenueBookingQueue(): Promise<VenueBooking[]> {
  return apiFetch('/venue-bookings/queue') as Promise<VenueBooking[]>
}
