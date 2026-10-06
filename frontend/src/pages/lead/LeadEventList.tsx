import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { ApiError } from '../../lib/api'
import type { LeadEvent } from '../../lib/coordinatorLead'
import { Link } from 'react-router'
import { EVENT_STATUS_LABELS, formatRange, formatTimestamp } from '../../lib/events'


interface Props {
  title: string
  subtitle: string
  emptyText: string
  load: () => Promise<LeadEvent[]>
  /** When set, each row links to its review page. */
  detailTo?: (event: LeadEvent) => string
  /** Show when each request was submitted. */
  showSubmitted?: boolean
  /** Controls shown above the list (e.g. a filter). */
  filter?: ReactNode
  /** A line showing how many rows there are. */
  countText?: (count: number) => string
}

/** Read-only list of Event Requests for the Coordinator Lead. Shared by the
 *  Unassigned Requests and Coordinator Assignments pages, which differ only
 *  in what they load and say. */
export function LeadEventList({ title, subtitle, emptyText, load, detailTo, showSubmitted, filter, countText }: Props) {
  const [events, setEvents] = useState<LeadEvent[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    load()
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
  }, [load])

  return (
    <div className="stack">
      <header className="page-header">
        <h1>{title}</h1>
        <p className="page-subtitle">{subtitle}</p>
      </header>

      {filter}

      {countText && !loading && !error && (
        <p className="page-subtitle" role="status">
          {countText(events.length)}
        </p>
      )}

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      {loading ? null : events.length === 0 ? (
        <div className="card notice-empty">
          <p>{emptyText}</p>
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
                  {event.event_type && ` · ${event.event_type}`}
                  {event.expected_attendance !== null && ` · ${event.expected_attendance} attendees`}
                  {` · Organiser: ${event.organiser.name}`}
                  {showSubmitted && ` · Submitted ${formatTimestamp(event.submitted_at) ?? 'n/a'}`}
                  {` · Coordinator: ${event.coordinator ? event.coordinator.name : 'not yet assigned'}`}
                </span>
              </div>
              <div className="request-side">
                <span className="badge badge-accent">
                  {EVENT_STATUS_LABELS[event.status] ?? event.status}
                </span>
                {detailTo && <Link to={detailTo(event)}>Review →</Link>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
