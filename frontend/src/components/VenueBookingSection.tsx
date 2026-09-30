import { useEffect, useState } from 'react'
import { ApiError } from '../lib/api'
import { formatRange, formatTimestamp } from '../lib/events'
import { listVenues } from '../lib/venues'
import type { VenueSummary } from '../lib/venues'
import {
  BOOKING_STATUS_LABELS,
  listEventVenueBookings,
  submitVenueBooking,
} from '../lib/venueBookings'
import type { VenueBooking } from '../lib/venueBookings'

interface Props {
  eventId: number
  expectedAttendance: number | null
}

/** The Coordinator's "request a venue" card for one approved event.
 *
 *  The event's timing and requirements are not typed here: the server copies
 *  them from the event, so the request always matches what the Organiser
 *  asked for. Choosing the venue is the only input. With none chosen the
 *  submit is refused -- by the server, whose message is shown -- and
 *  nothing is created. */
export function VenueBookingSection({ eventId, expectedAttendance }: Props) {
  const [bookings, setBookings] = useState<VenueBooking[] | null>(null)
  const [venues, setVenues] = useState<VenueSummary[]>([])
  const [venueId, setVenueId] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    listEventVenueBookings(eventId)
      .then((b) => !cancelled && setBookings(b))
      .catch(() => !cancelled && setBookings([]))
    // Every active venue, as on the Venues tab. Not narrowed by attendance:
    // a hidden venue is indistinguishable from a missing one, so a small
    // venue is flagged in its label instead.
    listVenues()
      .then((v) => !cancelled && setVenues(v.filter((venue) => venue.is_active)))
      .catch((err: unknown) => {
        if (cancelled) return
        setVenues([])
        setLoadError(err instanceof ApiError ? err.message : 'Could not load venues.')
      })
    return () => {
      cancelled = true
    }
  }, [eventId])

  const live = bookings?.find((b) => b.status === 'pending' || b.status === 'approved')

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const created = await submitVenueBooking(eventId, venueId ? Number(venueId) : null)
      setBookings((current) => [created, ...(current ?? [])])
      setVenueId('')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not submit the booking request.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="card" aria-labelledby="venue-booking-heading">
      <h2 id="venue-booking-heading">Venue booking</h2>

      {live ? (
        <p role="status">
          <strong>{live.venue.name}</strong> requested on {formatTimestamp(live.created_at)} —{' '}
          {BOOKING_STATUS_LABELS[live.status]}.
        </p>
      ) : (
        <form onSubmit={(e) => void submit(e)} noValidate>
          <p className="page-subtitle">
            The event's date, time, expected attendance, layout and accessibility needs are sent
            with the request.
          </p>
          <label className="field">
            <span>Venue</span>
            <select value={venueId} onChange={(e) => setVenueId(e.target.value)} disabled={submitting}>
              <option value="">Select a venue…</option>
              {venues.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name} — {v.location} (capacity {v.capacity}
                  {expectedAttendance !== null && v.capacity < expectedAttendance ? ', too small' : ''})
                </option>
              ))}
            </select>
          </label>
          {loadError && (
            <p className="form-error" role="alert">
              {loadError}
            </p>
          )}
          <button type="submit" className="btn-primary" disabled={submitting}>
            {submitting ? 'Submitting…' : 'Submit booking request'}
          </button>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
        </form>
      )}

      {bookings && bookings.some((b) => b !== live) && (
        <>
          <h3>Earlier requests</h3>
          <ul>
            {bookings
              .filter((b) => b !== live)
              .map((b) => (
                <li key={b.id}>
                  {b.venue.name} · {formatRange(b.start_time, b.end_time)} ·{' '}
                  {BOOKING_STATUS_LABELS[b.status]}
                </li>
              ))}
          </ul>
        </>
      )}
    </section>
  )
}
