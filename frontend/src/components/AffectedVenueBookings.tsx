import { useEffect, useState } from 'react'
import { ApiError } from '../lib/api'
import { formatRange } from '../lib/events'
import { CONFLICT_FLAG_LABEL, isLiveBooking, listEventVenueBookings } from '../lib/venueBookings'
import type { VenueBooking } from '../lib/venueBookings'
import { FindReplacementLink } from './FindReplacementLink'

/** Bookings marked Venue Unavailable - Action Required, for an Event past the
 *  planning window. Requesting, changing and cancelling are closed by then, so
 *  VenueBookingSection is not shown; only finding a replacement is still open.
 *  Shows nothing while no booking needs one. */
export function AffectedVenueBookings({ eventId }: { eventId: number }) {
  const [bookings, setBookings] = useState<VenueBooking[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    listEventVenueBookings(eventId)
      .then((loaded) => {
        if (!cancelled) setBookings(loaded)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : 'Could not load the venue bookings.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [eventId])

  const affected = bookings.filter((b) => b.conflict_flagged && isLiveBooking(b.status))
  if (!error && affected.length === 0) return null

  return (
    <section className="card" aria-labelledby="affected-bookings-heading">
      <h2 id="affected-bookings-heading">Venue bookings needing action</h2>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <ul className="stack-tight">
        {affected.map((b) => {
          const replacement = bookings.find(
            (other) => other.replaces?.id === b.id && isLiveBooking(other.status),
          )
          return (
            <li key={b.id}>
              <p>
                <strong>{b.venue.name}</strong> · {formatRange(b.start_time, b.end_time)}
              </p>
              <p className="notice" role="note">
                <span className="badge">Conflict flagged</span> {CONFLICT_FLAG_LABEL}. Venue
                Unavailable - Action Required: your Event is not cancelled, so find a replacement
                venue.
              </p>
              {replacement ? (
                <p className="field-hint">
                  Replacement requested at {replacement.venue.name}. Waiting for Venue Staff.
                </p>
              ) : (
                <div className="form-actions">
                  <FindReplacementLink booking={b} />
                </div>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
