import { useId, useState } from 'react'
import { ApiError } from '../lib/api'
import { cancelVenueBooking } from '../lib/venueBookings'
import type { VenueBooking } from '../lib/venueBookings'
import { Dialog } from './Dialog'

interface Props {
  booking: VenueBooking
  /** Called with the booking as the server now holds it. */
  onCancelled: (updated: VenueBooking) => void
  onClose: () => void
}

/** Confirm cancelling ONE booking. Nothing is sent until the Coordinator says
 *  so; the reason is optional and goes in the Activity Log and to Venue Staff. */
export function CancelBookingDialog({ booking, onCancelled, onClose }: Props) {
  const reasonId = useId()
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)

  async function confirm() {
    setProblem(null)
    setBusy(true)
    try {
      onCancelled(await cancelVenueBooking(booking.id, reason.trim() || undefined))
    } catch (err) {
      setProblem(err instanceof ApiError ? err.message : 'Could not cancel the booking.')
      setBusy(false)
    }
  }

  return (
    <Dialog title={`Cancel ${booking.venue.name} booking?`} busy={busy} onClose={onClose}>
      <p className="modal-warning">
        Only this booking is cancelled. The other bookings are not affected, and neither is the
        event. Venue Staff will be told.
      </p>
      <div className="field">
        <label htmlFor={reasonId}>Reason (optional)</label>
        <textarea
          id={reasonId}
          rows={3}
          maxLength={2000}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </div>
      {problem && (
        <p className="form-error" role="alert">
          {problem}
        </p>
      )}
      <div className="form-actions">
        <button type="button" className="btn-primary" disabled={busy} onClick={() => void confirm()}>
          {busy ? 'Cancelling…' : 'Yes, cancel booking'}
        </button>
        <button type="button" className="btn-secondary" disabled={busy} onClick={onClose}>
          Keep booking
        </button>
      </div>
    </Dialog>
  )
}
