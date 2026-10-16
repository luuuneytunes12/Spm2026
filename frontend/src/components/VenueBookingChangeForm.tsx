import { useEffect, useId, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError } from '../lib/api'
import { changeVenueBooking } from '../lib/venueBookings'
import type { VenueBooking, VenueBookingChanges } from '../lib/venueBookings'
import { listVenues } from '../lib/venues'
import type { VenueSummary } from '../lib/venues'

interface Props {
  booking: VenueBooking
  /** Every active venue. */
  venues: VenueSummary[]
  /** Venues the event already has ANOTHER live booking at: not offered. */
  takenVenueIds: ReadonlySet<number>
  /** Called with the booking as the server now holds it. */
  onSaved: (updated: VenueBooking) => void
  onClose: () => void
}

type Need = 'room_layout_preference' | 'accessibility_needs' | 'facilities_needs'
type ChangeField = Need | 'expected_attendance'

const NEEDS: { field: Need; label: string }[] = [
  { field: 'room_layout_preference', label: 'Room layout' },
  { field: 'accessibility_needs', label: 'Accessibility needs' },
  { field: 'facilities_needs', label: 'Facilities' },
]

function describe(v: { name: string; location: string; capacity: number }): string {
  return `${v.name} — ${v.location} (capacity ${v.capacity})`
}

/** What the Coordinator is told will happen to the booking they are changing. */
function consequence(status: VenueBooking['status']): string {
  if (status === 'approved')
    return 'This booking will go back to Pending and will not count as approved until Venue Staff approve it again.'
  if (status === 'tentative_hold')
    return 'The hold will be released, and this goes back to Venue Staff as a pending request.'
  return 'Venue Staff will see the change in their queue.'
}

/** How a venue that is booked or closed at the event's time is marked. */
const NOT_FREE_TAG = 'not free at this time'

/** Change one booking: its venue, and what is needed of it. No time -- a
 *  booking has the event's. Only what differs is sent, and a need emptied is
 *  sent as null, which puts it back to what the event says. The rules are the
 *  server's; this shows its own words when it refuses.
 *
 *  A venue that is not free at the event's time is TAGGED, not hidden or
 *  refused: Venue Staff decide when they review the booking, as for a new
 *  request, but the Coordinator should not have to learn it afterwards. Which
 *  venues are free is asked of the existing venue search with the event's
 *  window. If that cannot be answered nothing is tagged, and the form says so. */
export function VenueBookingChangeForm({ booking, venues, takenVenueIds, onSaved, onClose }: Props) {
  const ids = useId()
  const initial: Record<ChangeField, string> = {
    expected_attendance: booking.expected_attendance?.toString() ?? '',
    room_layout_preference: booking.room_layout_preference ?? '',
    accessibility_needs: booking.accessibility_needs ?? '',
    facilities_needs: booking.facilities_needs ?? '',
  }
  const [venueId, setVenueId] = useState(String(booking.venue.id))
  const [needs, setNeeds] = useState(initial)
  const [attendance, setAttendance] = useState(initial.expected_attendance)
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  // The venues free for the event's time; null until known, or if it could
  // not be found out.
  const [freeIds, setFreeIds] = useState<ReadonlySet<number> | null>(null)
  const [checkFailed, setCheckFailed] = useState(false)

  useEffect(() => {
    // The booking's window is the event's, so it is the window to ask about.
    let cancelled = false
    listVenues({ start: booking.start_time, end: booking.end_time })
      .then((free) => {
        if (!cancelled) setFreeIds(new Set(free.map((v) => v.id)))
      })
      .catch(() => {
        if (!cancelled) setCheckFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [booking.start_time, booking.end_time])

  // Where it is now, then every other active venue the event is not already at.
  const others = venues.filter((v) => v.id !== booking.venue.id && !takenVenueIds.has(v.id))
  const notFree = (id: number) => id !== booking.venue.id && freeIds !== null && !freeIds.has(id)

  const venueChanged = Number(venueId) !== booking.venue.id
  const changedNeeds = NEEDS.filter(({ field }) => needs[field].trim() !== initial[field].trim())
  const attendanceChanged =
    attendance.trim() !== initial.expected_attendance.trim() &&
    (attendance.trim() !== '' || booking.attendance_is_overridden === true)
  const dirty = venueChanged || changedNeeds.length > 0 || attendanceChanged

  async function save(e: FormEvent) {
    e.preventDefault()
    const trimmedAttendance = attendance.trim()
    if (
      trimmedAttendance &&
      (!Number.isInteger(Number(trimmedAttendance)) || Number(trimmedAttendance) <= 0)
    ) {
      setProblem('Expected attendance must be a whole number greater than 0.')
      return
    }
    const changes: VenueBookingChanges = {}
    if (venueChanged) changes.venue_id = Number(venueId)
    if (attendanceChanged) {
      changes.expected_attendance = trimmedAttendance ? Number(trimmedAttendance) : null
    }
    for (const { field } of changedNeeds) changes[field] = needs[field].trim() || null

    setProblem(null)
    setBusy(true)
    try {
      onSaved(await changeVenueBooking(booking.id, changes))
    } catch (err) {
      setProblem(err instanceof ApiError ? err.message : 'Could not change the booking.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="booking-panel" aria-labelledby={`${ids}-heading`}>
      <h3 id={`${ids}-heading`} className="requirement-subtitle">
        Change {booking.venue.name} booking
      </h3>
      <p className="field-hint">{consequence(booking.status)}</p>
      <form onSubmit={(e) => void save(e)} noValidate className="stack-tight">
        <div className="field">
          <label htmlFor={`${ids}-attendance`}>Expected attendance for {booking.venue.name}</label>
          <input
            id={`${ids}-attendance`}
            type="number"
            min="1"
            step="1"
            value={attendance}
            placeholder="Use the event's attendance"
            onChange={(e) => setAttendance(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor={`${ids}-venue`}>Venue</label>
          <select id={`${ids}-venue`} value={venueId} onChange={(e) => setVenueId(e.target.value)}>
            <option value={booking.venue.id}>{describe(booking.venue)}</option>
            {others.map((v) => (
              <option key={v.id} value={v.id}>
                {describe(v)}
                {notFree(v.id) ? ` — ${NOT_FREE_TAG}` : ''}
              </option>
            ))}
          </select>
          {notFree(Number(venueId)) && (
            <p className="notice" role="note">
              This venue looks unavailable at the event's time. You can still ask for it; Venue Staff
              will decide.
            </p>
          )}
          {checkFailed && (
            <p className="field-hint">
              Availability could not be checked, so no venue is marked. Venue Staff will check when
              they review the booking.
            </p>
          )}
        </div>
        {NEEDS.map(({ field, label }) => (
          <div key={field} className="field">
            <label htmlFor={`${ids}-${field}`}>{label}</label>
            <input
              id={`${ids}-${field}`}
              value={needs[field]}
              placeholder="As the event says"
              onChange={(e) => setNeeds({ ...needs, [field]: e.target.value })}
            />
          </div>
        ))}
        {problem && (
          <p className="form-error" role="alert">
            {problem}
          </p>
        )}
        <div className="form-actions">
          <button type="submit" className="btn-secondary" disabled={busy || !dirty}>
            Save change
          </button>
          <button type="button" className="btn-link-muted" disabled={busy} onClick={onClose}>
            Discard changes
          </button>
        </div>
      </form>
    </section>
  )
}
