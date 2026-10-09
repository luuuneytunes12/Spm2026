import { useEffect, useState } from 'react'
import { ApiError } from '../lib/api'
import { checkEventVenueSuitability } from '../lib/venues'
import type { EventVenueSuitability as EventVenueSuitabilityResult } from '../lib/venues'

export function EventVenueSuitability({ eventId }: { eventId: number }) {
  const [result, setResult] = useState<EventVenueSuitabilityResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      setResult(await checkEventVenueSuitability(eventId))
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : 'Could not check event venue suitability.')
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
          setError(
            err instanceof ApiError ? err.message : 'Could not check event venue suitability.',
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
        Each active venue booking is checked separately against this event's requirements.
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
                  <strong>{venue.venue_name}: {venue.suitable ? 'Suitable' : 'Needs attention'}</strong>
                  <ul className="detail-value-list">
                    {venue.checks.map((check, index) => (
                      <li key={`${venue.booking_id}-${check.category}-${index}`}>
                        <strong>{check.category}:</strong> {check.message}
                        {' '}Required: {check.requirement}; available: {check.available}.
                      </li>
                    ))}
                  </ul>
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
            disabled={loading}
          >
            Recheck suitability
          </button>
        </>
      ) : null}
    </section>
  )
}
