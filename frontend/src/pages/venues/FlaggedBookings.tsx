import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../../lib/api'
import { formatRange } from '../../lib/events'
import {
  CONFLICT_FLAG_LABEL,
  cancelFlaggedBooking,
  describeConflict,
  formatBookingPeriods,
  keepFlaggedBooking,
  listFlaggedBookings,
} from '../../lib/venueBookings'
import type { VenueBooking } from '../../lib/venueBookings'

/** Venue Staff's list of approved bookings flagged because a setup or
 *  turnaround change made them overlap another booking. Each shows what it
 *  conflicts with and the overlapping period, and can be kept anyway or
 *  cancelled, either with a reason. A booking changed so it no longer
 *  overlaps drops off the list by itself. Cancelling a booking never cancels
 *  its Event. */
export function FlaggedBookings() {
  const [bookings, setBookings] = useState<VenueBooking[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [kept, setKept] = useState<{ booking: VenueBooking; cancelled: boolean } | null>(null)
  const confirmation = useRef<HTMLParagraphElement>(null)

  useEffect(() => {
    let cancelled = false
    listFlaggedBookings()
      .then((b) => !cancelled && setBookings(b))
      .catch((err: unknown) => {
        if (!cancelled)
          setError(err instanceof ApiError ? err.message : 'Could not load flagged bookings.')
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (kept) confirmation.current?.focus()
  }, [kept])

  function onResolved(result: VenueBooking, cancelled: boolean) {
    setBookings((current) => current?.filter((b) => b.id !== result.id) ?? null)
    setKept({ booking: result, cancelled })
  }

  return (
    <div>
      <h1>Flagged bookings</h1>
      <p className="page-subtitle">
        Approved bookings that now overlap another booking after a setup or turnaround change. They
        are not cancelled, but do not count as approved until resolved.
      </p>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {kept && (
        <p className="notice" role="status" tabIndex={-1} ref={confirmation}>
          {kept.cancelled ? 'Cancelled' : 'Kept'} {kept.booking.venue.name} for{' '}
          {kept.booking.event.name ?? 'an untitled event'}.{' '}
          {kept.cancelled
            ? 'The flag is cleared and the Coordinator is told. The Event is not cancelled.'
            : 'The flag is cleared.'}
        </p>
      )}
      {!error && bookings === null && <p>Loading…</p>}
      {bookings?.length === 0 && <p>No flagged bookings.</p>}

      {bookings?.map((b) => (
        <FlaggedCard key={b.id} booking={b} onResolved={onResolved} />
      ))}
    </div>
  )
}

function FlaggedCard({
  booking: b,
  onResolved,
}: {
  booking: VenueBooking
  onResolved: (result: VenueBooking, cancelled: boolean) => void
}) {
  const [reason, setReason] = useState('')
  const [reasonError, setReasonError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const inputId = `keep-reason-${b.id}`
  const errorId = `${inputId}-error`

  function keep(e: React.FormEvent) {
    e.preventDefault()
    void resolve(false)
  }

  async function resolve(cancel: boolean) {
    if (!reason.trim()) {
      setReasonError(`Enter a reason for ${cancel ? 'cancelling' : 'keeping'} this booking.`)
      return
    }
    setSaving(true)
    setReasonError(null)
    try {
      const act = cancel ? cancelFlaggedBooking : keepFlaggedBooking
      onResolved(await act(b.id, reason.trim()), cancel)
    } catch (err) {
      setReasonError(
        err instanceof ApiError ? err.message : `Could not ${cancel ? 'cancel' : 'keep'} the booking.`,
      )
      setSaving(false)
    }
  }

  return (
    <section className="card" aria-label={`Flagged booking for ${b.event.name ?? 'an event'}`}>
      <h2>{b.event.name ?? 'Untitled event'}</h2>
      <p className="notice" role="note">
        <span className="badge">Conflict flagged</span> {CONFLICT_FLAG_LABEL}.
      </p>
      <dl className="detail-list">
        <div className="detail-row">
          <dt>Venue</dt>
          <dd>
            {b.venue.name} — {b.venue.location}
          </dd>
        </div>
        <div className="detail-row">
          <dt>Date and time</dt>
          <dd>{formatRange(b.start_time, b.end_time)}</dd>
        </div>
        <div className="detail-row">
          <dt>Venue time held</dt>
          <dd>{formatBookingPeriods(b)}</dd>
        </div>
      </dl>
      <h3>Conflicts with</h3>
      {(b.conflicts ?? []).length === 0 ? (
        <p>No overlapping booking is listed.</p>
      ) : (
        <ul>
          {(b.conflicts ?? []).map((c) => {
            const d = describeConflict(c)
            return (
              <li key={c.booking_id ?? `unavailable-${c.event_start}`}>
                {d.unavailable ? (
                  <>
                    <strong>Venue unavailable</strong> ({d.reason ?? 'no reason given'}) {d.occupied}. Overlap:{' '}
                    {d.overlap}.
                  </>
                ) : (
                  <>
                    <strong>{d.name}</strong> holds the venue {d.occupied}. Overlap: {d.overlap}.
                  </>
                )}
              </li>
            )
          })}
        </ul>
      )}

      <form className="status-actions decision-form" onSubmit={keep} noValidate>
        <label className="field" htmlFor={inputId}>
          <span>Reason for keeping or cancelling {b.event.name ?? 'this booking'}</span>
          <textarea
            id={inputId}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            maxLength={2000}
            rows={3}
            disabled={saving}
            aria-invalid={reasonError ? true : undefined}
            aria-describedby={reasonError ? errorId : undefined}
          />
          {reasonError && (
            <span id={errorId} className="form-error" role="alert">
              {reasonError}
            </span>
          )}
        </label>
        <div className="form-actions">
          <button type="submit" className="btn-primary" disabled={saving}>
            {saving ? 'Saving…' : 'Keep anyway'}
          </button>
          <button type="button" className="btn-secondary" disabled={saving} onClick={() => void resolve(true)}>
            Cancel booking
          </button>
        </div>
      </form>
    </section>
  )
}
