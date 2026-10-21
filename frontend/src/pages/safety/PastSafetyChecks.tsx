import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { ApiError } from '../../lib/api'
import { EVENT_STATUS_LABELS, formatRange, formatTimestamp } from '../../lib/events'
import { listPastSafetyChecks } from '../../lib/safetyChecks'
import type { PastSafetyCheck } from '../../lib/safetyChecks'

/** The Safety Checks the signed-in Safety Officer has decided: one row per
 *  event with their latest decision, reason and time, newest first. */
export function PastSafetyChecks() {
  const [events, setEvents] = useState<PastSafetyCheck[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    listPastSafetyChecks()
      .then((rows) => !cancelled && setEvents(rows))
      .catch((err: unknown) => {
        if (cancelled) return
        setEvents([])
        setError(err instanceof ApiError ? err.message : 'Could not load your past safety checks.')
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="stack">
      <header className="page-header">
        <h1>Past Safety Checks</h1>
        <p className="page-subtitle">Events you have approved, rejected or sent back for changes.</p>
      </header>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      {events === null ? null : events.length === 0 ? (
        <div className="card notice-empty">
          <p>No past safety checks.</p>
          <p className="page-subtitle">Events appear here once you approve, reject or request changes.</p>
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
                  {formatRange(event.proposed_start, event.proposed_end)} · Now:{' '}
                  {EVENT_STATUS_LABELS[event.status] ?? event.status}
                </span>
                <span className="request-meta">
                  <span className="badge">{event.decision}</span> · Decided{' '}
                  {formatTimestamp(event.decided_at)}
                </span>
                {event.reason && <span className="request-meta">Reason: {event.reason}</span>}
              </div>
              <div className="request-side">
                <Link
                  to={`/safety-checks/${event.id}`}
                  aria-label={`View ${event.name ?? 'untitled event'}`}
                >
                  View →
                </Link>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
