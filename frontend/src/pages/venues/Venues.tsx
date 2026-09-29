import { useEffect, useId, useRef, useState } from 'react'
import type { ReactNode } from 'react'
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

type FilterKey = 'attendance' | 'layout' | 'dates' | 'facilities' | 'accessibility'

/** "8 Oct, 16:00 – 20:00", or "8 Oct, 16:00 – 9 Oct, 10:00" across days.
 *  The year is added only when it is not this year. Short enough for a chip,
 *  in the same style as the dates elsewhere in the app. */
function formatWindow(startIso: string, endIso: string): string {
  const start = new Date(startIso)
  const end = new Date(endIso)
  const thisYear = new Date().getFullYear()
  const day = (d: Date) =>
    d.toLocaleDateString(undefined, {
      day: 'numeric',
      month: 'short',
      ...(d.getFullYear() !== thisYear ? { year: 'numeric' } : {}),
    })
  const time = (d: Date) => d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
  return day(start) === day(end)
    ? `${day(start)}, ${time(start)} – ${time(end)}`
    : `${day(start)}, ${time(start)} – ${day(end)}, ${time(end)}`
}

/** Every venue, searchable and filterable by an event's requirements, for
 *  Event Coordinators and Venue Staff to pick one and open its details.
 *
 *  The filters sit in a compact bar -- one chip per filter, each opening a
 *  small panel -- so the venues rather than the options fill the page. An
 *  applied filter shows its value on its chip, so what is filtered stays
 *  visible after its panel closes.
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

  // --- which filter panel is open (one at a time) -------------------------
  const [open, setOpen] = useState<FilterKey | null>(null)

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
  let windowState: 'none' | 'incomplete' | 'invalid' | 'valid' = 'none'
  if (from || until) {
    if (!startIso || !endIso) {
      windowError = 'Enter both a start and an end.'
      windowState = 'incomplete'
    } else if (new Date(endIso) <= new Date(startIso)) {
      windowError = 'The end must be after the start.'
      windowState = 'invalid'
    } else {
      windowState = 'valid'
    }
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
  if (windowState === 'valid' && startIso && endIso) {
    search.start = startIso
    search.end = endIso
  }

  // A string key so the effects below compare searches by value.
  const key = JSON.stringify(search)
  const searching = key !== '{}'
  // "Clear all" is offered whenever there is anything to clear -- including
  // an unfinished date window, which is not part of the search yet.
  const anythingSet = searching || windowState !== 'none'

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
        // degrades two filters rather than the whole page.
        if (!cancelled) setOptionsFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [])

  function toggle(list: string[], value: string, set: (next: string[]) => void) {
    set(list.includes(value) ? list.filter((v) => v !== value) : [...list, value])
  }

  function clearAll() {
    setKeyword('')
    setAttendance('')
    setLayout('')
    setFacilities([])
    setAccessibility([])
    setFrom('')
    setUntil('')
    setOpen(null)
    // Straight back to every venue, without waiting out the debounce.
    setSentKey('{}')
  }

  function panelProps(which: FilterKey) {
    return {
      open: open === which,
      onToggle: () => setOpen((current) => (current === which ? null : which)),
      onClose: () => setOpen((current) => (current === which ? null : current)),
    }
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
      <section className="card venue-filters" aria-label="Search and filter venues">
        <div className="search-field">
          <svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16" fill="none">
            <circle cx="7" cy="7" r="5" stroke="currentColor" strokeWidth="1.6" />
            <path d="M11 11l3.5 3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
          <label htmlFor="venue-search" className="visually-hidden">
            Search venues
          </label>
          <input
            id="venue-search"
            type="text"
            placeholder="Search by name or location"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
          />
        </div>

        <div className="filter-bar">
          <FilterChip
            label="Attendance"
            summary={search.minCapacity !== undefined ? `Attendance: ${search.minCapacity}+` : null}
            panelLabel="Filter by attendance"
            onClear={() => setAttendance('')}
            {...panelProps('attendance')}
          >
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
              <p className="field-hint">Leaves out venues that hold fewer people.</p>
            </div>
          </FilterChip>

          <FilterChip
            label="Layout"
            summary={layout ? `Layout: ${layout}` : null}
            panelLabel="Filter by layout"
            onClear={() => setLayout('')}
            {...panelProps('layout')}
          >
            <div className="filter-options" role="radiogroup" aria-label="Layout">
              {/* One choice -- an event uses one layout -- with "Any layout"
                  as the way back. */}
              {['', ...options.layouts].map((value) => (
                <label key={value || 'any'} className="checkbox-row">
                  <input
                    type="radio"
                    name="venue-layout"
                    value={value}
                    checked={layout === value}
                    onChange={() => setLayout(value)}
                  />
                  {value || 'Any layout'}
                </label>
              ))}
            </div>
          </FilterChip>

          <FilterChip
            label="Date & time"
            summary={
              windowState === 'valid' && startIso && endIso
                ? formatWindow(startIso, endIso)
                : windowState === 'incomplete'
                  ? 'Date & time: incomplete'
                  : windowState === 'invalid'
                    ? 'Date & time: invalid'
                    : null
            }
            warning={windowState === 'incomplete' || windowState === 'invalid'}
            panelLabel="Filter by date & time"
            onClear={() => {
              setFrom('')
              setUntil('')
            }}
            {...panelProps('dates')}
          >
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
            {windowError ? (
              <p className="field-error" aria-live="polite">
                {windowError}
              </p>
            ) : (
              <p className="field-hint">
                Leaves out venues already booked or closed during this time.
              </p>
            )}
          </FilterChip>

          <FilterChip
            label="Facilities"
            summary={facilities.length > 0 ? `Facilities · ${facilities.length}` : null}
            panelLabel="Filter by facilities"
            onClear={() => setFacilities([])}
            {...panelProps('facilities')}
          >
            <fieldset className="field-group">
              <legend className="visually-hidden">Facilities</legend>
              <CheckboxList
                values={options.facilities}
                selected={facilities}
                onToggle={(value) => toggle(facilities, value, setFacilities)}
                failed={optionsFailed}
              />
            </fieldset>
          </FilterChip>

          <FilterChip
            label="Accessibility"
            summary={accessibility.length > 0 ? `Accessibility · ${accessibility.length}` : null}
            panelLabel="Filter by accessibility"
            onClear={() => setAccessibility([])}
            {...panelProps('accessibility')}
          >
            <fieldset className="field-group">
              <legend className="visually-hidden">Accessibility</legend>
              <CheckboxList
                values={options.accessibility_features}
                selected={accessibility}
                onToggle={(value) => toggle(accessibility, value, setAccessibility)}
                failed={optionsFailed}
              />
            </fieldset>
          </FilterChip>

          {anythingSet && (
            <button type="button" className="btn-link-muted filter-clear" onClick={clearAll}>
              Clear all
            </button>
          )}
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
                <button type="button" className="btn-link-muted" onClick={clearAll}>
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
        <>
          <p className="page-subtitle venue-count" aria-live="polite">
            {venues.length} {venues.length === 1 ? 'venue' : 'venues'}
          </p>
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
        </>
      )}
    </div>
  )
}

