import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { ApiError } from '../../lib/api'
import { formatRange, formatTimestamp } from '../../lib/events'
import { getAttendeeEvent } from '../../lib/registrations'
import type { AttendeeEventDetail } from '../../lib/registrations'

/** The attendee-facing details of one confirmed event. Shows only what the
 *  server's attendee view returns, which holds no planning information. */
export function AttendeeEventView() {
  const { id } = useParams()
  const [event, setEvent] = useState<AttendeeEventDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    getAttendeeEvent(Number(id))
      .then((e) => {
        if (!cancelled) setEvent(e)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : 'Could not load this event.')
      })
    return () => {
      cancelled = true
    }
  }, [id])

  const back = (
    <p>
      <Link to="/attendee/events">← Back to events</Link>
    </p>
  )
  if (error) {
    return (
      <div className="stack">
        <p className="form-error" role="alert">
          {error}
        </p>
        {back}
      </div>
    )
  }
  if (!event) return null

  const rows: [string, string | null][] = [
    ['Description', event.description],
    ['Category', event.event_type],
    ['Date and time', formatRange(event.proposed_start, event.proposed_end)],
    ['Venues', event.venues.map((v) => `${v.name}, ${v.location}`).join('\n')],
    ['Accessibility', event.accessibility_needs],
    ['Programme', event.programme],
    ['Registration opens', formatTimestamp(event.registration_opens_at ?? null)],
    ['Registration closes', formatTimestamp(event.registration_closes_at ?? null)],
  ]

  return (
    <div className="stack">
      <header className="page-header">
        <h1>{event.name ?? 'Untitled event'}</h1>
      </header>
      <section className="card">
        <dl className="detail-list">
          {rows.map(([label, value]) => (
            <div key={label} className="detail-row">
              <dt>{label}</dt>
              <dd style={{ whiteSpace: 'pre-line' }}>
                {value || <span className="text-muted">Not provided</span>}
              </dd>
            </div>
          ))}
        </dl>
      </section>
      {back}
    </div>
  )
}
