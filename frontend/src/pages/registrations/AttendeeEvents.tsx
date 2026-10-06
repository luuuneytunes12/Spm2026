import { useEffect, useState } from 'react'
import { ApiError } from '../../lib/api'
import { formatRange, formatTimestamp } from '../../lib/events'
import {
  listRegistrableEvents,
  registerForEvent,
  withdrawFromEvent,
} from '../../lib/registrations'
import type { RegistrableEvent } from '../../lib/registrations'

/** The Attendee's list of events they can register for, and the ones they
 *  already have. Each row offers at most one action: Withdraw if registered,
 *  Register if open, otherwise nothing -- so a closed event or an existing
 *  registration never shows a Register button. The status-only view of
 *  registrations is My Registrations. */
export function AttendeeEvents() {
  const [events, setEvents] = useState<RegistrableEvent[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<number | null>(null)
  // Fixed at mount: only used to word "not open yet" vs "closed".
  const [now] = useState(() => Date.now())

  useEffect(() => {
    let cancelled = false
    listRegistrableEvents()
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

  async function act(id: number, action: (id: number) => Promise<RegistrableEvent>) {
    setBusyId(id)
    setError(null)
    try {
      const updated = await action(id)
      setEvents((rows) => rows.map((e) => (e.id === id ? updated : e)))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.')
    } finally {
      setBusyId(null)
    }
  }

  function row(event: RegistrableEvent) {
    const notYetOpen =
      !event.registration_open &&
      !!event.registration_opens_at &&
      new Date(event.registration_opens_at).getTime() > now
    return (
      <li key={event.id} className="card request">
        <div className="request-main">
          <span className="request-title">
            {event.name ?? <em className="text-muted">Untitled event</em>}
          </span>
          <span className="request-meta">
            {formatRange(event.proposed_start, event.proposed_end)}
          </span>
          {event.registration_opens_at && event.registration_closes_at && (
            <span className="request-meta">
              Registration: {formatTimestamp(event.registration_opens_at)} –{' '}
              {formatTimestamp(event.registration_closes_at)}
            </span>
          )}
        </div>
        <div className="request-side">
          {event.my_status === 'registered' && (
            <span className="badge badge-accent">Registered</span>
          )}
          {event.my_status === 'withdrawn' && <span className="badge badge-muted">Withdrawn</span>}
          {event.my_status === 'registered' ? (
            <button
              type="button"
              className="btn-link-muted"
              onClick={() => void act(event.id, withdrawFromEvent)}
              disabled={busyId === event.id}
            >
              {busyId === event.id ? 'Withdrawing…' : 'Withdraw'}
            </button>
          ) : event.registration_open ? (
            <button
              type="button"
              onClick={() => void act(event.id, registerForEvent)}
              disabled={busyId === event.id}
            >
              {busyId === event.id
                ? 'Registering…'
                : event.my_status === 'withdrawn'
                  ? 'Register again'
                  : 'Register'}
            </button>
          ) : notYetOpen ? (
            <span className="text-muted">Registration not open yet</span>
          ) : (
            <span className="text-muted">Registration closed</span>
          )}
        </div>
      </li>
    )
  }

  return (
    <div className="stack">
      <header className="page-header">
        <h1>Events</h1>
        <p className="page-subtitle">
          Confirmed events open for registration, and the ones you have registered for.
        </p>
      </header>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      {loading ? null : events.length === 0 ? (
        <div className="card notice-empty">
          <p>No events are open for registration right now.</p>
        </div>
      ) : (
        <ul className="request-list">{events.map(row)}</ul>
      )}
    </div>
  )
}
