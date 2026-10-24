import { useEffect, useState } from 'react'
import { Link, useInRouterContext } from 'react-router'
import { ApiError } from '../lib/api'
import { formatRange, formatTimestamp } from '../lib/events'
import { listVenues } from '../lib/venues'
import type { VenueSummary } from '../lib/venues'
import {
  BOOKING_STATUS_LABELS,
  CONFLICT_FLAG_LABEL,
  findReplacementPath,
  formatBookingPeriods,
  isLiveBooking,
  listEventVenueBookings,
  submitVenueBookings,
} from '../lib/venueBookings'
import type { VenueBooking, VenueRequest } from '../lib/venueBookings'
import { CancelAllBookingsDialog } from './CancelAllBookingsDialog'
import { CancelBookingDialog } from './CancelBookingDialog'
import { VenueBookingChangeForm } from './VenueBookingChangeForm'

interface Props {
  eventId: number
  expectedAttendance: number | null
  /** Called after venues are requested, changed or cancelled: the first
   *  request moves an approved event into planning, and every change is a line
   *  in the Activity Log, so the page reloads the event to show both. */
  onChanged?: () => void
}

/** "Find replacement" for a booking marked Venue Unavailable - Action Required.
 *  A router link where there is a router, a plain link otherwise. */
function FindReplacementLink({ booking }: { booking: VenueBooking }) {
  const inRouter = useInRouterContext()
  const to = findReplacementPath(booking)
  const label = `Find replacement for ${booking.venue.name} booking`
  return inRouter ? (
    <Link to={to} className="btn-link-accent" aria-label={label}>
      Find replacement
    </Link>
  ) : (
    <a href={to} className="btn-link-accent" aria-label={label}>
      Find replacement
    </a>
  )
}

/** What the Coordinator typed for one chosen venue. */
interface Needs {
  expected_attendance: string
  room_layout_preference: string
  accessibility_needs: string
  facilities_needs: string
}

const NO_NEEDS: Needs = {
  expected_attendance: '',
  room_layout_preference: '',
  accessibility_needs: '',
  facilities_needs: '',
}

