import { useEffect, useId, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router'
import { ApiError } from '../../lib/api'
import { EVENT_STATUS_LABELS, fromDateTimeLocal, getAssignedEvent, toDateTimeLocal } from '../../lib/events'
import { REPLACEMENT_EVENT_STATUSES, requestReplacementVenue } from '../../lib/venueBookings'
import { AddVenueLink } from './AddVenueLink'
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
  // "Find replacement" (SCRUM-95) opens this page with the affected booking's
  // date, time and requirements already filled in, and the booking it replaces.
  const [params] = useSearchParams()
  const replacesId = Number(params.get('replaces')) || null
  const [replaceState, setReplaceState] = useState<{ busy: number | null; done: string | null; error: string | null }>({
    busy: null,
    done: null,
    error: null,
  })
  const replacementEventId = replacesId === null ? null : Number(params.get('event')) || null
  const [replacementRefusal, setReplacementRefusal] = useState<string | null>(null)
  useEffect(() => {
    if (replacementEventId === null) return
    let cancelled = false
    getAssignedEvent(replacementEventId)
      .then((event) => {
        if (!cancelled && !REPLACEMENT_EVENT_STATUSES.includes(event.status)) {
          setReplacementRefusal(
            `This event is ${EVENT_STATUS_LABELS[event.status]}, so a replacement venue cannot be requested.`,
          )
        }
      })
      .catch((err: unknown) => {
        // Not refused by this: the request itself is checked by the server.
        console.error('Failed to check the event for a replacement search.', { error: err })
      })
    return () => {
      cancelled = true
    }
  }, [replacementEventId])
  const list = (name: string) => (params.get(name) ?? '').split(',').filter(Boolean)
  // The prefilled window arrives as ISO instants; the form wants a local day and hours.
  const [fromDate, fromTime = ''] = toDateTimeLocal(params.get('from')).split('T')
  const [, untilTime = ''] = toDateTimeLocal(params.get('until')).split('T')

  // --- what the user has entered -----------------------------------------
  const [keyword, setKeyword] = useState('')
  const [attendance, setAttendance] = useState(params.get('attendance') ?? '')
  const [layout, setLayout] = useState(params.get('layout') ?? '')
  const [facilities, setFacilities] = useState<string[]>(() => list('facilities'))
  const [accessibility, setAccessibility] = useState<string[]>(() => list('accessibility'))
  // The day and the hours an event needs, in the Coordinator's local time.
  const [date, setDate] = useState(fromDate ?? '')
  const [startTime, setStartTime] = useState(fromTime)
  const [endTime, setEndTime] = useState(untilTime)

  // --- which filter panel is open (one at a time) -------------------------
  const [open, setOpen] = useState<FilterKey | null>(null)

  // --- the choices the filters offer ------------------------------------
  const [options, setOptions] = useState<VenueFilterOptions>(NO_OPTIONS)
  const [optionsFailed, setOptionsFailed] = useState(false)

  // --- results -----------------------------------------------------------
  const [venues, setVenues] = useState<VenueSummary[]>([])
  const [error, setError] = useState<string | null>(null)

  // The time window only counts once it is complete and the right way
  // round. An unfinished one is left out of the search and the missing
  // fields are flagged. One that ends before it starts BLOCKS the search
  // (Filter Venues by Date and Time, AC3): showing results for it would
  // present venues as free for a time nobody asked about.
  const startIso = date && startTime ? fromDateTimeLocal(`${date}T${startTime}`) : null
  const endIso = date && endTime ? fromDateTimeLocal(`${date}T${endTime}`) : null
  let windowError: string | null = null
  let windowState: 'none' | 'incomplete' | 'invalid' | 'valid' = 'none'
  // Which of the three fields to mark invalid.
  const flagged = { date: false, start: false, end: false }
  if (date || startTime || endTime) {
    if (!startIso || !endIso) {
      windowError = 'Enter a date, a start time and an end time.'
      windowState = 'incomplete'
      flagged.date = !date
      flagged.start = !startTime
      flagged.end = !endTime
    } else if (new Date(endIso) <= new Date(startIso)) {
      windowError = 'The end time must be after the start time.'
      windowState = 'invalid'
      flagged.start = true
      flagged.end = true
    } else {
      windowState = 'valid'
    }
  }
  const blocked = windowState === 'invalid'

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
    // Nothing is sent while the window is back to front -- see `blocked`.
    if (blocked) return
    const timer = setTimeout(() => setSentKey(key), SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [key, blocked])

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
    setDate('')
    setStartTime('')
    setEndTime('')
    setOpen(null)
    // Straight back to every venue, without waiting out the debounce.
    setSentKey('{}')
  }

  async function requestReplacement(venue: VenueSummary) {
    if (replacesId === null) return
    setReplaceState({ busy: venue.id, done: null, error: null })
    try {
      await requestReplacementVenue(replacesId, {
        venue_id: venue.id,
        expected_attendance: search.minCapacity ?? null,
      })
      setReplaceState({
        busy: null,
        done: `Replacement requested at ${venue.name}. Venue Staff will see it replaces the booking at ${params.get('replacesVenue') ?? 'the affected venue'}.`,
        error: null,
      })
    } catch (err) {
      setReplaceState({
        busy: null,
        done: null,
        error: err instanceof ApiError ? err.message : 'Could not request the replacement.',
      })
    }
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
        <AddVenueLink />
      </header>

      {replacesId !== null && (
        <section className="card" aria-label="Replacement venue request">
          {replacementRefusal ? (
            <p className="form-error" role="alert">
              {replacementRefusal}
            </p>
          ) : (
            <p>
              Finding a replacement for your booking at{' '}
              <strong>{params.get('replacesVenue') ?? 'the affected venue'}</strong>. Its date, time and
              requirements are filled in below.
            </p>
          )}
          {replaceState.done && (
            <p role="status" className="field-hint">
              {replaceState.done}{' '}
              {params.get('event') && <Link to={`/coordinator/events/${params.get('event')}`}>Back to the event</Link>}
            </p>
          )}
          {replaceState.error && (
            <p className="form-error" role="alert">
              {replaceState.error}
            </p>
          )}
        </section>
      )}

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
              setDate('')
              setStartTime('')
              setEndTime('')
            }}
            {...panelProps('dates')}
          >
            <div className={flagged.date ? 'field field-invalid' : 'field'}>
              <label htmlFor="venue-date">Date</label>
              <input
                id="venue-date"
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                aria-invalid={flagged.date}
                aria-describedby="venue-window-message"
              />
            </div>
            <div className="form-row form-row-tight">
              <div className={flagged.start ? 'field field-invalid' : 'field'}>
                <label htmlFor="venue-start-time">Start time</label>
                <input
                  id="venue-start-time"
                  type="time"
                  value={startTime}
                  onChange={(e) => setStartTime(e.target.value)}
                  aria-invalid={flagged.start}
                  aria-describedby="venue-window-message"
                />
              </div>
              <div className={flagged.end ? 'field field-invalid' : 'field'}>
                <label htmlFor="venue-end-time">End time</label>
                <input
                  id="venue-end-time"
                  type="time"
                  value={endTime}
                  onChange={(e) => setEndTime(e.target.value)}
                  aria-invalid={flagged.end}
                  aria-describedby="venue-window-message"
                />
              </div>
            </div>
            {windowError ? (
              <p id="venue-window-message" className="field-error" aria-live="polite">
                {windowError}
              </p>
            ) : (
              <p id="venue-window-message" className="field-hint">
                Leaves out venues booked, tentatively held or closed then, counting each
                venue's setup and turnaround time, and venues outside their operating hours.
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

      {blocked ? (
        <div className="card notice-empty">
          <p>Search paused.</p>
          <p className="page-subtitle">
            The end time is earlier than the start time. Fix the date and time to see venues.
          </p>
        </div>
      ) : loading ? null : venues.length === 0 ? (
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
                  {replacesId !== null && replacementRefusal === null && venue.is_active && (
                    <button
                      type="button"
                      className="btn-secondary"
                      disabled={replaceState.busy !== null || replaceState.done !== null}
                      aria-label={`Request as replacement: ${venue.name}`}
                      onClick={() => void requestReplacement(venue)}
                    >
                      Request as replacement
                    </button>
                  )}
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
