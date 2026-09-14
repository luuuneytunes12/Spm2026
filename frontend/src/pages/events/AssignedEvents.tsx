import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { ApiError } from '../../lib/api'
import { EVENT_STATUS_LABELS, EventStatus, formatRange, listAssignedEvents } from '../../lib/events'
import type { EventSummary } from '../../lib/events'

/** The Event Coordinator's list of events assigned to them, and the way in
 *  to each one's full detail.
 *
 *  There are no tabs here, unlike the Organiser's own requests: a Coordinator
 *  cares about everything on their plate at once, and an assigned event moves
 *  through several statuses rather than living in two buckets. The status of
 *  each row is shown as a badge instead. */
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
        if (cancelled) return
        setEvents([])
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
        <h1>My assigned events</h1>
        <p className="page-subtitle">
          Events you have been assigned to coordinate. Open one to see its full requirements.
        </p>
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
            Submitted event requests appear here once ConnectSphere assigns you as their
            Coordinator.
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
                <span
                  className={
                    event.status === EventStatus.DRAFT ? 'badge badge-muted' : 'badge badge-accent'
                  }
                >
                  {EVENT_STATUS_LABELS[event.status] ?? event.status}
                </span>
                <Link to={`/coordinator/events/${event.id}`}>View details →</Link>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