/** The Coordinator's "request venues" card for one event being planned.
 *
 *  One or more venues are ticked, each with its own expected attendance,
 *  layout, accessibility and facilities (attendance defaults to the Event's
 *  total; blank needs use the Event's own). The event's date and time are
 *  copied from the Event, so each request always matches its schedule. A
 *  separate booking is made for each venue. With none ticked the
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
  const [bookingsLoadError, setBookingsLoadError] = useState<string | null>(null)
  const [loadingBookings, setLoadingBookings] = useState(true)
  // Changing or cancelling (SCRUM-96): at most one booking is being changed,
  // and one confirmation is open, at a time.
  const [changingId, setChangingId] = useState<number | null>(null)
  const [cancelling, setCancelling] = useState<VenueBooking | null>(null)
  const [cancellingAll, setCancellingAll] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    listEventVenueBookings(eventId)
      .then((b) => {
        if (!cancelled) {
          setBookings(b)
          setBookingsLoadError(null)
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return
        console.error('Failed to load event venue bookings.', { eventId, error: err })
        setBookings(null)
        setBookingsLoadError(
          err instanceof ApiError ? err.message : 'Could not load the existing venue bookings.',
        )
      })
      .finally(() => {
        if (!cancelled) setLoadingBookings(false)
      })
    // Every active venue, as on the Venues tab. Not narrowed by attendance:
    // a hidden venue is indistinguishable from a missing one, so a small
    // venue is flagged in its label instead.
    listVenues()
      .then((v) => !cancelled && setVenues(v.filter((venue) => venue.is_active)))
      .catch((err: unknown) => {
        if (cancelled) return
        console.error('Failed to load active venues for event booking.', { eventId, error: err })
        setVenues([])
        setLoadError(err instanceof ApiError ? err.message : 'Could not load venues.')
      })
    return () => {
      cancelled = true
    }
  }, [eventId])

  // A venue the event already has a live booking at -- pending, held or
  // approved -- cannot be requested again.
  const liveVenueIds = new Set(
    (bookings ?? []).filter((b) => isLiveBooking(b.status)).map((b) => b.venue.id),
  )

  /** Put the bookings the server returned in place of the ones shown. */
  function replaceBookings(updated: VenueBooking[]) {
    const byId = new Map(updated.map((b) => [b.id, b]))
    setBookings((current) => current?.map((b) => byId.get(b.id) ?? b) ?? current)
  }

  function done(message: string) {
    setNotice(message)
    onChanged?.()
  }

  async function reloadBookings() {
    setLoadingBookings(true)
    setBookingsLoadError(null)
    setBookings(null)
    try {
      setBookings(await listEventVenueBookings(eventId))
    } catch (err: unknown) {
      console.error('Failed to load event venue bookings.', { eventId, error: err })
      setBookingsLoadError(
        err instanceof ApiError ? err.message : 'Could not load the existing venue bookings.',
      )
    } finally {
      setLoadingBookings(false)
    }
  }

  async function reloadVenues() {
    setLoadError(null)
    try {
      setVenues((await listVenues()).filter((venue) => venue.is_active))
    } catch (err: unknown) {
      console.error('Failed to load active venues for event booking.', { eventId, error: err })
      setLoadError(err instanceof ApiError ? err.message : 'Could not load venues.')
    }
  }

  function toggle(venueId: number) {
    setChosen((current) => {
      const next = { ...current }
      if (venueId in next) delete next[venueId]
      else next[venueId] = {
        ...NO_NEEDS,
        expected_attendance: expectedAttendance?.toString() ?? '',
      }
      return next
    })
  }

  function setNeed(venueId: number, field: keyof Needs, value: string) {
    setChosen((current) => ({ ...current, [venueId]: { ...current[venueId], [field]: value } }))
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    for (const [id, needs] of Object.entries(chosen)) {
      const attendance = needs.expected_attendance.trim()
      if (attendance && (!Number.isInteger(Number(attendance)) || Number(attendance) <= 0)) {
        const venueName = venues.find((venue) => venue.id === Number(id))?.name ?? 'This venue'
        setError(`Expected attendance for ${venueName} must be a whole number greater than 0.`)
        return
      }
    }
    setSubmitting(true)
    setError(null)
    const requests: VenueRequest[] = Object.entries(chosen).map(([id, needs]) => ({
      venue_id: Number(id),
      expected_attendance: needs.expected_attendance.trim()
        ? Number(needs.expected_attendance)
        : null,
      room_layout_preference: needs.room_layout_preference,
      accessibility_needs: needs.accessibility_needs,
      facilities_needs: needs.facilities_needs,
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

      {bookingsLoadError && (
        <div>
          <p className="form-error" role="alert">{bookingsLoadError}</p>
          <p className="page-subtitle">
            Existing booking status could not be checked, so you cannot submit another request yet.
          </p>
          <button type="button" className="btn-secondary" onClick={() => void reloadBookings()}>
            Retry loading bookings
          </button>
        </div>
      )}
      {loadingBookings && <p role="status">Loading existing venue bookings…</p>}
      {notice && (
        <p role="status" className="field-hint">
          {notice}
        </p>
      )}

      {bookings && bookings.length > 0 && (
        <ul aria-label="Venue bookings for this event" className="booking-list">
          {bookings.map((b) => (
            <li key={b.id}>
              <strong>{b.venue.name}</strong> · {formatRange(b.start_time, b.end_time)} ·{' '}
              <span className="badge">{BOOKING_STATUS_LABELS[b.status]}</span>
              <p className="page-subtitle" aria-label={`Venue time for ${b.venue.name}`}>
                {formatBookingPeriods(b)}
              </p>
              {b.status === 'tentative_hold' && (
                <p className="notice" role="note">
                  Held until{' '}
                  {formatTimestamp(b.expires_at) ?? 'its expiry'}. Required action:{' '}
                  {b.hold_action ?? 'none given'}
                </p>
              )}
              {b.status === 'hold_expired' && (
                <p className="notice" role="note">
                  The hold lapsed{b.expires_at ? ` on ${formatTimestamp(b.expires_at)}` : ''} and{' '}
                  {b.venue.name} is no longer held for this event. Request it again or choose another
                  venue.
                </p>
              )}
              {b.conflict_flagged && (
                <p className="notice" role="note">
                  <span className="badge">Conflict flagged</span> {CONFLICT_FLAG_LABEL}. Venue Staff
                  are reviewing it; it is still held. Venue Unavailable - Action Required: your Event is not
                  cancelled, so find a replacement venue.
                </p>
              )}
              {b.status === 'replaced' && (
                <p className="notice" role="note">
                  Replaced by another venue booking. Kept here as history.
                </p>
              )}
              {b.replaces && (
                <p className="notice" role="note">
                  Replaces your booking at {b.replaces.venue.name}.
                </p>
              )}
              <Decision booking={b} />
              {isLiveBooking(b.status) && (
                <div className="form-actions">
                  {b.conflict_flagged && <FindReplacementLink booking={b} />}
                  <button
                    type="button"
                    className="btn-link-accent"
                    aria-label={`Change ${b.venue.name} booking`}
                    onClick={() => {
                      setNotice(null)
                      setChangingId(b.id)
                    }}
                  >
                    Change
                  </button>
                  <button
                    type="button"
                    className="btn-link-danger"
                    aria-label={`Cancel ${b.venue.name} booking`}
                    onClick={() => {
                      setNotice(null)
                      setCancelling(b)
                    }}
                  >
                    Cancel booking
                  </button>
                </div>
              )}
              {changingId === b.id && (
                <VenueBookingChangeForm
                  booking={b}
                  venues={venues}
                  takenVenueIds={
                    new Set(
                      (bookings ?? [])
                        .filter((o) => o.id !== b.id && isLiveBooking(o.status))
                        .map((o) => o.venue.id),
                    )
                  }
                  onSaved={(updated) => {
                    replaceBookings([updated])
                    setChangingId(null)
                    done('Sent back to Venue Staff for review.')
                  }}
                  onClose={() => setChangingId(null)}
                />
              )}
            </li>
          ))}
        </ul>
      )}

      {(bookings ?? []).some((b) => isLiveBooking(b.status)) && (
        <div className="form-actions">
          <button
            type="button"
            className="btn-secondary"
            onClick={() => {
              setNotice(null)
              setCancellingAll(true)
            }}
          >
            Cancel all venue bookings
          </button>
        </div>
      )}

      <form onSubmit={(e) => void submit(e)} noValidate>
        <p className="page-subtitle">
          Choose one or more venues. The event's date and time are sent with each request.
          Set attendance for each venue (defaults to the event total), then add its specific needs.
        </p>
        <fieldset disabled={submitting || bookings === null || bookingsLoadError !== null}>
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
                      <span>Expected attendance for {v.name}</span>
                      <input
                        type="number"
                        min="1"
                        step="1"
                        value={needs.expected_attendance}
                        onChange={(e) => setNeed(v.id, 'expected_attendance', e.target.value)}
                        placeholder="Enter attendance"
                      />
                    </label>
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
          <div>
            <p className="form-error" role="alert">{loadError}</p>
            <button type="button" className="btn-secondary" onClick={() => void reloadVenues()}>
              Retry loading venues
            </button>
          </div>
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

      {cancelling && (
        <CancelBookingDialog
          booking={cancelling}
          onCancelled={(updated) => {
            replaceBookings([updated])
            setCancelling(null)
            done('Booking cancelled. Venue Staff have been told.')
          }}
          onClose={() => setCancelling(null)}
        />
      )}
      {cancellingAll && (
        <CancelAllBookingsDialog
          eventId={eventId}
          onCancelled={(updated) => {
            replaceBookings(updated)
            setCancellingAll(false)
            done('All venue bookings cancelled. Venue Staff have been told.')
          }}
          onClose={() => setCancellingAll(false)}
        />
      )}
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
