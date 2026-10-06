import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { Link, useParams } from 'react-router'
import { EquipmentLines } from '../../components/EquipmentLines'
import { ApiError } from '../../lib/api'
import type { LeadEventDetail } from '../../lib/coordinatorLead'
import { EVENT_STATUS_LABELS, formatRange, formatTimestamp } from '../../lib/events'

interface Props {
  /** Fetches the Event by its id. */
  load: (id: number) => Promise<LeadEventDetail>
  backTo: string
  backLabel: string
  /** Shown when the server answers 404. */
  notFoundText: string
  /** Badge text; defaults to the Event's own status label. */
  /** Controls for acting on the Event, shown under the details (e.g. assign). */
  actions?: (event: LeadEventDetail) => ReactNode
}

/** An Event Request or active Event for the Coordinator Lead to review.
 *  Strictly read-only: there is no form, no input and no action on this page.
 *  Shared by the Unassigned Queue and the Coordinator Assignments pages. */
export function LeadRequestReview({ load, backTo, backLabel, notFoundText, actions }: Props) {
  const { id } = useParams()
  const [event, setEvent] = useState<LeadEventDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    load(Number(id))
      .then((row) => {
        if (!cancelled) setEvent(row)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(
          err instanceof ApiError && err.status === 404
            ? notFoundText
            : err instanceof ApiError
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
  }, [id, load, notFoundText])

  const back = <Link to={backTo}>{backLabel}</Link>

  if (loading) return null
  if (error || !event) {
    return (
      <div className="stack">
        {back}
        <p className="form-error" role="alert">
          {error}
        </p>
      </div>
    )
  }

  const rows: [string, string | null][] = [
    ['Event name', event.name],
    ['Purpose', event.purpose],
    ['Description', event.description],
    ['Type', event.event_type],
    ['Proposed date and time', formatRange(event.proposed_start, event.proposed_end)],
    ['Expected attendance', event.expected_attendance === null ? null : String(event.expected_attendance)],
    ['Venue requirements', event.venue_requirements],
    ['Accessibility needs', event.accessibility_needs],
    ['Equipment notes', event.equipment_requirements],
    ['Registration needed', event.registration_enabled ? 'Yes' : 'No'],
  ]

  return (
    <div className="stack">
      {back}
      <header className="page-header">
        <h1>{event.name ?? 'Untitled request'}</h1>
        <p className="page-subtitle">
          <span className="badge badge-accent">
            {EVENT_STATUS_LABELS[event.status] ?? event.status}
          </span>{' '}
          Review only: nothing on this page can be edited.
        </p>
      </header>

      <section className="card">
        <h2>What the Organiser entered</h2>
        <dl className="detail-list">
          {rows.map(([label, value]) => (
            <div key={label} className="detail-row">
              <dt>{label}</dt>
              <dd>{value ?? <em className="text-muted">Not provided</em>}</dd>
            </div>
          ))}
          <div className="detail-row">
            <dt>Equipment requirements</dt>
            <dd>
              <EquipmentLines lines={event.equipment_items} />
            </dd>
          </div>
        </dl>
      </section>

      <section className="card">
        <h2>Event Organiser</h2>
        <dl className="detail-list">
          <div className="detail-row">
            <dt>Name</dt>
            <dd>{event.organiser.name}</dd>
          </div>
          <div className="detail-row">
            <dt>Email</dt>
            <dd>
              <a href={`mailto:${event.organiser.email}`}>{event.organiser.email}</a>
            </dd>
          </div>
          <div className="detail-row">
            <dt>Submitted</dt>
            <dd>{formatTimestamp(event.submitted_at) ?? 'n/a'}</dd>
          </div>
          {event.coordinator && (
            <div className="detail-row">
              <dt>Event Coordinator</dt>
              <dd>{event.coordinator.name}</dd>
            </div>
          )}
        </dl>
      </section>
      {actions?.(event)}
    </div>
  )
}
