import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { ApiError } from '../../lib/api'
import {
  createEvent,
  fromDateTimeLocal,
  getEvent,
  submitEvent,
  toDateTimeLocal,
  updateEvent,
} from '../../lib/events'
import type { EventInput } from '../../lib/events'

/** Every input is a string here, which is what DOM inputs give us. It is
 *  converted to the API's shape in `toPayload` on the way out. */
interface FormState {
  name: string
  purpose: string
  event_type: string
  description: string
  programme: string
  proposed_start: string
  proposed_end: string
  expected_attendance: string
  venue_requirements: string
  room_layout_preference: string
  accessibility_needs: string
  equipment_requirements: string
  special_arrangements: string
  registration_enabled: boolean
}

const EMPTY: FormState = {
  name: '',
  purpose: '',
  event_type: '',
  description: '',
  programme: '',
  proposed_start: '',
  proposed_end: '',
  expected_attendance: '',
  venue_requirements: '',
  room_layout_preference: '',
  accessibility_needs: '',
  equipment_requirements: '',
  special_arrangements: '',
  registration_enabled: false,
}

// Suggestions only -- the backend stores event_type as free text because the
// customer briefing leaves the category list open-ended ("...or any other
// type defined by ConnectSphere").
const EVENT_TYPES = [
  'conference',
  'workshop',
  'training session',
  'exhibition',
  'meeting',
  'seminar',
  'networking event',
]

const ROOM_LAYOUTS = ['classroom', 'theatre', 'boardroom', 'banquet', 'exhibition', 'u-shape']

/** '' -> null so an untouched field is stored as "not answered" rather than
 *  an empty string. The submit endpoint treats both as missing, but null is
 *  the honest representation. */
function orNull(value: string): string | null {
  const trimmed = value.trim()
  return trimmed === '' ? null : trimmed
}

function toPayload(form: FormState): EventInput {
  const attendance = form.expected_attendance.trim()
  return {
    name: orNull(form.name),
    purpose: orNull(form.purpose),
    event_type: orNull(form.event_type),
    description: orNull(form.description),
    programme: orNull(form.programme),
    proposed_start: fromDateTimeLocal(form.proposed_start),
    proposed_end: fromDateTimeLocal(form.proposed_end),
    expected_attendance: attendance === '' ? null : Number(attendance),
    venue_requirements: orNull(form.venue_requirements),
    room_layout_preference: orNull(form.room_layout_preference),
    accessibility_needs: orNull(form.accessibility_needs),
    equipment_requirements: orNull(form.equipment_requirements),
    special_arrangements: orNull(form.special_arrangements),
    registration_enabled: form.registration_enabled,
  }
}

