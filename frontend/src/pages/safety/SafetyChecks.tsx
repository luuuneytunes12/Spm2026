import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { ApiError } from '../../lib/api'
import { formatRange } from '../../lib/events'
import { listSafetyChecks } from '../../lib/safetyChecks'
import type { SafetyCheckSummary } from '../../lib/safetyChecks'

/** The Safety Officer's queue: every event awaiting its Operational Safety
 *  Check, with its name, date and Event Coordinator. */
export function SafetyChecks() {
  const [events, setEvents] = useState<SafetyCheckSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    listSafetyChecks()
      .then((rows) => !cancelled && setEvents(rows))
      .catch((err: unknown) => {
        if (cancelled) return
        setEvents([])
        setError(err instanceof ApiError ? err.message : 'Could not load safety checks.')
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="stack">
      <header className="page-header">
        <h1>Safety Checks</h1>
        <p className="page-subtitle">
          Events whose venue and equipment are arranged, waiting for you to check they are safe.
        </p>
      </header>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      {events === null ? null : events.length === 0 ? (
        <div className="card notice-empty">
          <p>No events to review.</p>
          <p className="page-subtitle">
            Events appear here when their Event Coordinator submits them for a safety check.
          </p>
        </div>
      ) : (
        <ul className="request-list">
          {events.map((event) => (
            <li key={event.id} className="card request">
              <div className="request-main">
                <span className="request-title">
                  {event.name ?? <em className="text-muted">Untitled event</em>}
                </span>
                <span className="request-meta">
                  {formatRange(event.proposed_start, event.proposed_end)} · Coordinator:{' '}
                  {event.coordinator?.name ?? 'Unassigned'}
                </span>
              </div>
              <div className="request-side">
                <Link to={`/safety-checks/${event.id}`}>Review →</Link>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
