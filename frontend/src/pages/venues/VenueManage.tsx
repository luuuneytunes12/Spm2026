import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { ApiError } from '../../lib/api'
import {
  addVenue,
  editVenue,
  listVenueActivity,
  toVenueInput,
  venueFormErrors,
} from '../../lib/venueCatalogue'
import type { FlaggedBooking, VenueActivityEntry, VenueFormErrors, VenueFormValues } from '../../lib/venueCatalogue'
import { getVenue } from '../../lib/venues'

const EMPTY: VenueFormValues = {
  name: '',
  location: '',
  capacity: '',
  facilities: '',
  accessibility_features: '',
  supported_layouts: '',
  operating_hours: '',
}

interface FieldProps {
  id: keyof VenueFormValues
  label: string
  hint?: string
  value: string
  error?: string
  multiline?: boolean
  disabled: boolean
  onChange: (value: string) => void
}

function Field({ id, label, hint, value, error, multiline, disabled, onChange }: FieldProps) {
  const hintId = `${id}-hint`
  const errorId = `${id}-error`
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(' ') || undefined
  const common = {
    id,
    value,
    disabled,
    'aria-invalid': error ? true : undefined,
    'aria-describedby': describedBy,
  }
  return (
    <div className={`field${error ? ' field-invalid' : ''}`}>
      <label htmlFor={id}>{label}</label>
      {multiline ? (
        <textarea rows={3} {...common} onChange={(e) => onChange(e.target.value)} />
      ) : (
        <input type="text" {...common} onChange={(e) => onChange(e.target.value)} />
      )}
      {hint && (
        <p id={hintId} className="field-hint">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="field-error" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}

/** Venue Staff's form to add a Venue (no :id) or edit one (SCRUM-108). Nothing
 *  is sent until the required details are present and the capacity is a
 *  positive whole number; when the server refuses (e.g. a duplicate name) its
 *  reason is shown and the form keeps what was typed. */
export function VenueManage() {
  const { id } = useParams()
  const editingId = id ? Number(id) : null
  const navigate = useNavigate()
  const [values, setValues] = useState<VenueFormValues>(EMPTY)
  const [errors, setErrors] = useState<VenueFormErrors>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [loading, setLoading] = useState(editingId !== null)
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [flagged, setFlagged] = useState<FlaggedBooking[]>([])
  const [activity, setActivity] = useState<VenueActivityEntry[]>([])

  useEffect(() => {
    let cancelled = false
    if (editingId !== null) {
      getVenue(editingId)
        .then((v) => {
          if (cancelled) return
          setValues({
            name: v.name,
            location: v.location,
            capacity: String(v.capacity),
            facilities: v.facilities.join(', '),
            accessibility_features: v.accessibility_features.join(', '),
            supported_layouts: v.supported_layouts.join(', '),
            operating_hours: v.operating_hours ?? '',
          })
        })
        .catch((err) => {
          if (!cancelled) setFormError(err instanceof ApiError ? err.message : 'Could not load the venue.')
        })
        .finally(() => {
          if (!cancelled) setLoading(false)
        })
    }
    return () => {
      cancelled = true
    }
  }, [editingId])

  useEffect(() => {
    let cancelled = false
    listVenueActivity()
      .then((rows) => {
        if (!cancelled) setActivity(rows)
      })
      .catch(() => {
        if (!cancelled) setActivity([])
      })
    return () => {
      cancelled = true
    }
  }, [notice])

  function set(key: keyof VenueFormValues) {
    return (value: string) => setValues((current) => ({ ...current, [key]: value }))
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setNotice(null)
    setFormError(null)
    setFlagged([])
    const found = venueFormErrors(values)
    setErrors(found)
    if (Object.keys(found).length > 0) return
    setSaving(true)
    try {
      const body = toVenueInput(values)
      if (editingId === null) {
        const saved = await addVenue(body)
        navigate(`/venues/${saved.id}`)
        return
      }
      const saved = await editVenue(editingId, body)
      setFlagged(saved.flagged_bookings)
      setNotice(`${saved.name} saved.`)
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) {
        const text = err.messages.length > 0 ? err.messages.join(' ') : err.message
        const server: VenueFormErrors = {}
        for (const key of Object.keys(EMPTY) as (keyof VenueFormValues)[]) {
          if (err.fields.some((f) => f.endsWith(key))) server[key] = text
        }
        setErrors(server)
        if (Object.keys(server).length === 0) setFormError(text)
      } else {
        setFormError(err instanceof ApiError ? err.message : 'Could not save the venue.')
      }
    } finally {
      setSaving(false)
    }
  }

  if (loading) return null
  const disabled = saving

  return (
    <div className="stack">
      <header className="page-header">
        <h1>{editingId === null ? 'Add a venue' : 'Edit venue details'}</h1>
        <p className="page-subtitle">
          Event Coordinators see these details in the catalogue as soon as you save.
        </p>
      </header>
      <p>
        <Link to={editingId === null ? '/venues' : `/venues/${editingId}`}>← Back</Link>
      </p>

      <form className="card" onSubmit={(e) => void submit(e)} noValidate aria-label="Venue details">
        <Field id="name" label="Name" value={values.name} error={errors.name} disabled={disabled} onChange={set('name')} />
        <Field id="location" label="Location" value={values.location} error={errors.location} disabled={disabled} onChange={set('location')} />
        <Field
          id="capacity"
          label="Capacity (people)"
          hint="A whole number above zero."
          value={values.capacity}
          error={errors.capacity}
          disabled={disabled}
          onChange={set('capacity')}
        />
        <Field
          id="facilities"
          label="Facilities"
          hint="Separate with commas. Optional."
          value={values.facilities}
          disabled={disabled}
          onChange={set('facilities')}
        />
        <Field
          id="accessibility_features"
          label="Accessibility features"
          hint="Separate with commas. Optional."
          value={values.accessibility_features}
          disabled={disabled}
          onChange={set('accessibility_features')}
        />
        <Field
          id="supported_layouts"
          label="Supported room layouts"
          hint="Separate with commas, e.g. Theatre, Classroom."
          value={values.supported_layouts}
          error={errors.supported_layouts}
          disabled={disabled}
          onChange={set('supported_layouts')}
        />
        <Field
          id="operating_hours"
          label="Operating hours"
          hint="One entry per line, e.g. Mon-Fri 08:00-22:00."
          multiline
          value={values.operating_hours}
          error={errors.operating_hours}
          disabled={disabled}
          onChange={set('operating_hours')}
        />
        <button type="submit" className="btn-primary" disabled={disabled}>
          {saving ? 'Saving…' : editingId === null ? 'Add venue' : 'Save changes'}
        </button>
        {formError && (
          <p className="form-error" role="alert">
            {formError}
          </p>
        )}
        {notice && (
          <p className="notice" role="status">
            {notice}
          </p>
        )}
        {flagged.length > 0 && (
          <div className="form-error" role="alert">
            <p>
              {flagged.length} venue booking{flagged.length === 1 ? '' : 's'} kept and flagged for review:
            </p>
            <ul>
              {flagged.map((f) => (
                <li key={f.booking_id}>
                  {f.event_name ?? 'Untitled event'}: {f.reason}
                </li>
              ))}
            </ul>
          </div>
        )}
      </form>

      <section className="card" aria-labelledby="venue-activity-heading">
        <h2 id="venue-activity-heading">Venue Activity Log</h2>
        {activity.length === 0 ? (
          <p className="text-muted">No venue changes recorded yet.</p>
        ) : (
          <ul className="detail-value-list">
            {activity.map((row) => (
              <li key={row.id}>
                {row.note} By {row.changed_by ?? 'unknown'} on {new Date(row.created_at).toLocaleString()}.
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
