import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { ApiError } from '../../lib/api'
import { EVENT_STATUS_LABELS, EventStatus, formatRange, getEvent } from '../../lib/events'
import type { EventDetail } from '../../lib/events'

/** Read-only view of a request that has left the draft stage.
 *
 * Submitted requests are deliberately not editable here: once a Coordinator
 * may be reviewing it, changing the date underneath them would invalidate
 * the review. Later edits go through the change-request story instead, so
 * this page is a dead end by design rather than by omission. */
export function EventView() {
  const { id } = useParams()
  const [event, setEvent] = useState<EventDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!id) return
    let cancelled = false
    getEvent(Number(id))
      .then((e) => {
        if (!cancelled) setEvent(e)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : 'Could not load this request.')
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [id])

  if (loading) return null

  if (error || !event) {
    return (
      <div className="stack">
        <p className="form-error" role="alert">
          {error ?? 'Request not found.'}
        </p>
        <p>
          <Link to="/organiser/events">← Back to my requests</Link>
        </p>
      </div>
    )
  }

  const rows: [string, string | null][] = [
    ['Event type', event.event_type],
    ['Purpose', event.purpose],
    ['Description', event.description],
    ['Proposed date', formatRange(event.proposed_start, event.proposed_end)],
    ['Expected attendees', event.expected_attendance?.toString() ?? null],
    ['Programme', event.programme],
    ['Venue requirements', event.venue_requirements],
    ['Room layout preference', event.room_layout_preference],
    ['Accessibility requirements', event.accessibility_needs],
    ['Equipment requirements', event.equipment_requirements],
    ['Registration', event.registration_enabled ? 'Attendees must register' : 'Not required'],
    ['Special arrangements', event.special_arrangements],
  ]

  return (
    <div className="stack">
      <header className="page-header page-header-row">
        <div>
          <h1>{event.name ?? 'Untitled request'}</h1>
          <p className="page-subtitle">
            <span
              className={
                event.status === EventStatus.DRAFT ? 'badge badge-muted' : 'badge badge-accent'
              }
            >
              {EVENT_STATUS_LABELS[event.status] ?? event.status}
            </span>
            {event.submitted_at &&
              ` · submitted ${new Date(event.submitted_at).toLocaleString(undefined, {
                dateStyle: 'medium',
                timeStyle: 'short',
              })}`}
          </p>
        </div>
        {event.status === EventStatus.DRAFT && (
          <Link to={`/organiser/events/${event.id}/edit`} className="btn-primary btn-link">
            Continue editing
          </Link>
        )}
      </header>

      <section className="card">
        <dl className="detail-list">
          {rows.map(([label, value]) => (
            <div key={label} className="detail-row">
              <dt>{label}</dt>
              <dd>{value ?? <span className="text-muted">Not provided</span>}</dd>
            </div>
          ))}
        </dl>
      </section>

      <p>
        <Link to="/organiser/events">← Back to my requests</Link>
      </p>
    </div>
  )
}