export function EventForm() {
  const { id } = useParams()
  const navigate = useNavigate()
  const eventId = id ? Number(id) : null

  const [form, setForm] = useState<FormState>(EMPTY)
  const [loading, setLoading] = useState(eventId !== null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Field names the server flagged on the last submit attempt, so each
  // offending input can be marked rather than showing one generic error.
  const [missing, setMissing] = useState<string[]>([])

  useEffect(() => {
    if (eventId === null) return
    let cancelled = false
    void (async () => {
      try {
        const e = await getEvent(eventId)
        if (cancelled) return
        setForm({
          name: e.name ?? '',
          purpose: e.purpose ?? '',
          event_type: e.event_type ?? '',
          description: e.description ?? '',
          programme: e.programme ?? '',
          proposed_start: toDateTimeLocal(e.proposed_start),
          proposed_end: toDateTimeLocal(e.proposed_end),
          expected_attendance: e.expected_attendance?.toString() ?? '',
          venue_requirements: e.venue_requirements ?? '',
          room_layout_preference: e.room_layout_preference ?? '',
          accessibility_needs: e.accessibility_needs ?? '',
          equipment_requirements: e.equipment_requirements ?? '',
          special_arrangements: e.special_arrangements ?? '',
          registration_enabled: e.registration_enabled,
        })
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : 'Could not load this request.')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [eventId])

  const set = useCallback(
    <K extends keyof FormState>(key: K, value: FormState[K]) =>
      setForm((prev) => ({ ...prev, [key]: value })),
    [],
  )

  /** Persist the current form. Used on its own by "Save as draft", and as
   *  the first half of submitting -- so what gets validated is what is on
   *  screen, not whatever was last saved. */
  async function persist(): Promise<number> {
    const payload = toPayload(form)
    if (eventId !== null) {
      await updateEvent(eventId, payload)
      return eventId
    }
    return (await createEvent(payload)).id
  }

  function reportError(err: unknown, fallback: string) {
    if (err instanceof ApiError) {
      setError(err.message)
      setMissing(err.fields)
    } else {
      setError(fallback)
      setMissing([])
    }
  }

  async function onSaveDraft(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setMissing([])
    setBusy(true)
    try {
      await persist()
      navigate('/organiser/events', { replace: true })
    } catch (err) {
      reportError(err, 'Could not reach the server. Is the backend running?')
    } finally {
      setBusy(false)
    }
  }

  async function onSubmitRequest() {
    setError(null)
    setMissing([])
    setBusy(true)
    try {
      const savedId = await persist()
      await submitEvent(savedId)
      navigate('/organiser/events?tab=submitted', { replace: true })
    } catch (err) {
      reportError(err, 'Could not reach the server. Is the backend running?')
    } finally {
      setBusy(false)
    }
  }

  if (loading) return null

  const flagged = (field: keyof FormState) => missing.includes(field)
  const fieldClass = (field: keyof FormState) =>
    flagged(field) ? 'field field-invalid' : 'field'

  return (
    <div className="stack">
      <header className="page-header">
        <h1>{eventId === null ? 'New event request' : 'Edit event request'}</h1>
        <p className="page-subtitle">
          Save as a draft at any point — nothing here is required until you submit.
        </p>
      </header>

      {error && (
        <p className="form-error" role="alert">
          {missing.length > 0
            ? `Cannot submit yet — ${missing.length} required ${missing.length === 1 ? 'field is' : 'fields are'} incomplete. They are marked below.`
            : error}
        </p>
      )}

      {/* noValidate, and not a single `required` attribute: a draft must be
          saveable while empty. The backend is the only gate on completeness,
          and only at submit time. */}
      <form onSubmit={onSaveDraft} noValidate className="stack">
        <section className="card stack-tight">
          <h2>About the event</h2>

          <div className={fieldClass('name')}>
            <label htmlFor="name">Event name</label>
            <input
              id="name"
              type="text"
              maxLength={200}
              placeholder="Regional Partner Conference"
              value={form.name}
              onChange={(e) => set('name', e.target.value)}
              aria-invalid={flagged('name')}
            />
            {flagged('name') && <p className="field-error">Required before submitting.</p>}
          </div>

          <div className={fieldClass('event_type')}>
            <label htmlFor="event_type">Event type</label>
            <input
              id="event_type"
              type="text"
              list="event-types"
              maxLength={100}
              placeholder="conference"
              value={form.event_type}
              onChange={(e) => set('event_type', e.target.value)}
              aria-invalid={flagged('event_type')}
            />
            <datalist id="event-types">
              {EVENT_TYPES.map((t) => (
                <option key={t} value={t} />
              ))}
            </datalist>
            {flagged('event_type') && <p className="field-error">Required before submitting.</p>}
          </div>

          <div className={fieldClass('purpose')}>
            <label htmlFor="purpose">Purpose</label>
            <textarea
              id="purpose"
              rows={2}
              placeholder="Why is this event being held?"
              value={form.purpose}
              onChange={(e) => set('purpose', e.target.value)}
              aria-invalid={flagged('purpose')}
            />
            {flagged('purpose') && <p className="field-error">Required before submitting.</p>}
          </div>

          <div className="field">
            <label htmlFor="description">Description</label>
            <textarea
              id="description"
              rows={3}
              value={form.description}
              onChange={(e) => set('description', e.target.value)}
            />
            <p className="field-hint">Optional.</p>
          </div>
        </section>

        <section className="card stack-tight">
          <h2>Schedule &amp; size</h2>

          <div className="form-row">
            <div className={fieldClass('proposed_start')}>
              <label htmlFor="proposed_start">Preferred start</label>
              <input
                id="proposed_start"
                type="datetime-local"
                value={form.proposed_start}
                onChange={(e) => set('proposed_start', e.target.value)}
                aria-invalid={flagged('proposed_start')}
              />
              {flagged('proposed_start') && (
                <p className="field-error">Required before submitting.</p>
              )}
            </div>

            <div className={fieldClass('proposed_end')}>
              <label htmlFor="proposed_end">Preferred end</label>
              <input
                id="proposed_end"
                type="datetime-local"
                value={form.proposed_end}
                onChange={(e) => set('proposed_end', e.target.value)}
                aria-invalid={flagged('proposed_end')}
              />
              {flagged('proposed_end') && (
                <p className="field-error">Required before submitting.</p>
              )}
            </div>
          </div>

          <div className={fieldClass('expected_attendance')}>
            <label htmlFor="expected_attendance">Expected attendees</label>
            <input
              id="expected_attendance"
              type="number"
              min={1}
              placeholder="120"
              value={form.expected_attendance}
              onChange={(e) => set('expected_attendance', e.target.value)}
              aria-invalid={flagged('expected_attendance')}
            />
            {flagged('expected_attendance') && (
              <p className="field-error">Required before submitting.</p>
            )}
          </div>

          <div className="field">
            <label htmlFor="programme">General programme</label>
            <textarea
              id="programme"
              rows={4}
              placeholder="0900 registration&#10;0930 keynote&#10;1100 breakout sessions"
              value={form.programme}
              onChange={(e) => set('programme', e.target.value)}
            />
            <p className="field-hint">Sessions, breaks and presentations, if known.</p>
          </div>
        </section>

        <section className="card stack-tight">
          <h2>Requirements</h2>

          <div className={fieldClass('venue_requirements')}>
            <label htmlFor="venue_requirements">Venue requirements</label>
            <textarea
              id="venue_requirements"
              rows={2}
              placeholder="Main hall with stage and podium"
              value={form.venue_requirements}
              onChange={(e) => set('venue_requirements', e.target.value)}
              aria-invalid={flagged('venue_requirements')}
            />
            {flagged('venue_requirements') && (
              <p className="field-error">Required before submitting.</p>
            )}
          </div>

          <div className="field">
            <label htmlFor="room_layout_preference">Room layout preference</label>
            <input
              id="room_layout_preference"
              type="text"
              list="room-layouts"
              maxLength={100}
              placeholder="theatre"
              value={form.room_layout_preference}
              onChange={(e) => set('room_layout_preference', e.target.value)}
            />
            <datalist id="room-layouts">
              {ROOM_LAYOUTS.map((l) => (
                <option key={l} value={l} />
              ))}
            </datalist>
          </div>

          <div className={fieldClass('accessibility_needs')}>
            <label htmlFor="accessibility_needs">Accessibility requirements</label>
            <textarea
              id="accessibility_needs"
              rows={2}
              placeholder="Step-free access, hearing loop"
              value={form.accessibility_needs}
              onChange={(e) => set('accessibility_needs', e.target.value)}
              aria-invalid={flagged('accessibility_needs')}
            />
            {flagged('accessibility_needs') && (
              <p className="field-error">Required before submitting.</p>
            )}
          </div>

          <div className={fieldClass('equipment_requirements')}>
            <label htmlFor="equipment_requirements">Equipment requirements</label>
            <textarea
              id="equipment_requirements"
              rows={2}
              placeholder="2 projectors, 4 radio microphones"
              value={form.equipment_requirements}
              onChange={(e) => set('equipment_requirements', e.target.value)}
              aria-invalid={flagged('equipment_requirements')}
            />
            {flagged('equipment_requirements') && (
              <p className="field-error">Required before submitting.</p>
            )}
          </div>

          <div className="field">
            <label htmlFor="registration_enabled">Registration</label>
            <label className="checkbox-row">
              <input
                id="registration_enabled"
                type="checkbox"
                checked={form.registration_enabled}
                onChange={(e) => set('registration_enabled', e.target.checked)}
              />
              <span>Attendees must register for this event</span>
            </label>
          </div>

          <div className="field">
            <label htmlFor="special_arrangements">Other special arrangements</label>
            <textarea
              id="special_arrangements"
              rows={2}
              placeholder="Halal catering, interpreter booth"
              value={form.special_arrangements}
              onChange={(e) => set('special_arrangements', e.target.value)}
            />
          </div>
        </section>

        <div className="form-actions">
          <button type="submit" className="btn-secondary" disabled={busy}>
            {busy ? 'Saving…' : 'Save as draft'}
          </button>
          <button
            type="button"
            className="btn-primary"
            disabled={busy}
            onClick={onSubmitRequest}
          >
            Submit request
          </button>
          <Link to="/organiser/events" className="form-cancel">
            Cancel
          </Link>
        </div>
      </form>
    </div>
  )
}
