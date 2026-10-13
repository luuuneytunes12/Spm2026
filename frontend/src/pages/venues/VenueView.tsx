import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { useAuth } from '../../auth/useAuth'
import { ApiError } from '../../lib/api'
import { Role } from '../../lib/roles'
import {
  UNAVAILABILITY_REASONS,
  availabilityRangeError,
  createUnavailability,
  deleteUnavailability,
  describeAffected,
  describeBusyPeriod,
  describeMinutes,
  describeRecheck,
  endUnavailabilityEarly,
  getVenue,
  getVenueAvailability,
  listUnavailability,
  minutesError,
  saveSetupTurnaround,
  unavailabilityErrors,
  updateUnavailability,
} from '../../lib/venues'
import type { BusyPeriod, Recheck, Unavailability, VenueDetail } from '../../lib/venues'
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

/** One minutes input, labelled, with its problem explained beside it. */
function MinutesField({
  id,
  label,
  value,
  error,
  disabled,
  onChange,
}: {
  id: string
  label: string
  value: string
  error: string | null
  disabled: boolean
  onChange: (value: string) => void
}) {
  const hintId = `${id}-hint`
  const errorId = `${id}-error`
  return (
    <div className={`field${error ? ' field-invalid' : ''}`}>
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="text"
        inputMode="numeric"
        value={value}
        disabled={disabled}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${hintId} ${errorId}` : hintId}
        onChange={(e) => onChange(e.target.value)}
      />
      <p id={hintId} className="field-hint">
        Whole minutes, 0 or more.
      </p>
      {error && (
        <p id={errorId} className="field-error" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}

/** Venue Staff's form for the venue's setup and turnaround minutes. Blocks
 *  an empty, negative or non-whole value before anything is sent, and shows
 *  the server's reasons beside the field it names if it refuses. */
function SetupTurnaroundForm({ venue, onSaved }: { venue: VenueDetail; onSaved: (v: VenueDetail) => void }) {
  const [setup, setSetup] = useState(venue.setup_minutes?.toString() ?? '')
  const [turnaround, setTurnaround] = useState(venue.turnaround_minutes?.toString() ?? '')
  const [errors, setErrors] = useState<{ setup: string | null; turnaround: string | null }>({
    setup: null,
    turnaround: null,
  })
  const [formError, setFormError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [recheck, setRecheck] = useState<Recheck | null>(null)
  const [saving, setSaving] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setSaved(false)
    setRecheck(null)
    setFormError(null)
    const next = {
      setup: minutesError('Setup time', setup),
      turnaround: minutesError('Turnaround time', turnaround),
    }
    setErrors(next)
    if (next.setup || next.turnaround) return
    setSaving(true)
    try {
      const updated = await saveSetupTurnaround(venue.id, {
        setup_minutes: Number(setup),
        turnaround_minutes: Number(turnaround),
      })
      const { recheck: result, ...detail } = updated
      onSaved(detail)
      setRecheck(result ?? null)
      setSaved(true)
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) {
        const text = err.messages.length > 0 ? err.messages.join(' ') : err.message
        const serverErrors = {
          setup: err.fields.some((f) => f.includes('setup_minutes')) ? text : null,
          turnaround: err.fields.some((f) => f.includes('turnaround_minutes')) ? text : null,
        }
        setErrors(serverErrors)
        if (!serverErrors.setup && !serverErrors.turnaround) setFormError(text)
      } else {
        setFormError(err instanceof ApiError ? err.message : 'Could not save the setup and turnaround times.')
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={(e) => void submit(e)} noValidate aria-label="Edit setup and turnaround">
      <MinutesField
        id="setup-minutes"
        label="Setup time (minutes)"
        value={setup}
        error={errors.setup}
        disabled={saving}
        onChange={setSetup}
      />
      <MinutesField
        id="turnaround-minutes"
        label="Turnaround time (minutes)"
        value={turnaround}
        error={errors.turnaround}
        disabled={saving}
        onChange={setTurnaround}
      />
      <button type="submit" className="btn-primary" disabled={saving}>
        {saving ? 'Saving…' : 'Save setup and turnaround'}
      </button>
      {formError && (
        <p className="form-error" role="alert">
          {formError}
        </p>
      )}
      {saved && (
        <p className="notice" role="status">
          Setup and turnaround times saved.
          {recheck && ` ${describeRecheck(recheck)}`}
          {recheck && recheck.flagged > 0 && (
            <>
              {' '}
              <Link to="/venue-staff/flagged">View flagged bookings</Link>
            </>
          )}
        </p>
      )}
    </form>
  )
}

/** ISO instant -> the `YYYY-MM-DDTHH:mm` a datetime-local input takes. */
function toLocalInput(iso: string): string {
  const d = new Date(iso)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`
}

function whenText(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

/** Periods in which the venue is temporarily unavailable (SCRUM-93). Everyone
 *  who can open the venue sees them with their reasons; Venue Staff can also
 *  add, edit, end early or remove one, and see which future bookings fall
 *  inside it. Saving never cancels a booking or its Event. */
function UnavailabilitySection({ venueId, canEdit }: { venueId: number; canEdit: boolean }) {
  const [periods, setPeriods] = useState<Unavailability[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [editing, setEditing] = useState<Unavailability | null>(null)
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [category, setCategory] = useState('')
  const [details, setDetails] = useState('')
  const [errors, setErrors] = useState<{ dates: string | null; category: string | null }>({
    dates: null,
    category: null,
  })
  const [formError, setFormError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [now] = useState(() => Date.now())

  useEffect(() => {
    let cancelled = false
    listUnavailability(venueId)
      .then((rows) => {
        if (!cancelled) setPeriods(rows)
      })
      .catch((err: unknown) => {
        if (!cancelled) setLoadError(err instanceof ApiError ? err.message : 'Could not load unavailable periods.')
      })
    return () => {
      cancelled = true
    }
  }, [venueId])

  function reset() {
    setEditing(null)
    setStart('')
    setEnd('')
    setCategory('')
    setDetails('')
    setErrors({ dates: null, category: null })
  }

  function startEdit(p: Unavailability) {
    setEditing(p)
    setStart(toLocalInput(p.start_time))
    setEnd(toLocalInput(p.end_time))
    setCategory(p.reason_category)
    setDetails(p.reason ?? '')
    setErrors({ dates: null, category: null })
    setFormError(null)
    setNotice(null)
  }

  /** Put the saved row in the list (or drop it) and say what happened. */
  function applied(row: Unavailability | null, id: number, message: string) {
    setPeriods((rows) => {
      const rest = (rows ?? []).filter((r) => r.id !== id)
      const next = row ? [...rest, row] : rest
      return next.sort((a, b) => a.start_time.localeCompare(b.start_time) || a.id - b.id)
    })
    const parts = [message]
    if (row) {
      const affected = describeAffected(row.affected_bookings.length)
      if (affected) parts.push(affected)
      if (row.recheck) parts.push(describeRecheck(row.recheck) ?? '')
    }
    setNotice(parts.filter(Boolean).join(' '))
  }

  async function run(action: () => Promise<void>) {
    setSaving(true)
    setFormError(null)
    setNotice(null)
    try {
      await action()
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Could not save the unavailable period.')
    } finally {
      setSaving(false)
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    const next = unavailabilityErrors(start, end, category)
    setErrors(next)
    setFormError(null)
    setNotice(null)
    if (next.dates || next.category) return
    setSaving(true)
    try {
      const input = {
        start_time: new Date(start).toISOString(),
        end_time: new Date(end).toISOString(),
        reason_category: category as Unavailability['reason_category'],
        reason: details.trim() || null,
      }
      const row = editing
        ? await updateUnavailability(venueId, editing.id, input)
        : await createUnavailability(venueId, input)
      applied(row, row.id, editing ? 'Unavailable period updated.' : 'Unavailable period saved.')
      reset()
    } catch (err) {
      if (err instanceof ApiError && err.status === 422 && err.fields.some((f) => f.includes('_time'))) {
        setErrors({ dates: err.messages.join(' ') || err.message, category: null })
      } else if (err instanceof ApiError && err.status === 422 && err.fields.some((f) => f.includes('reason'))) {
        setErrors({ dates: null, category: err.messages.join(' ') || err.message })
      } else {
        setFormError(err instanceof ApiError ? err.message : 'Could not save the unavailable period.')
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="card" aria-labelledby="unavailability-heading">
      <h2 id="unavailability-heading">Temporarily unavailable</h2>
      {loadError && (
        <p className="form-error" role="alert">
          {loadError}
        </p>
      )}
      {periods !== null &&
        (periods.length === 0 ? (
          <p className="text-muted">No unavailable periods are recorded.</p>
        ) : (
          <ul className="detail-value-list" aria-label="Unavailable periods">
            {periods.map((p) => {
              const underWay = new Date(p.start_time).getTime() <= now && now < new Date(p.end_time).getTime()
              return (
                <li key={p.id}>
                  <strong>{p.reason_category}</strong>
                  {p.reason ? `: ${p.reason}` : ''} - {whenText(p.start_time)} to {whenText(p.end_time)}
                  {canEdit && (
                    <>
                      {' '}
                      <button type="button" className="btn-link" disabled={saving} onClick={() => startEdit(p)}>
                        Edit
                      </button>{' '}
                      {underWay && (
                        <>
                          <button
                            type="button"
                            className="btn-link"
                            disabled={saving}
                            onClick={() =>
                              void run(async () =>
                                applied(await endUnavailabilityEarly(venueId, p.id), p.id, 'Unavailable period ended early.'),
                              )
                            }
                          >
                            End early
                          </button>{' '}
                        </>
                      )}
                      <button
                        type="button"
                        className="btn-link"
                        disabled={saving}
                        onClick={() =>
                          void run(async () => {
                            await deleteUnavailability(venueId, p.id)
                            applied(null, p.id, 'Unavailable period removed.')
                          })
                        }
                      >
                        Remove
                      </button>
                      {p.affected_bookings.length > 0 && (
                        <ul aria-label={`Bookings affected by ${p.reason_category}`}>
                          {p.affected_bookings.map((b) => (
                            <li key={b.booking_id}>
                              {b.event_name} ({b.status}), {whenText(b.start_time)} to {whenText(b.end_time)}
                              {b.flagged ? ' - flagged for review' : ''}
                            </li>
                          ))}
                        </ul>
                      )}
                    </>
                  )}
                </li>
              )
            })}
          </ul>
        ))}
      {canEdit && (
        <form onSubmit={(e) => void submit(e)} noValidate aria-label="Mark venue unavailable">
          <h3>{editing ? 'Edit unavailable period' : 'Mark unavailable'}</h3>
          <div className={`field${errors.dates ? ' field-invalid' : ''}`}>
            <label htmlFor="unavailable-start">Unavailable from</label>
            <input
              id="unavailable-start"
              type="datetime-local"
              value={start}
              disabled={saving}
              aria-invalid={errors.dates ? true : undefined}
              aria-describedby={errors.dates ? 'unavailable-dates-error' : undefined}
              onChange={(e) => setStart(e.target.value)}
            />
          </div>
          <div className={`field${errors.dates ? ' field-invalid' : ''}`}>
            <label htmlFor="unavailable-end">Unavailable until</label>
            <input
              id="unavailable-end"
              type="datetime-local"
              value={end}
              disabled={saving}
              aria-invalid={errors.dates ? true : undefined}
              aria-describedby={errors.dates ? 'unavailable-dates-error' : undefined}
              onChange={(e) => setEnd(e.target.value)}
            />
          </div>
          {errors.dates && (
            <p id="unavailable-dates-error" className="field-error" role="alert">
              {errors.dates}
            </p>
          )}
          <div className={`field${errors.category ? ' field-invalid' : ''}`}>
            <label htmlFor="unavailable-reason">Reason</label>
            <select
              id="unavailable-reason"
              value={category}
              disabled={saving}
              aria-invalid={errors.category ? true : undefined}
              aria-describedby={errors.category ? 'unavailable-reason-error' : undefined}
              onChange={(e) => setCategory(e.target.value)}
            >
              <option value="">Choose a reason</option>
              {UNAVAILABILITY_REASONS.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
            {errors.category && (
              <p id="unavailable-reason-error" className="field-error" role="alert">
                {errors.category}
              </p>
            )}
          </div>
          <div className="field">
            <label htmlFor="unavailable-details">Details (optional)</label>
            <textarea
              id="unavailable-details"
              rows={2}
              maxLength={2000}
              value={details}
              disabled={saving}
              onChange={(e) => setDetails(e.target.value)}
            />
          </div>
          <button type="submit" className="btn-primary" disabled={saving}>
            {saving ? 'Saving…' : editing ? 'Save changes' : 'Save unavailable period'}
          </button>
          {editing && (
            <button type="button" className="btn-secondary" disabled={saving} onClick={reset}>
              Cancel edit
            </button>
          )}
        </form>
      )}
      {formError && (
        <p className="form-error" role="alert">
          {formError}
        </p>
      )}
      {notice && (
        <p className="notice" role="status">
          {notice}{' '}
          {notice.includes('future booking') && <Link to="/venue-staff/flagged">View flagged bookings</Link>}
        </p>
      )}
    </section>
  )
}

/** Pick a date range and list when the venue is held or closed in it. A
 *  booking shows its occupied window (setup and turnaround included), so the
 *  venue never looks free during it. */
function AvailabilitySection({ venueId }: { venueId: number }) {
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [rangeError, setRangeError] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [busy, setBusy] = useState<BusyPeriod[] | null>(null)
  const [checking, setChecking] = useState(false)

  async function check(e: React.FormEvent) {
    e.preventDefault()
    setLoadError(null)
    const problem = availabilityRangeError(start, end)
    setRangeError(problem)
    if (problem) {
      setBusy(null)
      return
    }
    setChecking(true)
    try {
      const result = await getVenueAvailability(
        venueId,
        new Date(start).toISOString(),
        new Date(end).toISOString(),
      )
      setBusy(result.busy)
    } catch (err) {
      setBusy(null)
      setLoadError(err instanceof ApiError ? err.message : 'Could not check availability.')
    } finally {
      setChecking(false)
    }
  }

  return (
    <section className="card" aria-labelledby="availability-heading">
      <h2 id="availability-heading">Availability</h2>
      <form onSubmit={(e) => void check(e)} noValidate aria-label="Check availability">
        <div className={`field${rangeError ? ' field-invalid' : ''}`}>
          <label htmlFor="availability-start">Availability from</label>
          <input
            id="availability-start"
            type="datetime-local"
            value={start}
            aria-invalid={rangeError ? true : undefined}
            aria-describedby={rangeError ? 'availability-error' : undefined}
            onChange={(e) => setStart(e.target.value)}
          />
        </div>
        <div className={`field${rangeError ? ' field-invalid' : ''}`}>
          <label htmlFor="availability-end">Availability until</label>
          <input
            id="availability-end"
            type="datetime-local"
            value={end}
            aria-invalid={rangeError ? true : undefined}
            aria-describedby={rangeError ? 'availability-error' : undefined}
            onChange={(e) => setEnd(e.target.value)}
          />
        </div>
        {rangeError && (
          <p id="availability-error" className="field-error" role="alert">
            {rangeError}
          </p>
        )}
        <button type="submit" className="btn-primary" disabled={checking}>
          {checking ? 'Checking…' : 'Check availability'}
        </button>
      </form>
      {loadError && (
        <p className="form-error" role="alert">
          {loadError}
        </p>
      )}
      {busy !== null && (
        <div role="region" aria-label="Availability results" aria-live="polite">
          {busy.length === 0 ? (
            <p>Available for the whole period.</p>
          ) : (
            <>
              <p>Not available at these times:</p>
              <ul className="detail-value-list">
                {busy.map((p, i) => (
                  <li key={`${p.kind}-${p.start}-${i}`}>{describeBusyPeriod(p)}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </section>
  )
}

/** Everything an internal user needs to judge whether a venue suits an
 *  event. Read-only except Venue Staff's setup and turnaround form. */
export function VenueView() {
  const { id } = useParams()
  const { user } = useAuth()
  const canEdit = user?.role === Role.VENUE_STAFF
  const [venue, setVenue] = useState<VenueDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    if (!id) return
    let cancelled = false
    getVenue(Number(id))
      .then((v) => {
        if (!cancelled) setVenue(v)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        console.error('Failed to load venue details.', { venueId: Number(id), error: err })
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

      <section className="card" aria-labelledby="setup-turnaround-heading">
        <h2 id="setup-turnaround-heading">Setup and turnaround</h2>
        <dl className="detail-list">
          <div className="detail-row">
            <dt>Setup time</dt>
            <dd>{describeMinutes(venue.setup_minutes)}</dd>
          </div>
          <div className="detail-row">
            <dt>Turnaround time</dt>
            <dd>{describeMinutes(venue.turnaround_minutes)}</dd>
          </div>
          <div className="detail-row">
            <dt>Venue occupied</dt>
            <dd>
              From the Event start minus {venue.setup_minutes ?? 0} minutes to the Event end plus{' '}
              {venue.turnaround_minutes ?? 0} minutes
            </dd>
          </div>
        </dl>
        {canEdit && <SetupTurnaroundForm venue={venue} onSaved={setVenue} />}
      </section>

      <UnavailabilitySection venueId={venue.id} canEdit={canEdit} />

      <AvailabilitySection venueId={venue.id} />

      {user?.role === Role.COORDINATOR && (
        <VenueSuitability venueId={venue.id} venueName={venue.name} />
      )}

      <p>
        <Link to={`/venues/${venue.id}/availability`}>View availability calendar →</Link>
      </p>

      {back}
    </div>
  )
}
