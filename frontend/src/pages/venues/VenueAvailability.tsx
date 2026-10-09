import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { ApiError } from '../../lib/api'
import { fromDateTimeLocal } from '../../lib/events'
import { getVenue, getVenueAvailability } from '../../lib/venues'
import type {
  VenueAvailability as VenueAvailabilityData,
  VenueAvailabilityItem,
  VenueDetail,
} from '../../lib/venues'

const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

function localDateTimeValue(value: Date): string {
  const local = new Date(value.getTime() - value.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 16)
}

function localDateKey(value: Date): string {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function initialRange(): [string, string] {
  const start = new Date()
  start.setDate(1)
  start.setHours(0, 0, 0, 0)
  const end = new Date(start.getFullYear(), start.getMonth() + 1, 0, 23, 59, 0, 0)
  return [localDateTimeValue(start), localDateTimeValue(end)]
}

function monthValue(value: Date): string {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}`
}

function monthDateRange(value: Date): [string, string] {
  const firstDay = new Date(value.getFullYear(), value.getMonth(), 1)
  const lastDay = new Date(value.getFullYear(), value.getMonth() + 1, 0, 23, 59)
  return [localDateTimeValue(firstDay), localDateTimeValue(lastDay)]
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

function itemStatus(item: VenueAvailabilityItem): string {
  if (item.kind === 'unavailability' || item.conflicts_with_unavailability) return 'Unavailable'
  if (item.kind === 'tentative_hold') return 'Tentative hold'
  return 'Confirmed booking'
}

function itemMarkerKind(item: VenueAvailabilityItem): VenueAvailabilityItem['kind'] {
  return item.conflicts_with_unavailability ? 'unavailability' : item.kind
}

function availabilityErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return 'Your session has expired. Sign in again to view availability.'
    if (error.status === 403) return 'Your account does not have permission to view venue availability.'
    if (error.status === 404) return 'This venue could not be found. Return to venues and select another venue.'
    if (error.status === 422) return `The selected date range is invalid: ${error.message}`
    if (error.status === 503 && error.message.includes('backend/sql/019_multi_venue_tentative_holds.sql')) {
      return error.message
    }
    if (error.status >= 500) {
      return 'Availability is temporarily unavailable. Please try again. If the problem continues, contact support.'
    }
    return `Could not retrieve availability (HTTP ${error.status}): ${error.message}`
  }
  if (error instanceof TypeError) {
    return 'Could not reach the backend to retrieve availability. Check that the backend is running and try again.'
  }
  return 'An unexpected error prevented availability from loading. Please try again; if it continues, contact support.'
}

function monthsInRange(start: Date, end: Date): Date[] {
  const months: Date[] = []
  const cursor = new Date(start.getFullYear(), start.getMonth(), 1)
  const lastMonth = new Date(end.getFullYear(), end.getMonth(), 1)
  while (cursor <= lastMonth) {
    months.push(new Date(cursor))
    cursor.setMonth(cursor.getMonth() + 1)
  }
  return months
}

export function VenueAvailability() {
  const { id } = useParams()
  const venueId = Number(id)
  const [venue, setVenue] = useState<VenueDetail | null>(null)
  const [initialStart, initialEnd] = initialRange()
  const [[from, until], setRange] = useState<[string, string]>([initialStart, initialEnd])
  const [viewMonth, setViewMonth] = useState(() => new Date())
  const [selectedDate, setSelectedDate] = useState(() => localDateKey(new Date()))
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
          console.error('Failed to load venue details.', { venueId, error: err })
          setError(
            err instanceof ApiError && err.status === 404
              ? 'This venue could not be found. Return to venues and select another venue.'
              : err instanceof ApiError && err.status === 403
                ? 'Your account does not have permission to view this venue.'
                : err instanceof ApiError && err.status === 401
                  ? 'Your session has expired. Sign in again to view this venue.'
                  : err instanceof TypeError
                    ? 'Could not reach the backend to load this venue. Check that the backend is running and try again.'
                    : 'Could not load this venue. Please try again; check the browser console for diagnostic details.',
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

  async function requestAvailability(startValue: string, endValue: string) {
    const start = fromDateTimeLocal(startValue)
    const end = fromDateTimeLocal(endValue)
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
      const result = await getVenueAvailability(venueId, start, end)
      setAvailability(result)
      setSelectedDate(localDateKey(new Date(start)))
      setViewMonth(new Date(new Date(start).getFullYear(), new Date(start).getMonth(), 1))
    } catch (err: unknown) {
      setAvailability(null)
      console.error('Failed to retrieve venue availability.', {
        venueId,
        start,
        end,
        error: err,
      })
      setError(availabilityErrorMessage(err))
    } finally {
      setLoadingCalendar(false)
    }
  }

  function loadCalendar() {
    void requestAvailability(from, until)
  }

  function changeMonth(value: string) {
    if (!value) return
    const [year, month] = value.split('-').map(Number)
    const nextMonth = new Date(year, month - 1, 1)
    const [nextFrom, nextUntil] = monthDateRange(nextMonth)
    setViewMonth(nextMonth)
    setRange([nextFrom, nextUntil])
    setSelectedDate(localDateKey(nextMonth))
    void requestAvailability(nextFrom, nextUntil)
  }

  function shiftMonth(offset: number) {
    const nextMonth = new Date(viewMonth.getFullYear(), viewMonth.getMonth() + offset, 1)
    changeMonth(monthValue(nextMonth))
  }

  const itemsByDate = new Map<string, VenueAvailabilityItem[]>()
  for (const item of availability?.items ?? []) {
    const start = new Date(item.start_time)
    const lastOccupiedInstant = new Date(new Date(item.end_time).getTime() - 1)
    const day = new Date(start.getFullYear(), start.getMonth(), start.getDate())
    const lastDay = new Date(
      lastOccupiedInstant.getFullYear(),
      lastOccupiedInstant.getMonth(),
      lastOccupiedInstant.getDate(),
    )
    while (day <= lastDay) {
      const key = localDateKey(day)
      itemsByDate.set(key, [...(itemsByDate.get(key) ?? []), item])
      day.setDate(day.getDate() + 1)
    }
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

  const calendarMonths = availability
    ? monthsInRange(new Date(availability.start), new Date(availability.end))
    : []
  const selectedItems = itemsByDate.get(selectedDate) ?? []

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
        <button
          type="button"
          className="btn-primary"
          onClick={loadCalendar}
          disabled={loadingCalendar}
        >
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
          <div className="availability-month-controls">
            <button
              type="button"
              className="btn-secondary"
              onClick={() => shiftMonth(-1)}
              aria-label="Previous month"
            >
              ‹
            </button>
            <div className="field">
              <label htmlFor="availability-month">View month</label>
              <input
                id="availability-month"
                type="month"
                value={monthValue(viewMonth)}
                onChange={(event) => changeMonth(event.target.value)}
              />
            </div>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => shiftMonth(1)}
              aria-label="Next month"
            >
              ›
            </button>
          </div>

          {calendarMonths.map((month) => {
            const firstDay = new Date(month.getFullYear(), month.getMonth(), 1)
            const daysInMonth = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate()
            const rangeStart = localDateKey(new Date(availability.start))
            const rangeEnd = localDateKey(new Date(availability.end))
            const monthLabel = month.toLocaleDateString(undefined, {
              month: 'long',
              year: 'numeric',
            })
            return (
              <section className="card availability-month" key={monthValue(month)}>
                <h2>{monthLabel}</h2>
                <div className="availability-calendar-grid" role="grid" aria-label={monthLabel}>
                  {WEEKDAYS.map((weekday) => (
                    <div className="availability-weekday" role="columnheader" key={weekday}>
                      {weekday}
                    </div>
                  ))}
                  {Array.from({ length: firstDay.getDay() }, (_, index) => (
                    <div
                      className="availability-day availability-day-empty"
                      role="gridcell"
                      aria-hidden="true"
                      key={`empty-${index}`}
                    />
                  ))}
                  {Array.from({ length: daysInMonth }, (_, index) => {
                    const day = index + 1
                    const date = new Date(month.getFullYear(), month.getMonth(), day)
                    const key = localDateKey(date)
                    const dayItems = itemsByDate.get(key) ?? []
                    const inRange = key >= rangeStart && key <= rangeEnd
                    const dateName = date.toLocaleDateString(undefined, {
                      weekday: 'long',
                      month: 'long',
                      day: 'numeric',
                      year: 'numeric',
                    })
                    return (
                      <div
                        className={`availability-day${selectedDate === key ? ' availability-day-selected' : ''}`}
                        role="gridcell"
                        key={key}
                      >
                        <button
                          type="button"
                          className="availability-day-button"
                          aria-label={`${dateName}${dayItems.length ? `, ${dayItems.length} availability ${dayItems.length === 1 ? 'entry' : 'entries'}` : ''}`}
                          aria-pressed={selectedDate === key}
                          disabled={!inRange}
                          onClick={() => setSelectedDate(key)}
                        >
                          <span>{day}</span>
                          {dayItems.length > 0 && (
                            <span className="availability-day-markers" aria-hidden="true">
                              {dayItems.map((item) => (
                                <span
                                  className={`availability-marker availability-marker-${itemMarkerKind(item)}`}
                                  key={`${item.kind}-${item.id}`}
                                />
                              ))}
                            </span>
                          )}
                        </button>
                      </div>
                    )
                  })}
                </div>
              </section>
            )
          })}

          <div className="availability-legend" aria-label="Calendar legend">
            <span><i className="availability-marker availability-marker-confirmed_booking" /> Confirmed</span>
            <span><i className="availability-marker availability-marker-tentative_hold" /> Tentative hold</span>
            <span><i className="availability-marker availability-marker-unavailability" /> Unavailable</span>
          </div>

          <section className="card stack" aria-label={`Availability on ${selectedDate}`}>
            <h2>{dateLabel(`${selectedDate}T12:00:00`)}</h2>
            {selectedItems.length === 0 ? (
              <p className="notice-empty">
                No confirmed bookings, active holds, or closures on this date.
              </p>
            ) : (
              <ul className="availability-day-list">
                {selectedItems.map((item) => (
                  <li className="availability-entry" key={`${item.kind}-${item.id}`}>
                    <div className="availability-entry-main">
                      <strong>{item.event_name || 'Unavailable'}</strong>
                      <span>{timeLabel(item.start_time)} – {timeLabel(item.end_time)}</span>
                    </div>
                    <span
                      className={`badge ${
                        item.kind === 'tentative_hold' ? 'badge-accent' : 'badge-muted'
                      }`}
                    >
                      {itemStatus(item)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </section>
      )}

      <p>
        <Link to={`/venues/${venue.id}`}>Back to {venue.name}</Link>
      </p>
    </div>
  )
}
