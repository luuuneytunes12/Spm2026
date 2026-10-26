import { useEffect, useState } from 'react'
import { ApiError } from '../lib/api'
import { EQUIPMENT_PROGRESS_LABELS, getOwnEventProgress, PROGRESS_STATUSES } from '../lib/eventProgress'
import type { EventProgress } from '../lib/eventProgress'
import { EventStatus, formatRange, formatTimestamp } from '../lib/events'
import { BOOKING_STATUS_LABELS } from '../lib/venueBookings'

/** How the Event's planning is coming along, for its own Organiser: each
 *  Venue Booking (flagging one that needs a replacement venue), each
 *  equipment line, and the Safety Check -- with the reason if it sent the
 *  Event back. Renders nothing before planning starts. */
export function EventStatusTracker({ eventId, status }: { eventId: number; status: EventStatus }) {
  const [progress, setProgress] = useState<EventProgress | null>(null)
  const [error, setError] = useState<string | null>(null)
  const shown = PROGRESS_STATUSES.includes(status)

  useEffect(() => {
    if (!shown) return
    let cancelled = false
    getOwnEventProgress(eventId)
      .then((p) => {
        if (!cancelled) setProgress(p)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : 'Could not load the planning progress.')
      })
    return () => {
      cancelled = true
    }
  }, [eventId, status, shown])

  if (!shown) return null
  if (error) {
    return (
      <p className="form-error" role="alert">
        {error}
      </p>
    )
  }
  if (!progress) return null

  const { venue_bookings: bookings, equipment, safety_check: safety } = progress
  return (
    <section className="card stack-tight" aria-labelledby="planning-progress-heading">
      <h2 id="planning-progress-heading">Planning progress</h2>

      <h3>Venue bookings</h3>
      {bookings.length === 0 ? (
        <p className="page-subtitle">No venue has been requested yet.</p>
      ) : (
        <ul className="activity-list" aria-label="Venue bookings">
          {bookings.map((b) => (
            <li key={b.id} className="activity-item">
              <p className="activity-change">
                <strong>{b.venue_name}</strong> · <span>{BOOKING_STATUS_LABELS[b.status] ?? b.status}</span>
              </p>
              <p className="activity-meta">{formatRange(b.start_time, b.end_time)}</p>
              {b.needs_replacement && (
                <p className="field-error">This venue fell through. A replacement venue is needed.</p>
              )}
              {b.replaces_venue_name && (
                <p className="activity-note">Replacement for {b.replaces_venue_name}.</p>
              )}
            </li>
          ))}
        </ul>
      )}

      <h3>Equipment</h3>
      {equipment.length === 0 ? (
        <p className="page-subtitle">No equipment was requested.</p>
      ) : (
        <ul className="activity-list" aria-label="Equipment progress">
          {equipment.map((line) => (
            <li key={line.id} className="activity-item">
              <p className="activity-change">
                <strong>{line.equipment_name}</strong> × {line.quantity_requested} ·{' '}
                <span>{EQUIPMENT_PROGRESS_LABELS[line.status] ?? line.status}</span>
              </p>
            </li>
          ))}
        </ul>
      )}

      <h3>Safety Check</h3>
      <p>
        Safety Check: <strong>{safety.stage}</strong>
      </p>
      {safety.sent_back && (
        <div role="note" className="notice">
          <p>
            <strong>{safety.sent_back.result}</strong>
            {safety.sent_back.decided_by_name && ` by ${safety.sent_back.decided_by_name}`}
            {formatTimestamp(safety.sent_back.decided_at) && ` · ${formatTimestamp(safety.sent_back.decided_at)}`}
          </p>
          <p>Reason: {safety.sent_back.reason}</p>
        </div>
      )}
    </section>
  )
}
