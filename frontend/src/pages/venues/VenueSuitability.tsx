import { useEffect, useState } from 'react'
import { ApiError } from '../../lib/api'
import { listAssignedEvents } from '../../lib/events'
import type { EventSummary } from '../../lib/events'
import { checkVenueSuitability } from '../../lib/venues'
import type { VenueSuitability as VenueSuitabilityResult } from '../../lib/venues'

export function VenueSuitability({ venueId }: { venueId: number }) {
  const [events, setEvents] = useState<EventSummary[]>([])
  const [loadingEvents, setLoadingEvents] = useState(true)
  const [eventsError, setEventsError] = useState<string | null>(null)
  const [selectedEventId, setSelectedEventId] = useState('')
  const [result, setResult] = useState<VenueSuitabilityResult | null>(null)
  const [checkError, setCheckError] = useState<string | null>(null)
  const [checking, setChecking] = useState(false)

  useEffect(() => {
    let cancelled = false
    listAssignedEvents()
      .then((rows) => {
        if (!cancelled) {
          setEvents(rows)
          setEventsError(null)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setEventsError(
            err instanceof ApiError ? err.message : 'Could not load your assigned events.',
          )
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingEvents(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function loadEvents() {
    setLoadingEvents(true)
    setEventsError(null)
    try {
      setEvents(await listAssignedEvents())
    } catch (err: unknown) {
      setEventsError(
        err instanceof ApiError ? err.message : 'Could not load your assigned events.',
      )
    } finally {
      setLoadingEvents(false)
    }
  }

  async function runCheck() {
    if (!selectedEventId) return
    setChecking(true)
    setCheckError(null)
    setResult(null)
    try {
      setResult(await checkVenueSuitability(venueId, Number(selectedEventId)))
    } catch (err: unknown) {
      setCheckError(
        err instanceof ApiError ? err.message : 'Could not check suitability. Please try again.',
      )
    } finally {
      setChecking(false)
    }
  }

  return (
    <section className="card stack" aria-label="Check event suitability">
      <h2>Check suitability for an event</h2>
      <p className="page-subtitle">
        Compare this venue with an event assigned to you. Requirement text may contain comma-,
        semicolon-, or line-separated items.
      </p>
      {eventsError ? (
        <div>
          <p className="form-error" role="alert">
            {eventsError}
          </p>
          <button
            type="button"
            className="btn-secondary"
            onClick={loadEvents}
            disabled={loadingEvents}
          >
            {loadingEvents ? 'Loading events…' : 'Retry loading events'}
          </button>
        </div>
      ) : (
        <>
          {loadingEvents ? (
            <p role="status">Loading assigned events…</p>
          ) : (
            <>
              <div className="field">
                <label htmlFor="suitability-event">Event</label>
                <select
                  id="suitability-event"
                  value={selectedEventId}
                  onChange={(event) => {
                    setSelectedEventId(event.target.value)
                    setResult(null)
                    setCheckError(null)
                  }}
                >
                  <option value="">Select an assigned event</option>
                  {events.map((event) => (
                    <option key={event.id} value={event.id}>
                      {event.name || `Event ${event.id}`}
                    </option>
                  ))}
                </select>
              </div>
              {events.length === 0 && (
                <p className="text-muted">You have no assigned events to check.</p>
              )}
              <button
                type="button"
                className="btn-primary"
                onClick={runCheck}
                disabled={!selectedEventId || checking}
              >
                {checking ? 'Checking suitability…' : 'Check suitability'}
              </button>
            </>
          )}
        </>
      )}

      {checkError && (
        <div>
          <p className="form-error" role="alert">
            {checkError}
          </p>
          <button
            type="button"
            className="btn-secondary"
            onClick={runCheck}
            disabled={checking || !selectedEventId}
          >
            Retry check
          </button>
        </div>
      )}
      {result && (
        <div className="stack" aria-live="polite">
          <h3>
            {result.suitable ? 'Suitable' : 'Not suitable'}
            {result.event_name ? ` for ${result.event_name}` : ''}
          </h3>
          <ul className="detail-value-list" aria-label="Suitability check results">
            {result.checks.map((check, index) => (
              <li key={`${check.category}-${check.requirement}-${index}`}>
                <strong>{check.category}:</strong> {check.message}{' '}
                <span className="text-muted">
                  (Required: {check.requirement}; available: {check.available})
                </span>
              </li>
            ))}
          </ul>
          {result.checks.length === 0 && (
            <p className="text-muted">No event requirements have been recorded.</p>
          )}
        </div>
      )}
    </section>
  )
}
