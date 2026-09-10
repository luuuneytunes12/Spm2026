import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { ApiError } from '../../lib/api'
import {
  EVENT_STATUS_LABELS,
  EventStatus,
  formatRange,
  listMyEvents,
} from '../../lib/events'
import type { EventSummary } from '../../lib/events'

/** Drafts and submitted requests are the same rows at different stages, so
 *  they live on one page as two tabs rather than two routes. Submitting
 *  moves a row from the left tab to the right one, which makes the
 *  "no longer appears under drafts" behaviour visible in a single click. */
const TABS = [
  { key: 'drafts', label: 'Drafts', status: EventStatus.DRAFT },
  { key: 'submitted', label: 'Submitted Requests', status: EventStatus.SUBMITTED },
] as const

type TabKey = (typeof TABS)[number]['key']

export function MyRequests() {
  // The tab lives in the URL so it survives a reload and can be linked to
  // directly -- the form redirects to ?tab=submitted after submitting.
  const [params, setParams] = useSearchParams()
  const active: TabKey = params.get('tab') === 'submitted' ? 'submitted' : 'drafts'
  const status = TABS.find((t) => t.key === active)!.status

  const [events, setEvents] = useState<EventSummary[]>([])
  const [error, setError] = useState<string | null>(null)
  // Which tab the current `events`/`error` belong to. Deriving loading from
  // this rather than setting a flag at the top of the effect keeps the
  // effect free of synchronous setState, and means a tab switch cannot show
  // the previous tab's rows or its error while the new one loads.
  const [loadedStatus, setLoadedStatus] = useState<EventStatus | null>(null)
  const loading = loadedStatus !== status
  const shownError = loading ? null : error

  useEffect(() => {
    let cancelled = false
    listMyEvents(status)
      .then((rows) => {
        if (cancelled) return
        setEvents(rows)
        setError(null)
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
        if (!cancelled) setLoadedStatus(status)
      })
    return () => {
      cancelled = true
    }
  }, [status])

  return (
    <div className="stack">
      <header className="page-header page-header-row">
        <div>
          <h1>My event requests</h1>
          <p className="page-subtitle">
            Drafts are visible only to you until you submit them.
          </p>
        </div>
        <Link to="/organiser/events/new" className="btn-primary btn-link">
          New request
        </Link>
      </header>

      <div className="tabs" role="tablist" aria-label="Request status">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={active === tab.key}
            className={active === tab.key ? 'tab tab-active' : 'tab'}
            onClick={() => setParams(tab.key === 'drafts' ? {} : { tab: tab.key })}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {shownError && (
        <p className="form-error" role="alert">
          {shownError}
        </p>
      )}

      {loading ? null : events.length === 0 ? (
        <div className="card notice-empty">
          {active === 'drafts' ? (
            <>
              <p>No drafts yet.</p>
              <p className="page-subtitle">
                <Link to="/organiser/events/new">Start an event request</Link> — you can save it
                incomplete and finish it later.
              </p>
            </>
          ) : (
            <>
              <p>Nothing submitted yet.</p>
              <p className="page-subtitle">
                Once you submit a draft it appears here, and ConnectSphere begins reviewing it.
              </p>
            </>
          )}
        </div>
      ) : (
        <ul className="request-list">
          {events.map((event) => (
            <li key={event.id} className="card request">
              <div className="request-main">
                <span className="request-title">
                  {event.name ?? <em className="text-muted">Untitled draft</em>}
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
                {event.status === EventStatus.DRAFT ? (
                  <Link to={`/organiser/events/${event.id}/edit`}>Continue editing →</Link>
                ) : (
                  <Link to={`/organiser/events/${event.id}`}>View →</Link>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
