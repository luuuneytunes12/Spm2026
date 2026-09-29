import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { ApiError } from '../../lib/api'
import { fromDateTimeLocal } from '../../lib/events'
import { listVenueFilterOptions, listVenues } from '../../lib/venues'
import type { VenueFilterOptions, VenueSearch, VenueSummary } from '../../lib/venues'

/** How long to wait after the last change before searching. Long enough that
 *  typing a word is one request rather than one per keystroke, short enough
 *  that the list still feels like it follows what is typed. Same as the
 *  equipment catalogue. */
const SEARCH_DEBOUNCE_MS = 250

const NO_OPTIONS: VenueFilterOptions = { layouts: [], facilities: [], accessibility_features: [] }

/** Every venue, searchable and filterable by an event's requirements, for
 *  Event Coordinators and Venue Staff to pick one and open its details.
 *
 *  Read-only: creating and editing venues is its own story. With nothing
 *  entered, this is the same list the page showed before search existed. */
export function Venues() {
  // --- what the user has entered -----------------------------------------
  const [keyword, setKeyword] = useState('')
  const [attendance, setAttendance] = useState('')
  const [layout, setLayout] = useState('')
  const [facilities, setFacilities] = useState<string[]>([])
  const [accessibility, setAccessibility] = useState<string[]>([])
  const [from, setFrom] = useState('')
  const [until, setUntil] = useState('')

  // --- the choices the filters offer ------------------------------------
  const [options, setOptions] = useState<VenueFilterOptions>(NO_OPTIONS)
  const [optionsFailed, setOptionsFailed] = useState(false)

  // --- results -----------------------------------------------------------
  const [venues, setVenues] = useState<VenueSummary[]>([])
  const [error, setError] = useState<string | null>(null)

  // The time window only counts once it is complete and the right way
  // round. Half a window is not a search -- the API would reject it -- so
  // until then it is left out and the user is told what is missing.
  const startIso = fromDateTimeLocal(from)
  const endIso = fromDateTimeLocal(until)
  let windowError: string | null = null
  if (from || until) {
    if (!startIso || !endIso) windowError = 'Enter both a start and an end.'
    else if (new Date(endIso) <= new Date(startIso)) windowError = 'The end must be after the start.'
  }

  // The search, with every empty criterion left out, so a cleared filter
  // means "no filter" rather than "match nothing".
  const search: VenueSearch = {}
  if (keyword.trim()) search.q = keyword.trim()
  const people = Number(attendance)
  // Anything but a whole number of at least one is not a filter yet -- the
  // API would reject it, and while typing it is usually a half-typed value.
  if (attendance.trim() && Number.isInteger(people) && people >= 1) search.minCapacity = people
  if (layout) search.layout = layout
  if (facilities.length > 0) search.facilities = facilities
  if (accessibility.length > 0) search.accessibility = accessibility
  if ((from || until) && !windowError && startIso && endIso) {
    search.start = startIso
    search.end = endIso
  }

  // A string key so the effects below compare searches by value.
  const key = JSON.stringify(search)
  const searching = key !== '{}'

  // The key that has actually been sent. Starts equal to the current key so
  // the first load is immediate; after that it follows a pause in typing.
  const [sentKey, setSentKey] = useState(key)
  // Which search the current `venues` belong to. Deriving loading from this
  // keeps the fetch effect free of synchronous setState, and means a new
  // search cannot briefly show the previous one's results as if they
  // matched it.
  const [loadedKey, setLoadedKey] = useState<string | null>(null)
  const loading = loadedKey !== sentKey

  useEffect(() => {
    const timer = setTimeout(() => setSentKey(key), SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [key])

  useEffect(() => {
    let cancelled = false
    listVenues(JSON.parse(sentKey) as VenueSearch)
      .then((rows) => {
        if (cancelled) return
        setVenues(rows)
        setError(null)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setVenues([])
        setError(err instanceof ApiError ? err.message : 'Could not load venues.')
      })
      .finally(() => {
        if (!cancelled) setLoadedKey(sentKey)
      })
    return () => {
      cancelled = true
    }
  }, [sentKey])

  useEffect(() => {
    let cancelled = false
    listVenueFilterOptions()
      .then((loaded) => {
        if (!cancelled) setOptions(loaded)
      })
      .catch(() => {
        // Keyword, attendance and dates still work without these, so this
        // degrades the filters rather than the whole page.
        if (!cancelled) setOptionsFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [])

  function toggle(list: string[], value: string, set: (next: string[]) => void) {
    set(list.includes(value) ? list.filter((v) => v !== value) : [...list, value])
  }

  function clearFilters() {
    setKeyword('')
    setAttendance('')
    setLayout('')
    setFacilities([])
    setAccessibility([])
    setFrom('')
    setUntil('')
    // Straight back to every venue, without waiting out the debounce.
    setSentKey('{}')
  }

  return (
    <div className="stack">
      <header className="page-header">
        <h1>Venues</h1>
        <p className="page-subtitle">
          Search by name or location and filter by what your event needs, then open a venue
          to check it against the event's requirements.
        </p>
      </header>

      {/* Outside the loading swap below: the filters are how you get out of
          an unhelpful result, so they never disappear while a search runs. */}
      <section className="card stack-tight" aria-label="Search and filter venues">
        <div className="form-row">
          <div className="field">
            <label htmlFor="venue-search">Search venues</label>
            <input
              id="venue-search"
              type="text"
              placeholder="Name or location"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="venue-attendance">Expected attendance</label>
            <input
              id="venue-attendance"
              type="number"
              min={1}
              inputMode="numeric"
              placeholder="e.g. 120"
              value={attendance}
              onChange={(e) => setAttendance(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="venue-layout">Layout</label>
            <select id="venue-layout" value={layout} onChange={(e) => setLayout(e.target.value)}>
              <option value="">Any layout</option>
              {options.layouts.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="form-row">
          <div className="field">
            <label htmlFor="venue-from">Available from</label>
            <input
              id="venue-from"
              type="datetime-local"
              value={from}
              onChange={(e) => setFrom(e.target.value)}
              aria-invalid={windowError !== null}
            />
          </div>
          <div className="field">
            <label htmlFor="venue-until">Available until</label>
            <input
              id="venue-until"
              type="datetime-local"
              value={until}
              onChange={(e) => setUntil(e.target.value)}
              aria-invalid={windowError !== null}
            />
          </div>
        </div>
        {windowError ? (
          <p className="field-error" aria-live="polite">
            {windowError}
          </p>
        ) : (
          <p className="field-hint">
            Leaves out venues already booked or closed during this time.
          </p>
        )}

        <div className="form-row">
          <fieldset className="field-group">
            <legend>Facilities</legend>
            <CheckboxGroup
              values={options.facilities}
              selected={facilities}
              onToggle={(value) => toggle(facilities, value, setFacilities)}
              failed={optionsFailed}
            />
          </fieldset>
          <fieldset className="field-group">
            <legend>Accessibility</legend>
            <CheckboxGroup
              values={options.accessibility_features}
              selected={accessibility}
              onToggle={(value) => toggle(accessibility, value, setAccessibility)}
              failed={optionsFailed}
            />
          </fieldset>
        </div>
      </section>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      {loading ? null : venues.length === 0 ? (
        <div className="card notice-empty">
          {searching ? (
            <>
              <p>No venues match your search.</p>
              <p className="page-subtitle">
                <button type="button" className="btn-link-muted" onClick={clearFilters}>
                  Clear filters
                </button>{' '}
                to see every venue.
              </p>
            </>
          ) : (
            <p className="page-subtitle">No venues have been recorded yet.</p>
          )}
        </div>
      ) : (
        <ul className="request-list">
          {venues.map((venue) => (
            <li key={venue.id} className="card request">
              <div className="request-main">
                <span className="request-title">{venue.name}</span>
                <span className="request-meta">
                  {venue.location} · Capacity {venue.capacity}
                </span>
                {venue.facilities.length > 0 && (
                  <ul className="chip-list" aria-label={`Facilities at ${venue.name}`}>
                    {venue.facilities.map((facility) => (
                      <li key={facility} className="chip">
                        {facility}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="request-side">
                {!venue.is_active && <span className="badge badge-muted">Inactive</span>}
                <Link to={`/venues/${venue.id}`} aria-label={`View details of ${venue.name}`}>
                  View details →
                </Link>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

interface CheckboxGroupProps {
  values: string[]
  selected: string[]
  onToggle: (value: string) => void
  failed: boolean
}

/** One checkbox per recorded value. Ticking several means the venue must
 *  have every one of them. */
function CheckboxGroup({ values, selected, onToggle, failed }: CheckboxGroupProps) {
  if (failed) return <p className="field-hint">Could not load these choices.</p>
  if (values.length === 0) return <p className="field-hint">None recorded yet.</p>
  return (
    <div className="checkbox-grid">
      {values.map((value) => (
        <label key={value} className="checkbox-row">
          <input
            type="checkbox"
            checked={selected.includes(value)}
            onChange={() => onToggle(value)}
          />
          {value}
        </label>
      ))}
    </div>
  )
}
