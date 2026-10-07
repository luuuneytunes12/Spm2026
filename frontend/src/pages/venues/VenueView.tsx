import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { useAuth } from '../../auth/useAuth'
import { ApiError } from '../../lib/api'
import { fromDateTimeLocal } from '../../lib/events'
import { Role } from '../../lib/roles'
import { getVenue, recordVenueUnavailability } from '../../lib/venues'
import type { VenueDetail } from '../../lib/venues'
import { VenueSuitability } from './VenueSuitability'

/** A list field as chips, or an explicit "None recorded" -- an empty list
 *  must read as "nothing recorded", not as a missing row. */
function ChipList({ items, label }: { items: string[]; label: string }) {
  if (items.length === 0) return <span className="text-muted">None recorded</span>
  return (
    <ul className="chip-list" aria-label={label}>
      {items.map((item) => (
        <li key={item} className="chip">
          {item}
        </li>
      ))}
    </ul>
  )
}

/** Operating hours are free text; one entry per line is shown as a list. */
function OperatingHours({ value }: { value: string | null }) {
  const lines = (value ?? '').split('\n').map((line) => line.trim()).filter(Boolean)
  if (lines.length === 0) return <span className="text-muted">Not recorded</span>
  if (lines.length === 1) return <>{lines[0]}</>
  return (
    <ul className="detail-value-list">
      {lines.map((line, i) => (
        <li key={i}>{line}</li>
      ))}
    </ul>
  )
}

/** Everything an internal user needs to judge whether a venue suits an
 *  event. Read-only by design. */
export function VenueView() {
  const { id } = useParams()
  const { user } = useAuth()
  const [venue, setVenue] = useState<VenueDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [unavailableFrom, setUnavailableFrom] = useState('')
  const [unavailableUntil, setUnavailableUntil] = useState('')
  const [unavailableReason, setUnavailableReason] = useState('')
  const [savingUnavailability, setSavingUnavailability] = useState(false)
  const [unavailabilityError, setUnavailabilityError] = useState<string | null>(null)
  const [unavailabilityNotice, setUnavailabilityNotice] = useState<string | null>(null)

  async function markUnavailable(event: import('react').FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const start = fromDateTimeLocal(unavailableFrom)
    const end = fromDateTimeLocal(unavailableUntil)
    if (!start || !end || new Date(end) <= new Date(start)) {
      setUnavailabilityError('Enter a valid period with an end after the start.')
      return
    }
    setSavingUnavailability(true)
    setUnavailabilityError(null)
    setUnavailabilityNotice(null)
    try {
      const result = await recordVenueUnavailability(Number(id), {
        start_time: start,
        end_time: end,
        reason: unavailableReason,
      })
      setUnavailabilityNotice(
        `Unavailable period recorded. ${result.affected_booking_ids.length} existing booking(s) are affected; they were not cancelled.`,
      )
      setUnavailableReason('')
    } catch (err: unknown) {
      setUnavailabilityError(
        err instanceof ApiError ? err.message : 'Could not record venue unavailability.',
      )
    } finally {
      setSavingUnavailability(false)
    }
  }

  useEffect(() => {
    if (!id) return
    let cancelled = false
    getVenue(Number(id))
      .then((v) => {
        if (!cancelled) setVenue(v)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(
          err instanceof ApiError && err.status === 404
            ? 'Venue not found.'
            : err instanceof ApiError
              ? err.message
              : 'Could not load this venue.',
        )
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [id])

  const back = (
    <p>
      <Link to="/venues">← Back to venues</Link>
    </p>
  )

  if (loading) return null

  if (error || !venue) {
    return (
      <div className="stack">
        <p className="form-error" role="alert">
          {error ?? 'Venue not found.'}
        </p>
        {back}
      </div>
    )
  }

  return (
    <div className="stack">
      <header className="page-header">
        <h1>{venue.name}</h1>
        {!venue.is_active && (
          <p className="page-subtitle">
            <span className="badge badge-muted">Inactive</span>
          </p>
        )}
      </header>

      <section className="card">
        <h2>Overview</h2>
        <dl className="detail-list">
          <div className="detail-row">
            <dt>Location</dt>
            <dd>{venue.location}</dd>
          </div>
          <div className="detail-row">
            <dt>Capacity</dt>
            <dd>{venue.capacity} people</dd>
          </div>
          <div className="detail-row">
            <dt>Operating hours</dt>
            <dd>
              <OperatingHours value={venue.operating_hours} />
            </dd>
          </div>
        </dl>
      </section>

      <section className="card">
        <h2>Suitability</h2>
        <dl className="detail-list">
          <div className="detail-row">
            <dt>Supported room layouts</dt>
            <dd>
              <ChipList items={venue.supported_layouts} label="Supported room layouts" />
            </dd>
          </div>
          <div className="detail-row">
            <dt>Facilities</dt>
            <dd>
              <ChipList items={venue.facilities} label="Facilities" />
            </dd>
          </div>
          <div className="detail-row">
            <dt>Accessibility features</dt>
            <dd>
              <ChipList items={venue.accessibility_features} label="Accessibility features" />
            </dd>
          </div>
        </dl>
      </section>

      {user?.role === Role.COORDINATOR && (
        <VenueSuitability venueId={venue.id} />
      )}

      {user?.role === Role.VENUE_STAFF && (
        <section className="card stack" aria-label="Mark venue unavailable">
          <h2>Mark venue unavailable</h2>
          <p>Existing bookings are preserved and affected coordinators are notified.</p>
          <form className="stack" onSubmit={(event) => void markUnavailable(event)}>
            <label className="field">
              <span>From</span>
              <input
                type="datetime-local"
                required
                value={unavailableFrom}
                onChange={(event) => setUnavailableFrom(event.target.value)}
              />
            </label>
            <label className="field">
              <span>Until</span>
              <input
                type="datetime-local"
                required
                value={unavailableUntil}
                onChange={(event) => setUnavailableUntil(event.target.value)}
              />
            </label>
            <label className="field">
              <span>Reason</span>
              <input
                required
                maxLength={2000}
                value={unavailableReason}
                onChange={(event) => setUnavailableReason(event.target.value)}
              />
            </label>
            <button type="submit" className="btn-primary" disabled={savingUnavailability}>
              {savingUnavailability ? 'Recording…' : 'Record unavailability'}
            </button>
          </form>
          {unavailabilityError && <p className="form-error" role="alert">{unavailabilityError}</p>}
          {unavailabilityNotice && <p className="notice" role="status">{unavailabilityNotice}</p>}
        </section>
      )}

      <p>
        <Link to={`/venues/${venue.id}/availability`}>View availability calendar →</Link>
      </p>
      {back}
    </div>
  )
}