interface FilterChipProps {
  /** The filter's name, shown while it is not applied: "Facilities". */
  label: string
  /** What the chip reads once applied: "Facilities · 2". Null when unset. */
  summary: string | null
  /** An applied-but-unusable state, e.g. half a date window. */
  warning?: boolean
  /** Accessible name of the panel: "Filter by facilities". */
  panelLabel: string
  open: boolean
  onToggle: () => void
  onClose: () => void
  onClear: () => void
  children: ReactNode
}

/** One filter in the bar: a chip that opens a small panel.
 *
 *  Applied, the chip shows its value and gains its own ✕, so a filter can be
 *  seen and removed without reopening it. The panel closes on Escape (focus
 *  returns to the chip) or on a click anywhere else, and takes focus when it
 *  opens so a keyboard user lands on its first control. */
function FilterChip({
  label,
  summary,
  warning = false,
  panelLabel,
  open,
  onToggle,
  onClose,
  onClear,
  children,
}: FilterChipProps) {
  const panelId = useId()
  const wrapper = useRef<HTMLDivElement>(null)
  const button = useRef<HTMLButtonElement>(null)
  const panel = useRef<HTMLDivElement>(null)
  const applied = summary !== null

  // The parent passes a fresh onClose on every render. Kept in a ref so the
  // effect below runs only when the panel opens or closes -- depending on
  // onClose directly would re-run it on every keystroke, and its focus step
  // would pull the cursor back to the first field mid-typing.
  const closeRef = useRef(onClose)
  useEffect(() => {
    closeRef.current = onClose
  })

  useEffect(() => {
    if (!open) return
    // Land on the checked choice if there is one, otherwise the first control.
    const target =
      panel.current?.querySelector<HTMLElement>('input:checked') ??
      panel.current?.querySelector<HTMLElement>('input, select, button')
    target?.focus()

    function onPointerDown(event: MouseEvent) {
      if (!wrapper.current?.contains(event.target as Node)) closeRef.current()
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        closeRef.current()
        button.current?.focus()
      }
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  const chipClass = [
    'filter-chip',
    applied && (warning ? 'filter-chip-warning' : 'filter-chip-active'),
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <div
      ref={wrapper}
      className={applied ? 'filter-chip-wrap filter-chip-wrap-removable' : 'filter-chip-wrap'}
    >
      <button
        ref={button}
        type="button"
        className={chipClass}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        onClick={onToggle}
      >
        {!applied && (
          <svg aria-hidden="true" width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path d="M6 1.5v9M1.5 6h9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        )}
        {summary ?? label}
      </button>
      {applied && (
        <button
          type="button"
          className="filter-chip-remove"
          aria-label={`Remove ${label} filter`}
          onClick={() => {
            onClear()
            onClose()
            button.current?.focus()
          }}
        >
          <svg aria-hidden="true" width="10" height="10" viewBox="0 0 10 10" fill="none">
            <path d="M2 2l6 6M8 2l-6 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </button>
      )}
      {open && (
        <div ref={panel} id={panelId} role="dialog" aria-label={panelLabel} className="filter-panel">
          {children}
        </div>
      )}
    </div>
  )
}

interface CheckboxListProps {
  values: string[]
  selected: string[]
  onToggle: (value: string) => void
  failed: boolean
}

/** One checkbox per recorded value. Ticking several means the venue must
 *  have every one of them, which the hint says in so many words. */
function CheckboxList({ values, selected, onToggle, failed }: CheckboxListProps) {
  if (failed) return <p className="field-hint">Could not load these choices.</p>
  if (values.length === 0) return <p className="field-hint">None recorded yet.</p>
  return (
    <>
      <div className="filter-options">
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
      <p className="field-hint">Venues must have every one you tick.</p>
    </>
  )
}
