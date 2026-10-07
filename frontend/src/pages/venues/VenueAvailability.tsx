import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { useAuth } from '../../auth/useAuth'
import { ApiError } from '../../lib/api'
import { fromDateTimeLocal } from '../../lib/events'
import { Role } from '../../lib/roles'
import { getVenue, getVenueAvailability } from '../../lib/venues'
import type { VenueAvailability as VenueAvailabilityData, VenueDetail } from '../../lib/venues'

function localDateTimeValue(value: Date): string {
  const local = new Date(value.getTime() - value.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 16)
}

function initialRange(): [string, string] {
  const start = new Date()
  start.setHours(0, 0, 0, 0)
  const end = new Date(start)
  end.setDate(end.getDate() + 30)
  end.setHours(23, 59, 0, 0)
  return [localDateTimeValue(start), localDateTimeValue(end)]
}

function dateLabel(value: string): string {
  return new Date(value).toLocaleDateString(undefined, {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
}

function timeLabel(value: string): string {
  return new Date(value).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

function timestampLabel(value: string): string {
  return new Date(value).toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function VenueAvailability() {
  const { id } = useParams()
  const { user } = useAuth()
  const venueId = Number(id)
  const [venue, setVenue] = useState<VenueDetail | null>(null)
  const [[from, until], setRange] = useState(initialRange)
  const [availability, setAvailability] = useState<VenueAvailabilityData | null>(null)
  const [loadingVenue, setLoadingVenue] = useState(true)
  const [loadingCalendar, setLoadingCalendar] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [rangeError, setRangeError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    getVenue(venueId)
      .then((loaded) => {
        if (!cancelled) {
          setVenue(loaded)
          setError(null)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(
            err instanceof ApiError ? err.message : 'Could not load this venue. Please try again.',
          )
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingVenue(false)
      })
    return () => {
      cancelled = true
    }
  }, [venueId])

  async function loadCalendar() {
    const start = fromDateTimeLocal(from)
    const end = fromDateTimeLocal(until)
    if (!start || !end) {
      setRangeError('Enter both a start and an end date and time.')
      return
    }
    if (new Date(end) <= new Date(start)) {
      setRangeError('The end must be after the start.')
      return
    }

    setRangeError(null)
    setError(null)
    setLoadingCalendar(true)
    try {
      setAvailability(await getVenueAvailability(venueId, start, end))
    } catch (err: unknown) {
      setAvailability(null)
      setError(
        err instanceof ApiError
          ? err.message
          : 'Could not load venue availability. You can retry without leaving this page.',
      )
    } finally {
      setLoadingCalendar(false)
    }
  }

  const grouped = new Map<string, NonNullable<typeof availability>['items']>()
  for (const item of availability?.items ?? []) {
    const key = new Date(item.start_time).toLocaleDateString()
    grouped.set(key, [...(grouped.get(key) ?? []), item])
  }

  if (loadingVenue) {
    return <p role="status">Loading venue…</p>
  }

  if (!venue) {
    return (
      <div className="stack">
        <p className="form-error" role="alert">
          {error ?? 'Venue not found.'}
        </p>
        <Link to="/venues">Back to venues</Link>
      </div>
    )
  }

  return (
    <div className="stack">
      <header className="page-header">
        <h1>{venue.name}: availability calendar</h1>
        <p className="page-subtitle">
          Confirmed bookings, active tentative holds, and recorded periods of unavailability
          are shown for the selected date and time range.
        </p>
      </header>

      <section className="card stack" aria-label="Filter calendar date range">
        <div className="field">
          <label htmlFor="availability-from">From</label>
          <input
            id="availability-from"
            type="datetime-local"
            value={from}
            onChange={(event) => setRange([event.target.value, until])}
            aria-invalid={rangeError !== null}
          />
        </div>
        <div className="field">
          <label htmlFor="availability-until">Until</label>
          <input
            id="availability-until"
            type="datetime-local"
            value={until}
            onChange={(event) => setRange([from, event.target.value])}
            aria-invalid={rangeError !== null}
          />
        </div>
        {rangeError && (
          <p className="field-error" role="alert">
            {rangeError}
          </p>
        )}
        <button type="button" className="btn-primary" onClick={loadCalendar} disabled={loadingCalendar}>
          {loadingCalendar ? 'Loading calendar…' : 'Check availability'}
        </button>
      </section>

      {error && (
        <div className="card stack">
          <p className="form-error" role="alert">
            {error}
          </p>
          {!loadingCalendar && (
            <button type="button" className="btn-secondary" onClick={loadCalendar}>
              Retry
            </button>
          )}
        </div>
      )}

      {loadingCalendar && <p role="status">Loading availability…</p>}
      {availability && !loadingCalendar && (
        <section className="stack" aria-label="Venue availability calendar">
          <h2>
            {dateLabel(availability.start)} – {dateLabel(availability.end)}
          </h2>
          {availability.items.length === 0 ? (
            <p className="card notice-empty">
              No confirmed bookings, active holds, or closures in this period.
            </p>
          ) : (
            [...grouped.entries()].map(([day, items]) => (
              <section className="card stack" key={day} aria-label={day}>
                <h3>{day}</h3>
                <ul className="request-list">
                  {items.map((item) => (
                    <li className="card request" key={`${item.kind}-${item.id}`}>
                      <div className="request-main">
                        {item.event_id !== null && user?.role === Role.COORDINATOR ? (
                          <Link className="request-title" to={`/coordinator/events/${item.event_id}`}>
                            {item.event_name || 'Event booking'}
                          </Link>
                        ) : item.event_id !== null ? (
                          <span className="request-title">
                            {item.event_name || 'Event booking'} · Event #{item.event_id}
                          </span>
                        ) : (
                          <span className="request-title">
                            {item.kind === 'unavailability' ? 'Unavailable' : 'Tentative hold'}
                          </span>
                        )}
                        <span className="request-meta">
                          {timeLabel(item.start_time)} – {timeLabel(item.end_time)}
                        </span>
                        {item.kind === 'tentative_hold' && item.expires_at && (
                          <span className="request-meta">
                            Tentative hold expires {timestampLabel(item.expires_at)}
                          </span>
                        )}
                        {item.kind === 'unavailability' && item.reason && (
                          <span className="request-meta">Reason: {item.reason}</span>
                        )}
                        {item.conflicts_with_unavailability && (
                          <span className="form-error" role="status">
                            This booking overlaps a recorded unavailability period.
                          </span>
                        )}
                      </div>
                      <span
                        className={`badge ${
                          item.kind === 'tentative_hold' ? 'badge-accent' : 'badge-muted'
                        }`}
                      >
                        {item.kind === 'confirmed_booking'
                          ? 'Confirmed booking'
                          : item.kind === 'tentative_hold'
                            ? 'Tentative hold'
                            : 'Unavailable'}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            ))
          )}
        </section>
      )}

      <p>
        <Link to={`/venues/${venue.id}`}>Back to {venue.name}</Link>
      </p>
    </div>
  )
}
