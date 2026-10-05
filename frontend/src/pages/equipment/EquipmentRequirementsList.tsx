import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { ApiError } from '../../lib/api'
import { EVENT_STATUS_LABELS, formatRange } from '../../lib/events'
import { listSupportEvents } from '../../lib/equipmentRequirements'
import type { SupportEventSummary } from '../../lib/equipmentRequirements'

/** Technical Support's list of events that have equipment to review, and the
 *  way in to each event's record.
 *
 *  Read-only for now: updating a requirement's status is its own story. Which
 *  events appear is decided by the server -- approved, planning or confirmed,
 *  with at least one requirement, never a draft. */
export function EquipmentRequirementsList() {
  const [events, setEvents] = useState<SupportEventSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    listSupportEvents()
      .then((rows) => {
        if (!cancelled) setEvents(rows)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setEvents([])
        setError(err instanceof ApiError ? err.message : 'Could not load the events.')
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="stack">
      <header className="page-header">
        <h1>Equipment Requirements</h1>
        <p className="page-subtitle">
          Events with equipment to review. Open one to see what its Coordinator has recorded.
        </p>
      </header>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      {events !== null && events.length === 0 && !error && (
        <div className="card notice-empty">
          <p>No events have equipment to review yet.</p>
          <p className="page-subtitle">
            Events appear here once an event is approved and its Coordinator has recorded the
            equipment it needs.
          </p>
        </div>
      )}

      {events !== null && events.length > 0 && (
        <ul className="request-list">
          {events.map((event) => {
            const title = event.name ?? <em className="text-muted">Untitled event</em>
            return (
              <li key={event.id} className="card request">
                <div className="request-main">
                  <span className="request-title">{title}</span>
                  <span className="request-meta">
                    {formatRange(event.proposed_start, event.proposed_end)}
                    {event.expected_attendance !== null && ` · ${event.expected_attendance} attendees`}
                    {event.event_type && ` · ${event.event_type}`}
                  </span>
                </div>
                <div className="request-side">
                  <span className="request-meta">
                    {`${event.requirement_count} requirement${event.requirement_count === 1 ? '' : 's'}`}
                  </span>
                  <span className="badge badge-accent">
                    {EVENT_STATUS_LABELS[event.status] ?? event.status}
                  </span>
                  <Link
                    to={`/equipment-requirements/${event.id}`}
                    aria-label={`View requirements for ${event.name ?? 'untitled event'}`}
                  >
                    View requirements →
                  </Link>
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
