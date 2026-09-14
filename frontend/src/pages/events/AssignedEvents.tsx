import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { ApiError } from '../../lib/api'
import { EVENT_STATUS_LABELS, formatRange, listAssignedEvents } from '../../lib/events'
import type { EventSummary } from '../../lib/events'

/** The Coordinator's landing list: every event auto-assigned to them,
 *  newest first. There is no draft/submitted split here -- unlike the
 *  Organiser's requests, everything on this list is already submitted
 *  (a draft has no Coordinator to show it to). */
export function AssignedEvents() {
  const [events, setEvents] = useState<EventSummary[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    listAssignedEvents()
      .then((rows) => {
        if (!cancelled) setEvents(rows)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(
            err instanceof ApiError
              ? err.message
              : 'Could not reach the server. Is the backend running?',
          )
        }
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
        <h1>My assigned events</h1>
        <p className="page-subtitle">Events ConnectSphere has assigned you to coordinate.</p>
      </header>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      {loading ? null : events.length === 0 ? (
        <div className="card notice-empty">
          <p>Nothing assigned to you yet.</p>
          <p className="page-subtitle">
            When an Organiser submits a request, ConnectSphere assigns it to an available
            Coordinator automatically -- it will show up here.
          </p>
        </div>
      ) : (
        <ul className="request-list">
          {events.map((event) => (
            <li key={event.id} className="card request">
              <div className="request-main">
                <span className="request-title">
                  {event.name ?? <em className="text-muted">Untitled request</em>}
                </span>
                <span className="request-meta">
                  {formatRange(event.proposed_start, event.proposed_end)}
                  {event.expected_attendance !== null && ` · ${event.expected_attendance} attendees`}
                  {event.event_type && ` · ${event.event_type}`}
                </span>
              </div>
              <div className="request-side">
                <span className="badge badge-accent">
                  {EVENT_STATUS_LABELS[event.status] ?? event.status}
                </span>
                <Link to={`/coordinator/events/${event.id}`}>View →</Link>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
