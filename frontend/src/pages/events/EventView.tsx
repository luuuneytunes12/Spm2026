import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { AvailableCoordinatorsCount } from '../../components/AvailableCoordinatorsCount'
import { EquipmentLines } from '../../components/EquipmentLines'
import { ApiError } from '../../lib/api'
import {
  EVENT_STATUS_LABELS,
  EventStatus,
  formatRange,
  formatTimestamp,
  getEvent,
  getOwnEventActivity,
} from '../../lib/events'
import type { ActivityEntry, EventDetail } from '../../lib/events'

function activityStatusLabel(value: string): string {
  return EVENT_STATUS_LABELS[value as EventStatus] ?? value
}

/** View an event request and offer corrections until its review is decided. */
export function EventView() {
  const { id } = useParams()
  const [event, setEvent] = useState<EventDetail | null>(null)
  const [activity, setActivity] = useState<ActivityEntry[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!id) return
    let cancelled = false
    Promise.all([getEvent(Number(id)), getOwnEventActivity(Number(id))])
      .then(([e, entries]) => {
        if (!cancelled) {
          setEvent(e)
          setActivity(entries)
        }
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
    ['Other equipment notes', event.equipment_requirements],
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
        {(event.status === EventStatus.DRAFT ||
          event.status === EventStatus.SUBMITTED ||
          event.status === EventStatus.UNDER_REVIEW) && (
          <Link to={`/organiser/events/${event.id}/edit`} className="btn-primary btn-link">
            {event.status === EventStatus.DRAFT ? 'Continue editing' : 'Correct request'}
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
          {/* Outside the map: these are structured rows, not a string. */}
          <div className="detail-row">
            <dt>Equipment requirements</dt>
            <dd>
              <EquipmentLines lines={event.equipment_items} />
            </dd>
          </div>
        </dl>
      </section>

      {event.status !== EventStatus.DRAFT && (
        <section className="card">
          <h2>Your Assigned Event Coordinator</h2>
          <AvailableCoordinatorsCount />
          {event.coordinator ? (
            <dl className="detail-list">
              <div className="detail-row">
                <dt>Name</dt>
                <dd>{event.coordinator.name}</dd>
              </div>
              <div className="detail-row">
                <dt>Email</dt>
                <dd>
                  <a href={`mailto:${event.coordinator.email}`}>{event.coordinator.email}</a>
                </dd>
              </div>
            </dl>
          ) : (
            <p className="page-subtitle">
              Not yet assigned. ConnectSphere will assign one automatically once a Coordinator is
              available.
            </p>
          )}
        </section>
      )}

      {event.status !== EventStatus.DRAFT && (
        <section className="card">
          <h2>Activity Log</h2>
          {activity.length === 0 ? (
            <p className="page-subtitle">No activity recorded yet.</p>
          ) : (
            <ol className="activity-list" aria-label="Activity log">
              {activity.map((entry, index) => {
                const sameStatus = entry.from_status === entry.to_status
                const assignment =
                  sameStatus &&
                  (entry.note?.startsWith('Assigned to ') ||
                    entry.note?.startsWith('Reassigned from '))
                const timestamp = formatTimestamp(entry.created_at)
                return (
                  <li key={`${entry.created_at}-${index}`} className="activity-item">
                    <p className="activity-change">
                      {assignment ? (
                        <strong>Assignment</strong>
                      ) : sameStatus ? (
                        <strong>Request update</strong>
                      ) : entry.from_status ? (
                        <>
                          {activityStatusLabel(entry.from_status)}{' '}
                          <span aria-hidden="true">→</span>{' '}
                          <strong>{activityStatusLabel(entry.to_status)}</strong>
                        </>
                      ) : (
                        <strong>{activityStatusLabel(entry.to_status)}</strong>
                      )}
                    </p>
                    <p className="activity-meta">
                      {entry.changed_by_name ?? 'Unknown user'}
                      {timestamp && ` · ${timestamp}`}
                    </p>
                    {entry.note && <p className="activity-note">{entry.note}</p>}
                  </li>
                )
              })}
            </ol>
          )}
        </section>
      )}

      <p>
        <Link to="/organiser/events">← Back to my requests</Link>
      </p>
    </div>
  )
}
