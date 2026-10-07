import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { ApiError } from '../../lib/api'
import {
  EVENT_STATUS_LABELS,
  EventStatus,
  formatRange,
  formatTimestamp,
} from '../../lib/events'
import {
  approveSafetyCheck,
  getSafetyCheck,
  rejectSafetyCheck,
  requestSafetyChanges,
} from '../../lib/safetyChecks'
import type { SafetyCheckDetail } from '../../lib/safetyChecks'

type Decision = 'request-changes' | 'reject'

function statusLabel(status: string): string {
  return EVENT_STATUS_LABELS[status as EventStatus] ?? status
}

function listOrNone(values: string[]): string {
  return values.length ? values.join(', ') : 'None recorded'
}

/** One event's Operational Safety Check: what is needed to judge it, and
 *  the three decisions -- approve, request changes to marked items, or
 *  reject the whole arrangement. */
export function SafetyCheckView() {
  const { id } = useParams()
  const [event, setEvent] = useState<SafetyCheckDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [decision, setDecision] = useState<Decision | null>(null)
  const [reason, setReason] = useState('')
  const [markedBookings, setMarkedBookings] = useState<number[]>([])
  const [markedLines, setMarkedLines] = useState<number[]>([])
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    let cancelled = false
    getSafetyCheck(Number(id))
      .then((e) => !cancelled && setEvent(e))
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : 'Could not load this event.')
      })
    return () => {
      cancelled = true
    }
  }, [id])

  async function decide(action: () => Promise<unknown>, message: string) {
    if (!event) return
    setSaving(true)
    setSaveError(null)
    try {
      await action()
      setEvent(await getSafetyCheck(event.id))
      setDecision(null)
      setDone(message)
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : 'Could not save the decision.')
    } finally {
      setSaving(false)
    }
  }

  function submitDecision(e: React.FormEvent) {
    e.preventDefault()
    if (!event || !decision) return
    if (!reason.trim()) {
      setSaveError('Give a reason before saving the decision.')
      return
    }
    if (decision === 'reject') {
      void decide(() => rejectSafetyCheck(event.id, reason), 'Safety arrangement rejected.')
      return
    }
    const bookingIds = markedBookings
    if (bookingIds.length === 0 && markedLines.length === 0) {
      setSaveError('Mark at least one venue booking or equipment item that needs changing.')
      return
    }
    void decide(
      () => requestSafetyChanges(event.id, reason, bookingIds, markedLines),
      'Changes requested.',
    )
  }

  if (error) {
    return (
      <p className="form-error" role="alert">
        {error}
      </p>
    )
  }
  if (!event) return <p>Loading…</p>

  const awaiting = event.status === EventStatus.AWAITING_SAFETY_CHECK
  const marking = decision === 'request-changes'

  return (
    <div className="stack">
      <header className="page-header">
        <h1>{event.name ?? 'Untitled event'}</h1>
        <p className="page-subtitle">
          {formatRange(event.proposed_start, event.proposed_end)} ·{' '}
          <span className="badge badge-accent">{statusLabel(event.status)}</span>
        </p>
      </header>

      {done && (
        <p className="notice" role="status">
          {done}
        </p>
      )}

      <section className="card" aria-labelledby="event-heading">
        <h2 id="event-heading">Event</h2>
        <dl className="detail-list">
          {(
            [
              ['Expected attendance', event.expected_attendance?.toString() ?? 'Not given'],
              ['Layout requested', event.room_layout_preference ?? 'None given'],
              ['Accessibility requirements', event.accessibility_needs ?? 'None given'],
              ['Special arrangements', event.special_arrangements ?? 'None given'],
              ['Event Organiser', event.organiser.name],
              ['Event Coordinator', event.coordinator?.name ?? 'Unassigned'],
            ] as const
          ).map(([label, value]) => (
            <div key={label} className="detail-row">
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="card" aria-labelledby="venue-heading">
        <h2 id="venue-heading">Venue</h2>
        {event.venue_bookings.length > 0 ? (
          event.venue_bookings.map((booking) => (
            <div key={booking.id} className="card stack">
              <h3>{booking.venue.name} — {booking.venue.location}</h3>
              <dl className="detail-list">
                {(
                  [
                    ['Capacity', booking.venue.capacity.toString()],
                    ['Supported layouts', listOrNone(booking.venue.supported_layouts)],
                    ['Accessibility features', listOrNone(booking.venue.accessibility_features)],
                    ['Emergency access', booking.venue.emergency_access ?? 'None recorded'],
                    ['Known restrictions', booking.venue.known_restrictions ?? 'None recorded'],
                  ] as const
                ).map(([label, value]) => (
                  <div key={label} className="detail-row">
                    <dt>{label}</dt>
                    <dd>{value}</dd>
                  </div>
                ))}
              </dl>
              {booking.safety_recheck_reason && (
                <p>
                  <span className="badge">Awaiting re-review</span> {booking.safety_recheck_reason}
                </p>
              )}
              {marking && (
                <label className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={markedBookings.includes(booking.id)}
                    onChange={(e) =>
                      setMarkedBookings((current) =>
                        e.target.checked
                          ? [...current, booking.id]
                          : current.filter((id) => id !== booking.id),
                      )
                    }
                  />{' '}
                  Venue booking needs changes
                </label>
              )}
            </div>
          ))
        ) : (
          <p className="text-muted">No approved venue booking.</p>
        )}
      </section>

      <section className="card" aria-labelledby="equipment-heading">
        <h2 id="equipment-heading">Equipment</h2>
        {event.equipment.length === 0 ? (
          <p className="text-muted">No equipment requested.</p>
        ) : (
          <ul>
            {event.equipment.map((line) => (
              <li key={line.id}>
                {marking ? (
                  <label className="checkbox-row">
                    <input
                      type="checkbox"
                      checked={markedLines.includes(line.id)}
                      onChange={(e) =>
                        setMarkedLines((current) =>
                          e.target.checked
                            ? [...current, line.id]
                            : current.filter((x) => x !== line.id),
                        )
                      }
                    />{' '}
                    {line.quantity_requested} × {line.equipment_name}
                  </label>
                ) : (
                  <>
                    {line.quantity_requested} × {line.equipment_name}
                  </>
                )}{' '}
                · Placement: {line.placement_notes ?? 'Not recorded'}
                {line.safety_recheck_reason && (
                  <>
                    {' '}
                    <span className="badge">Awaiting re-review</span> {line.safety_recheck_reason}
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {awaiting && (
        <section className="card status-actions" aria-labelledby="decision-heading">
          <h2 id="decision-heading">Decision</h2>
          {decision ? (
            <form className="stack decision-form" onSubmit={submitDecision} noValidate>
              <p className="page-subtitle">
                {decision === 'reject'
                  ? 'Every venue and equipment arrangement goes back for review. Nothing is cancelled.'
                  : 'Mark the venue booking or equipment above that needs changing. Only those go back for review.'}
              </p>
              <div className="field">
                <label htmlFor="safety-reason">Reason</label>
                <textarea
                  id="safety-reason"
                  required
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
              </div>
              <div className="form-actions">
                <button type="submit" className="btn-primary" disabled={saving}>
                  {saving
                    ? 'Saving…'
                    : decision === 'reject'
                      ? 'Confirm rejection'
                      : 'Send change request'}
                </button>
                <button type="button" onClick={() => setDecision(null)} disabled={saving}>
                  Back
                </button>
              </div>
            </form>
          ) : (
            <div className="form-actions">
              <button
                type="button"
                className="btn-primary"
                disabled={saving}
                onClick={() => void decide(() => approveSafetyCheck(event.id), 'Safety Check passed. The event is confirmed.')}
              >
                Approve
              </button>
              <button type="button" onClick={() => setDecision('request-changes')}>
                Request changes
              </button>
              <button type="button" onClick={() => setDecision('reject')}>
                Reject
              </button>
            </div>
          )}
          {saveError && (
            <p className="form-error" role="alert">
              {saveError}
            </p>
          )}
        </section>
      )}

      <section className="card" aria-labelledby="activity-heading">
        <h2 id="activity-heading">Activity log</h2>
        <ol className="activity-list" aria-label="Activity log">
          {event.activity.map((entry) => (
            <li key={`${entry.created_at}-${entry.to_status}`} className="activity-item">
              <p className="activity-change">
                {entry.from_status && entry.from_status !== entry.to_status && (
                  <>
                    {statusLabel(entry.from_status)} <span aria-hidden="true">→</span>{' '}
                  </>
                )}
                <strong>{statusLabel(entry.to_status)}</strong>
              </p>
              <p className="activity-meta">
                {entry.changed_by_name ?? 'Unknown'} · {formatTimestamp(entry.created_at)}
              </p>
              {entry.note && <p className="activity-note">{entry.note}</p>}
            </li>
          ))}
        </ol>
      </section>

      <p>
        <Link to="/safety-checks">← Back to safety checks</Link>
      </p>
    </div>
  )
}
