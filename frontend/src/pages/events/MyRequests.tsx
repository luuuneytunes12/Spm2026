import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { AvailableCoordinatorsCount } from '../../components/AvailableCoordinatorsCount'
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
  { key: 'drafts', label: 'Drafts' },
  { key: 'submitted', label: 'Submitted Requests' },
] as const

type TabKey = (typeof TABS)[number]['key']

/** Which tab a request belongs on.
 *
 *  Deliberately "draft or not" rather than a list of statuses. Submitting
 *  assigns a Coordinator, and that immediately moves the request on to
 *  `under_review` -- so a tab filtered on `submitted` exactly would lose a
 *  request the moment it was submitted, which is precisely when the
 *  Organiser goes looking for it. Approved, rejected and every later stage
 *  would fall out of it too.
 *
 *  A draft is mine and unsent; everything else is with ConnectSphere and
 *  somewhere in its process. The badge on each row says where. */
function isDraft(event: EventSummary): boolean {
  return event.status === EventStatus.DRAFT
}

export function MyRequests() {
  // The tab lives in the URL so it survives a reload and can be linked to
  // directly -- the form redirects to ?tab=submitted after submitting.
  const [params, setParams] = useSearchParams()
  const active: TabKey = params.get('tab') === 'submitted' ? 'submitted' : 'drafts'

  const [all, setAll] = useState<EventSummary[]>([])
  const [error, setError] = useState<string | null>(null)
  // One fetch for both tabs rather than one per tab. The two buckets are a
  // partition of the same list, so switching is instant and a request can
  // never be missing from both because its status moved between fetches.
  const [loaded, setLoaded] = useState(false)
  const loading = !loaded
  const shownError = loading ? null : error

  const events = all.filter((event) => (active === 'drafts' ? isDraft(event) : !isDraft(event)))

  useEffect(() => {
    let cancelled = false
    listMyEvents()
      .then((rows) => {
        if (cancelled) return
        setAll(rows)
        setError(null)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setAll([])
        setError(
          err instanceof ApiError
            ? err.message
            : 'Could not reach the server. Is the backend running?',
        )
      })
      .finally(() => {
        if (!cancelled) setLoaded(true)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="stack">
      <header className="page-header page-header-row">
        <div>
          <h1>My Event Requests</h1>
          <p className="page-subtitle">
            Drafts are visible only to you until you submit them.
          </p>
        </div>
        <Link to="/organiser/events/new" className="btn-primary btn-link">
          New request
        </Link>
      </header>

      <AvailableCoordinatorsCount />

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
                  className={isDraft(event) ? 'badge badge-muted' : 'badge badge-accent'}
                >
                  {EVENT_STATUS_LABELS[event.status] ?? event.status}
                </span>
                {event.has_pending_change_request && (
                  <span className="badge badge-muted">Change pending</span>
                )}
                {isDraft(event) ? (
                  <Link to={`/organiser/events/${event.id}/edit`}>Continue editing →</Link>
                ) : (
                  <>
                    <Link to={`/organiser/events/${event.id}`}>View →</Link>
                    {(event.status === EventStatus.SUBMITTED ||
                      event.status === EventStatus.UNDER_REVIEW) &&
                      !event.has_pending_change_request && (
                      <Link to={`/organiser/events/${event.id}/edit`}>Request changes →</Link>
                    )}
                  </>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
