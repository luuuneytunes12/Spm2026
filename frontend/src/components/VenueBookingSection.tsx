import { useEffect, useState } from 'react'
import { ApiError } from '../lib/api'
import { formatRange, formatTimestamp } from '../lib/events'
import { listVenues } from '../lib/venues'
import type { VenueSummary } from '../lib/venues'
import {
  BOOKING_STATUS_LABELS,
  listEventVenueBookings,
  submitVenueBookings,
} from '../lib/venueBookings'
import type { VenueBooking, VenueRequest } from '../lib/venueBookings'

interface Props {
  eventId: number
  expectedAttendance: number | null
  /** Called after venues are requested: the first request moves an approved
   *  event into planning, so the page reloads the event to show its status. */
  onChanged?: () => void
}

/** What the Coordinator typed for one chosen venue. */
interface Needs {
  room_layout_preference: string
  accessibility_needs: string
  facilities_needs: string
}

const NO_NEEDS: Needs = { room_layout_preference: '', accessibility_needs: '', facilities_needs: '' }

/** The Coordinator's "request venues" card for one event being planned.
 *
 *  One or more venues are ticked, each with the layout, accessibility and
 *  facilities it needs (left blank, a venue gets the Event's own). The
 *  event's date, time and attendance are not typed here: the server copies
 *  them from the event, so a request always matches what the Organiser asked
 *  for. A separate booking is made for each venue. With none ticked the
 *  submit is refused -- by the server, whose message is shown -- and nothing
 *  is created.
 *
 *  Every booking is listed with its own status and, once Venue Staff have
 *  decided, who decided and why. A venue that already has a live request
 *  cannot be ticked again; a rejected one can. */
export function VenueBookingSection({ eventId, expectedAttendance, onChanged }: Props) {
  const [bookings, setBookings] = useState<VenueBooking[] | null>(null)
  const [venues, setVenues] = useState<VenueSummary[]>([])
  const [chosen, setChosen] = useState<Record<number, Needs>>({})
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    listEventVenueBookings(eventId)
      .then((b) => !cancelled && setBookings(b))
      .catch(() => !cancelled && setBookings([]))
    // Every active venue, as on the Venues tab. Not narrowed by attendance:
    // a hidden venue is indistinguishable from a missing one, so a small
    // venue is flagged in its label instead.
    listVenues()
      .then((v) => !cancelled && setVenues(v.filter((venue) => venue.is_active)))
      .catch((err: unknown) => {
        if (cancelled) return
        setVenues([])
        setLoadError(err instanceof ApiError ? err.message : 'Could not load venues.')
      })
    return () => {
      cancelled = true
    }
  }, [eventId])

  const liveVenueIds = new Set(
    (bookings ?? []).filter((b) => b.status === 'pending' || b.status === 'approved').map((b) => b.venue.id),
  )

  function toggle(venueId: number) {
    setChosen((current) => {
      const next = { ...current }
      if (venueId in next) delete next[venueId]
      else next[venueId] = { ...NO_NEEDS }
      return next
    })
  }

  function setNeed(venueId: number, field: keyof Needs, value: string) {
    setChosen((current) => ({ ...current, [venueId]: { ...current[venueId], [field]: value } }))
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    const requests: VenueRequest[] = Object.entries(chosen).map(([id, needs]) => ({
      venue_id: Number(id),
      ...needs,
    }))
    try {
      const created = await submitVenueBookings(eventId, requests)
      setBookings((current) => [...created, ...(current ?? [])])
      setChosen({})
      onChanged?.()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not submit the booking request.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="card" aria-labelledby="venue-booking-heading">
      <h2 id="venue-booking-heading">Venue bookings</h2>

      {bookings && bookings.length > 0 && (
        <ul aria-label="Venue bookings for this event" className="booking-list">
          {bookings.map((b) => (
            <li key={b.id}>
              <strong>{b.venue.name}</strong> · {formatRange(b.start_time, b.end_time)} ·{' '}
              <span className="badge">{BOOKING_STATUS_LABELS[b.status]}</span>
              <Decision booking={b} />
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={(e) => void submit(e)} noValidate>
        <p className="page-subtitle">
          Choose one or more venues. The event's date, time and expected attendance are sent with
          each request; add what you need of each venue below it.
        </p>
        <fieldset disabled={submitting}>
          <legend>Venues</legend>
          {venues.map((v) => {
            const live = liveVenueIds.has(v.id)
            const needs = chosen[v.id]
            return (
              <div key={v.id} className="venue-choice">
                <label>
                  <input
                    type="checkbox"
                    checked={needs !== undefined}
                    disabled={live}
                    onChange={() => toggle(v.id)}
                  />{' '}
                  {v.name} — {v.location} (capacity {v.capacity}
                  {expectedAttendance !== null && v.capacity < expectedAttendance ? ', too small' : ''})
                  {live ? ' — already requested' : ''}
                </label>
                {needs && (
                  <div className="venue-needs">
                    <label className="field">
                      <span>Room layout for {v.name}</span>
                      <input
                        value={needs.room_layout_preference}
                        onChange={(e) => setNeed(v.id, 'room_layout_preference', e.target.value)}
                        placeholder="As the event says"
                      />
                    </label>
                    <label className="field">
                      <span>Accessibility needs for {v.name}</span>
                      <input
                        value={needs.accessibility_needs}
                        onChange={(e) => setNeed(v.id, 'accessibility_needs', e.target.value)}
                        placeholder="As the event says"
                      />
                    </label>
                    <label className="field">
                      <span>Facilities for {v.name}</span>
                      <input
                        value={needs.facilities_needs}
                        onChange={(e) => setNeed(v.id, 'facilities_needs', e.target.value)}
                        placeholder="As the event says"
                      />
                    </label>
                  </div>
                )}
              </div>
            )
          })}
        </fieldset>
        {loadError && (
          <p className="form-error" role="alert">
            {loadError}
          </p>
        )}
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Submitting…' : 'Submit booking request'}
        </button>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
      </form>
    </section>
  )
}

/** Venue Staff's decision on one request: who decided and when, and for a
 *  rejection the reason and/or the alternative they suggest. Nothing while
 *  the request is still pending. */
function Decision({ booking }: { booking: VenueBooking }) {
  if (!booking.reviewed_at) return null
  const rows = [
    ['Reason', booking.decision_notes],
    ['Suggested alternative', booking.suggested_alternative],
    [
      'Decided',
      `${formatTimestamp(booking.reviewed_at)}${booking.reviewed_by ? ` by ${booking.reviewed_by.name}` : ''}`,
    ],
  ] as const
  return (
    <dl className="detail-list">
      {rows.map(
        ([label, value]) =>
          value && (
            <div key={label} className="detail-row">
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ),
      )}
    </dl>
  )
}
