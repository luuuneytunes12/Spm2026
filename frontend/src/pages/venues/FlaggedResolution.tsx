import { useState } from 'react'
import { ApiError } from '../../lib/api'
import { cancelFlaggedBooking, keepFlaggedBooking } from '../../lib/venueBookings'
import type { VenueBooking } from '../../lib/venueBookings'

/** Keep-anyway / Cancel-booking form for a flagged booking; both need a reason. */
export function FlaggedResolution({
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
    <form
      className="status-actions decision-form"
      onSubmit={(e) => {
        e.preventDefault()
        void resolve(false)
      }}
      noValidate
    >
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
  )
}
