import { useId, useState } from 'react'
import { ApiError } from '../lib/api'
import {
  BOOKING_STATUS_LABELS,
  cancelAllVenueBookings,
  listCancellableVenueBookings,
} from '../lib/venueBookings'
import type { VenueBooking } from '../lib/venueBookings'
import { Dialog } from './Dialog'

interface Props {
  eventId: number
  /** Called with the bookings as the server now holds them. */
  onCancelled: (updated: VenueBooking[]) => void
  onClose: () => void
}

/** Cancel every live booking of an event, in two steps.
 *
 *  First a plain question. Then the bookings that would be cancelled, listed
 *  from the SERVER -- not from what the page remembers -- and a second
 *  confirmation. What is sent is exactly the ids that were listed, so if the
 *  live bookings changed in between the server refuses; the list is then
 *  shown again, fresh, and asks again. It is never retried on its own. */
export function CancelAllBookingsDialog({ eventId, onCancelled, onClose }: Props) {
  const reasonId = useId()
  const [listed, setListed] = useState<VenueBooking[] | null>(null)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)

  async function loadList() {
    setProblem(null)
    setBusy(true)
    try {
      setListed(await listCancellableVenueBookings(eventId))
    } catch (err) {
      setProblem(err instanceof ApiError ? err.message : 'Could not load the bookings.')
    } finally {
      setBusy(false)
    }
  }

  async function confirm() {
    if (!listed) return
    setProblem(null)
    setBusy(true)
    try {
      onCancelled(
        await cancelAllVenueBookings(
          eventId,
          listed.map((b) => b.id),
          reason.trim() || undefined,
        ),
      )
    } catch (err) {
      setProblem(err instanceof ApiError ? err.message : 'Could not cancel the bookings.')
      setBusy(false)
      // The list went stale: show the live one now, and ask again.
      if (err instanceof ApiError && err.status === 409) {
        try {
          setListed(await listCancellableVenueBookings(eventId))
        } catch {
          /* the message above stands */
        }
      }
    }
  }

  if (listed === null) {
    return (
      <Dialog title="Cancel all venue bookings?" busy={busy} onClose={onClose}>
        <p className="modal-warning">
          This will cancel every live venue booking of this event. The event itself is not
          cancelled.
        </p>
        {problem && (
          <p className="form-error" role="alert">
            {problem}
          </p>
        )}
        <div className="form-actions">
          <button type="button" className="btn-primary" disabled={busy} onClick={() => void loadList()}>
            Continue
          </button>
          <button type="button" className="btn-secondary" disabled={busy} onClick={onClose}>
            Keep bookings
          </button>
        </div>
      </Dialog>
    )
  }

  return (
    <Dialog title="Confirm cancelling these bookings" busy={busy} onClose={onClose}>
      {listed.length === 0 ? (
        <p>There are no live bookings to cancel.</p>
      ) : (
        <>
          <p className="modal-warning">
            These bookings will be cancelled, and Venue Staff will be told. The event itself is not
            cancelled.
          </p>
          <ul aria-label="Bookings to be cancelled">
            {listed.map((b) => (
              <li key={b.id}>
                {b.venue.name} &mdash; {BOOKING_STATUS_LABELS[b.status]}
              </li>
            ))}
          </ul>
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
        </>
      )}
      {problem && (
        <p className="form-error" role="alert">
          {problem}
        </p>
      )}
      <div className="form-actions">
        {listed.length > 0 && (
          <button type="button" className="btn-primary" disabled={busy} onClick={() => void confirm()}>
            {busy ? 'Cancelling…' : 'Cancel all these bookings'}
          </button>
        )}
        <button type="button" className="btn-secondary" disabled={busy} onClick={onClose}>
          Go back
        </button>
      </div>
    </Dialog>
  )
}
