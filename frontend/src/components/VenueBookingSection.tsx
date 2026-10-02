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
 *  nothing is created.
 *
 *  Venue Staff's decision shows here too. An approval ends it. A rejection
 *  is shown with its reason and/or suggested alternative above the form,
 *  which comes back so the request can be submitted again -- as many times
 *  as it takes. */
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
  // Newest first, so with nothing live the first one is the latest answer.
  const lastRejected = !live && bookings?.[0]?.status === 'rejected' ? bookings[0] : undefined
  const earlier = bookings?.filter((b) => b !== live && b !== lastRejected) ?? []

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
        <div role="status">
          <p>
            <strong>{live.venue.name}</strong> requested on {formatTimestamp(live.created_at)} —{' '}
            {BOOKING_STATUS_LABELS[live.status]}.
          </p>
          <Decision booking={live} />
        </div>
      ) : (
        <form onSubmit={(e) => void submit(e)} noValidate>
          {lastRejected && (
            <div className="notice" role="status">
              <p>
                <strong>{lastRejected.venue.name}</strong> requested on{' '}
                {formatTimestamp(lastRejected.created_at)} —{' '}
                {BOOKING_STATUS_LABELS[lastRejected.status]}. You can submit the request again
                below, for this venue or another.
              </p>
              <Decision booking={lastRejected} />
            </div>
          )}
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

      {earlier.length > 0 && (
        <>
          <h3>Earlier requests</h3>
          <ul>
            {earlier.map((b) => (
              <li key={b.id}>
                {b.venue.name} · {formatRange(b.start_time, b.end_time)} ·{' '}
                {BOOKING_STATUS_LABELS[b.status]}
                <Decision booking={b} />
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}

/** Venue Staff's decision on one request: who decided and when, and for a
 *  rejection the reason and/or the alternative they suggest. Nothing while
 *  the request is still pending. */
function Decision({ booking }: { booking: VenueBooking }) {
  if (!booking.reviewed_at) return null
  const rows = [
    ['Reason', booking.decision_notes],
    ['Suggested alternative', booking.suggested_alternative],
    [
      'Decided',
      `${formatTimestamp(booking.reviewed_at)}${booking.reviewed_by ? ` by ${booking.reviewed_by.name}` : ''}`,
    ],
  ] as const
  return (
    <dl className="detail-list">
      {rows.map(
        ([label, value]) =>
          value && (
            <div key={label} className="detail-row">
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ),
      )}
    </dl>
  )
}
