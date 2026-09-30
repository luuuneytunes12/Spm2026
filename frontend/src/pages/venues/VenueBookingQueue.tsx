import { useEffect, useState } from 'react'
import { ApiError } from '../../lib/api'
import { formatRange, formatTimestamp } from '../../lib/events'
import { listVenueBookingQueue } from '../../lib/venueBookings'
import type { VenueBooking } from '../../lib/venueBookings'

/** Venue Staff's review queue: every pending booking request, each carrying
 *  what is needed to decide on it -- the venue, the event's date and time,
 *  expected attendance, layout, and accessibility or facility needs. */
export function VenueBookingQueue() {
  const [bookings, setBookings] = useState<VenueBooking[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    listVenueBookingQueue()
      .then((b) => !cancelled && setBookings(b))
      .catch((err: unknown) => {
        if (!cancelled)
          setError(err instanceof ApiError ? err.message : 'Could not load booking requests.')
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div>
      <h1>Booking requests</h1>
      <p className="page-subtitle">Pending venue booking requests from Event Coordinators.</p>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {!error && bookings === null && <p>Loading…</p>}
      {bookings?.length === 0 && <p>No pending booking requests.</p>}

      {bookings?.map((b) => (
        <section key={b.id} className="card" aria-label={`Booking request for ${b.event.name ?? 'an event'}`}>
          <h2>{b.event.name ?? 'Untitled event'}</h2>
          <dl className="detail-list">
            {(
              [
                ['Venue', `${b.venue.name} — ${b.venue.location}`],
                ['Date and time', formatRange(b.start_time, b.end_time)],
                ['Expected attendance', b.expected_attendance?.toString() ?? 'Not given'],
                ['Layout requirements', b.room_layout_preference ?? 'None given'],
                ['Accessibility needs', b.accessibility_needs ?? 'None given'],
                ['Facility needs', b.venue_requirements ?? 'None given'],
                ['Requested by', `${b.requested_by.name} (${b.requested_by.email})`],
                ['Requested on', formatTimestamp(b.created_at) ?? ''],
              ] as const
            ).map(([label, value]) => (
              <div key={label} className="detail-row">
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
        </section>
      ))}
    </div>
  )
}
