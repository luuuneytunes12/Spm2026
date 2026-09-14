import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { useAuth } from '../../auth/useAuth'
import { ApiError } from '../../lib/api'
import {
  EVENT_STATUS_LABELS,
  EventStatus,
  formatRange,
  getEvent,
  getEventHistory,
} from '../../lib/events'
import type { EventDetail, EventHistoryEntry } from '../../lib/events'
import { Role } from '../../lib/roles'

const timestamp = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })

/** What an activity log row says, since a status-preserving entry (e.g. a
 *  Coordinator auto-assignment) has nothing to show but its `note`. */
function historyText(entry: EventHistoryEntry): string {
  if (entry.note) return entry.note
  return entry.from_status && entry.from_status !== entry.to_status
    ? `Status changed from ${entry.from_status} to ${entry.to_status}`
    : `Status: ${entry.to_status}`
}

/** Read-only view of a request that has left the draft stage.
 *
 * Submitted requests are deliberately not editable here: once a Coordinator
 * may be reviewing it, changing the date underneath them would invalidate
 * the review. Later edits go through the change-request story instead, so
 * this page is a dead end by design rather than by omission.
 *
 * Shared between the Organiser (/organiser/events/:id) and the assigned
 * Coordinator (/coordinator/events/:id) -- the backend allows both to read
 * it, so the "back" link and the "who else is on this" row adapt to
 * whichever role is looking. */
export function EventView() {
  const { id } = useParams()
  const { user } = useAuth()
  const isCoordinator = user?.role === Role.COORDINATOR
  const basePath = isCoordinator ? '/coordinator/events' : '/organiser/events'

  const [event, setEvent] = useState<EventDetail | null>(null)
  const [history, setHistory] = useState<EventHistoryEntry[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!id) return
    let cancelled = false
    Promise.all([getEvent(Number(id)), getEventHistory(Number(id))])
      .then(([e, h]) => {
        if (cancelled) return
        setEvent(e)
        setHistory(h)
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
          <Link to={basePath}>← Back</Link>
        </p>
      </div>
    )
  }

  // The Coordinator wants to know who they're dealing with (the
  // Organiser); the Organiser wants to know who was assigned to them.
  // Showing "Coordinator: you" or "Organiser: you" to whichever side is
  // already the viewer would just be noise.
  const personRow: [string, string | null] = isCoordinator
    ? ['Organiser', event.organiser.name]
    : ['Assigned coordinator', event.coordinator?.name ?? null]

  const rows: [string, string | null][] = [
    personRow,
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
              ` · submitted ${timestamp(event.submitted_at)}`}
          </p>
        </div>
        {!isCoordinator && event.status === EventStatus.DRAFT && (
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

      {history.length > 0 && (
        <section className="card">
          <h2>Activity log</h2>
          <dl className="detail-list">
            {history.map((entry) => (
              <div key={entry.id} className="detail-row">
                <dt>{timestamp(entry.created_at)}</dt>
                <dd>{historyText(entry)}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      <p>
        <Link to={basePath}>← Back to {isCoordinator ? 'my assigned events' : 'my requests'}</Link>
      </p>
    </div>
  )
}
