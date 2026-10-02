import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { ApiError } from '../../lib/api'
import { formatRange } from '../../lib/events'
import { listMyRegistrations } from '../../lib/registrations'
import type { RegistrableEvent } from '../../lib/registrations'

/** The Attendee's registrations: every event they have registered for, with
 *  its name, date, time and their status (Registered / Withdrawn).
 *
 *  Read-only. Registering and withdrawing happen on the Events page; this is
 *  where an Attendee confirms the result. It always asks the server on open,
 *  so it reflects the latest register / withdraw. A withdrawn event stays
 *  listed -- as Withdrawn -- and a re-registered one is the same row back to
 *  Registered, so no event ever appears twice. */
export function MyRegistrations() {
  const [events, setEvents] = useState<RegistrableEvent[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    listMyRegistrations()
      .then((rows) => {
        if (!cancelled) setEvents(rows)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(
          err instanceof ApiError
            ? err.message
            : 'Could not reach the server. Is the backend running?',
        )
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="stack">
      <header className="page-header">
        <h1>My Registrations</h1>
        <p className="page-subtitle">The events you have registered for, and your status for each.</p>
      </header>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      {loading || error ? null : events.length === 0 ? (
        <div className="card notice-empty">
          <p>No registrations yet.</p>
          <p>
            <Link to="/attendee/events">Browse events open for registration</Link>
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
                  {formatRange(event.proposed_start, event.proposed_end)}
                </span>
              </div>
              <div className="request-side">
                {event.my_status === 'registered' ? (
                  <span className="badge badge-accent">Registered</span>
                ) : (
                  <span className="badge badge-muted">Withdrawn</span>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
