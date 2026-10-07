import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../../lib/api'
import { formatRange, formatTimestamp } from '../../lib/events'
import {
  BOOKING_STATUS_LABELS,
  approveVenueBooking,
  listVenueBookingQueue,
  rejectVenueBooking,
} from '../../lib/venueBookings'
import type { VenueBooking } from '../../lib/venueBookings'

/** Venue Staff's review queue: every pending booking request, each carrying
 *  what is needed to decide on it -- the venue, the event's date and time,
 *  expected attendance, layout, and accessibility or facility needs -- and
 *  the two decisions, Approve and Reject. A decided request leaves the
 *  queue. */
export function VenueBookingQueue() {
  const [bookings, setBookings] = useState<VenueBooking[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [decided, setDecided] = useState<VenueBooking | null>(null)
  const confirmation = useRef<HTMLParagraphElement>(null)

  useEffect(() => {
    let cancelled = false
    listVenueBookingQueue()
      .then((b) => !cancelled && setBookings(b))
      .catch((err: unknown) => {
        if (!cancelled)
          setError(err instanceof ApiError ? err.message : 'Could not load booking requests.')
      })
    return () => {
      cancelled = true
    }
  }, [])

  // The decided card is gone, and the keyboard focus with it: put it on the
  // confirmation rather than leaving it at the top of the document.
  useEffect(() => {
    if (decided) confirmation.current?.focus()
  }, [decided])

  function onDecided(result: VenueBooking) {
    setBookings((current) => current?.filter((b) => b.id !== result.id) ?? null)
    setDecided(result)
  }

  return (
    <div>
      <h1>Booking requests</h1>
      <p className="page-subtitle">Pending venue booking requests from Event Coordinators.</p>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {decided && (
        <p className="notice" role="status" tabIndex={-1} ref={confirmation}>
          {BOOKING_STATUS_LABELS[decided.status]}: {decided.venue.name} for{' '}
          {decided.event.name ?? 'an untitled event'}. {decided.requested_by.name} can now see the
          decision.
        </p>
      )}
      {!error && bookings === null && <p>Loading…</p>}
      {bookings?.length === 0 && <p>No pending booking requests.</p>}

      {bookings?.map((b) => (
        <BookingCard key={b.id} booking={b} onDecided={onDecided} />
      ))}
    </div>
  )
}

function BookingCard({
  booking: b,
  onDecided,
}: {
  booking: VenueBooking
  onDecided: (result: VenueBooking) => void
}) {
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')
  const [alternative, setAlternative] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function decide(action: () => Promise<VenueBooking>) {
    setSaving(true)
    setError(null)
    try {
      onDecided(await action())
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not save the decision.')
      setSaving(false)
    }
  }

  return (
    <section className="card" aria-label={`Booking request for ${b.event.name ?? 'an event'}`}>
      <h2>{b.event.name ?? 'Untitled event'}</h2>
      {b.safety_recheck_reason && (
        <p className="notice" role="note">
          <span className="badge">Safety re-review</span> Already approved and still
          held. The Safety Officer asked for another look: {b.safety_recheck_reason}
        </p>
      )}
      <dl className="detail-list">
        {(
          [
            ['Venue', `${b.venue.name} — ${b.venue.location}`],
            ['Date and time', formatRange(b.start_time, b.end_time)],
            ['Expected attendance', b.expected_attendance?.toString() ?? 'Not given'],
            ['Layout requirements', b.room_layout_preference ?? 'None given'],
            ['Accessibility needs', b.accessibility_needs ?? 'None given'],
            ['Facility needs', b.venue_requirements ?? 'None given'],
            ['Requested by', `${b.requested_by.name} (${b.requested_by.email})`],
            ['Requested on', formatTimestamp(b.created_at) ?? ''],
          ] as const
        ).map(([label, value]) => (
          <div key={label} className="detail-row">
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>

      {rejecting ? (
        <form
          className="status-actions decision-form"
          onSubmit={(e) => {
            e.preventDefault()
            void decide(() => rejectVenueBooking(b.id, { reason, suggested_alternative: alternative }))
          }}
        >
          <p className="page-subtitle">
            Give a reason, an alternative, or both. The Event Coordinator sees what you write.
          </p>
          <label className="field">
            <span>Reason</span>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              maxLength={2000}
              rows={3}
              disabled={saving}
              autoFocus
            />
          </label>
          <label className="field">
            <span>Suggested alternative</span>
            <textarea
              value={alternative}
              onChange={(e) => setAlternative(e.target.value)}
              maxLength={2000}
              rows={3}
              disabled={saving}
            />
          </label>
          <div className="form-actions">
            <button
              type="submit"
              className="btn-primary"
              disabled={saving || (!reason.trim() && !alternative.trim())}
            >
              {saving ? 'Saving…' : 'Confirm rejection'}
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => setRejecting(false)}
              disabled={saving}
            >
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <div className="status-actions">
          <div className="form-actions">
            <button
              type="button"
              className="btn-primary"
              onClick={() => void decide(() => approveVenueBooking(b.id))}
              disabled={saving}
            >
              {saving ? 'Saving…' : 'Approve'}
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => setRejecting(true)}
              disabled={saving}
            >
              Reject
            </button>
          </div>
        </div>
      )}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </section>
  )
}
