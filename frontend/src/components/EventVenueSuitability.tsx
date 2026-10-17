import { useEffect, useState } from 'react'
import { ApiError } from '../lib/api'
import { checkEventVenueSuitability, checkVenueBookingSuitability } from '../lib/venues'
import type { EventVenueSuitability as EventVenueSuitabilityResult } from '../lib/venues'

export function EventVenueSuitability({ eventId }: { eventId: number }) {
  const [result, setResult] = useState<EventVenueSuitabilityResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshingBookingIds, setRefreshingBookingIds] = useState<Set<number>>(() => new Set())
  const [bookingErrors, setBookingErrors] = useState<Record<number, string>>({})

  async function recheckBooking(bookingId: number) {
    setRefreshingBookingIds((current) => new Set(current).add(bookingId))
    setBookingErrors((current) => {
      const next = { ...current }
      delete next[bookingId]
      return next
    })
    try {
      const updated = await checkVenueBookingSuitability(bookingId)
      setResult((current) =>
        current
          ? {
              ...current,
              venues: current.venues.map((venue) =>
                venue.booking_id === bookingId ? updated : venue,
              ),
              suitable:
                current.combined_capacity.met &&
                current.venues.every((venue) =>
                  venue.booking_id === bookingId ? updated.suitable : venue.suitable,
                ),
            }
          : current,
      )
    } catch (err: unknown) {
      console.error('Failed to recheck venue booking suitability.', { bookingId, error: err })
      setBookingErrors((current) => ({
        ...current,
        [bookingId]:
          err instanceof ApiError
            ? err.message
            : err instanceof TypeError
              ? 'Could not reach the backend to recheck this venue booking.'
              : 'Could not recheck this venue booking. Check the browser console for diagnostic details.',
      }))
    } finally {
      setRefreshingBookingIds((current) => {
        const next = new Set(current)
        next.delete(bookingId)
        return next
      })
    }
  }

  async function load() {
    setLoading(true)
    setError(null)
    try {
      setResult(await checkEventVenueSuitability(eventId))
    } catch (err: unknown) {
      console.error('Failed to check event venue suitability.', { eventId, error: err })
      setError(
        err instanceof ApiError
          ? err.message
          : err instanceof TypeError
            ? 'Could not reach the backend to check event venue suitability.'
            : 'Could not check event venue suitability. Check the browser console for diagnostic details.',
      )
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    checkEventVenueSuitability(eventId)
      .then((value) => {
        if (!cancelled) {
          setResult(value)
          setError(null)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          console.error('Failed to check event venue suitability.', { eventId, error: err })
          setError(
            err instanceof ApiError
              ? err.message
              : err instanceof TypeError
                ? 'Could not reach the backend to check event venue suitability.'
                : 'Could not check event venue suitability. Check the browser console for diagnostic details.',
          )
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [eventId])

  return (
    <section className="card stack" aria-label="Event venue suitability">
      <h2>Venue suitability</h2>
      <p className="page-subtitle">
        Each active venue booking is checked separately against its own attendance and needs.
        Combined capacity is checked separately and must exceed expected attendance.
      </p>
      {loading ? (
        <p role="status">Checking venue suitability…</p>
      ) : error ? (
        <div>
          <p className="form-error" role="alert">{error}</p>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => void load()}
            disabled={loading}
          >
            Retry check
          </button>
        </div>
      ) : result ? (
        <>
          {result.venues.length === 0 ? (
            <p>No active venue bookings are attached to this event yet.</p>
          ) : (
            <ul className="detail-value-list">
              {result.venues.map((venue) => (
                <li key={venue.booking_id}>
                  <strong>{venue.venue_name}: {venue.suitable ? 'Suitable' : 'Not suitable'}</strong>
                  <p>
                    Attendance checked: {venue.expected_attendance ?? 'not recorded'}
                  </p>
                  <ul className="detail-value-list">
                    {venue.checks.map((check, index) => (
                      <li key={`${venue.booking_id}-${check.category}-${index}`}>
                        <strong>{check.category}:</strong> {check.message}
                        {' '}Required: {check.requirement}; available: {check.available}.
                      </li>
                    ))}
                  </ul>
                  {bookingErrors[venue.booking_id] && (
                    <p className="form-error" role="alert">{bookingErrors[venue.booking_id]}</p>
                  )}
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => void recheckBooking(venue.booking_id)}
                    disabled={refreshingBookingIds.has(venue.booking_id)}
                  >
                    {refreshingBookingIds.has(venue.booking_id)
                      ? `Rechecking ${venue.venue_name}…`
                      : `Recheck ${venue.venue_name}`}
                  </button>
                </li>
              ))}
            </ul>
          )}
          <p role={result.combined_capacity.met ? 'status' : 'alert'}>
            Combined capacity: {result.combined_capacity.available_capacity}
            {result.combined_capacity.required_capacity !== null
              ? ` / ${result.combined_capacity.required_capacity} required`
              : ' available'} · {result.combined_capacity.message}
          </p>
          <p role="status">
            Overall result: {result.suitable ? 'Suitable' : 'Not suitable'}.
          </p>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => void load()}
            disabled={loading || refreshingBookingIds.size > 0}
          >
            Recheck suitability
          </button>
        </>
      ) : null}
    </section>
  )
}
