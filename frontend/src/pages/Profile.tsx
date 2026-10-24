import { useState } from 'react'
import type { FormEvent } from 'react'
import { useAuth } from '../auth/useAuth'
import { ApiError } from '../lib/api'
import { COMMUNICATION_PREFERENCE_LABELS, CommunicationPreference } from '../lib/communication'
import { DEPARTMENT_LABELS, Department, RESPONSIBILITIES_MAX_LENGTH } from '../lib/departments'
import { isInternalStaff } from '../lib/roles'
import { expectedDigitsLabel, PHONE_COUNTRIES } from '../lib/phone'
import { updateMyProfile } from '../lib/profile'

interface FormState {
  name: string
  organisation: string
  email: string
  phone_country_code: string
  phone_number: string
  communication_preference: string
  department: string
  responsibilities: string
}

function toFormState(user: {
  name: string
  organisation: string | null
  email: string
  phone_country_code: string | null
  phone_number: string | null
  communication_preference: string | null
  department: string | null
  responsibilities: string | null
}): FormState {
  return {
    name: user.name,
    organisation: user.organisation ?? '',
    email: user.email,
    phone_country_code: user.phone_country_code ?? '',
    phone_number: user.phone_number ?? '',
    communication_preference: user.communication_preference ?? '',
    department: user.department ?? '',
    responsibilities: user.responsibilities ?? '',
  }
}

/** '' -> null so a cleared field is stored as "not set", not an empty
 *  string -- same convention as the event request form. */
function orNull(value: string): string | null {
  const trimmed = value.trim()
  return trimmed === '' ? null : trimmed
}

/** Own profile: name, organisation, contact details and communication
 *  preference -- plus, for a Coordinator, their availability status. Every
 *  registered user reaches this page, regardless of role -- it sits outside
 *  every RequireRole group in App.tsx. */
export function Profile() {
  const { user, refreshUser } = useAuth()
  const [form, setForm] = useState<FormState>(() => (user ? toFormState(user) : (null as never)))
  const [error, setError] = useState<string | null>(null)
  const [invalidFields, setInvalidFields] = useState<string[]>([])
  const [saved, setSaved] = useState(false)
  const [busy, setBusy] = useState(false)

  if (!user) return null
  const staff = isInternalStaff(user.role)

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }))
    setSaved(false)
  }

  // A rejected save leaves the typed values in the form so they can be
  // corrected; this is the way back to what is actually saved.
  const savedForm = toFormState(user)
  const dirty = (Object.keys(savedForm) as (keyof FormState)[]).some(
    (key) => form[key] !== savedForm[key],
  )

  function onDiscard() {
    setForm(savedForm)
    setError(null)
    setInvalidFields([])
    setSaved(false)
  }

  const flagged = (field: string) => invalidFields.includes(field)
  const fieldClass = (field: string) => (flagged(field) ? 'field field-invalid' : 'field')

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setInvalidFields([])
    setSaved(false)
    // Department is required of internal staff: blocked here, nothing sent.
    if (staff && form.department === '') {
      setError('Select your department.')
      setInvalidFields(['department'])
      return
    }
    setBusy(true)
    try {
      const updated = await updateMyProfile({
        name: form.name.trim(),
        organisation: orNull(form.organisation),
        email: form.email.trim(),
        phone_country_code: orNull(form.phone_country_code),
        phone_number: orNull(form.phone_number),
        communication_preference: orNull(form.communication_preference),
        // Only staff have these; anyone else would be refused by the API.
        ...(staff
          ? { department: form.department, responsibilities: orNull(form.responsibilities) }
          : {}),
      })
      setForm(toFormState(updated))
      await refreshUser()
      setSaved(true)
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message)
        setInvalidFields(err.fields)
      } else {
        setError('Could not reach the server. Is the backend running?')
      }
    } finally {
      setBusy(false)
    }
  }

  const digitsHint = expectedDigitsLabel(form.phone_country_code)

  return (
    <div className="stack">
      <header className="page-header">
        <h1>My profile</h1>
        <p className="page-subtitle">
          Keep your details up to date so the people you work with can reach you.
        </p>
      </header>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {saved && !error && (
        <p className="notice" role="status">
          Your profile has been updated.
        </p>
      )}

      <form onSubmit={onSubmit} noValidate className="stack">
        <section className="card stack-tight">
          <h2>About you</h2>

          <div className={fieldClass('name')}>
            <label htmlFor="name">Name</label>
            <input
              id="name"
              type="text"
              maxLength={200}
              value={form.name}
              onChange={(e) => set('name', e.target.value)}
              aria-invalid={flagged('name')}
            />
            {flagged('name') && <p className="field-error">Name cannot be blank.</p>}
          </div>

          <div className="field">
            <label htmlFor="organisation">Organisation</label>
            <input
              id="organisation"
              type="text"
              maxLength={200}
              placeholder="Optional"
              value={form.organisation}
              onChange={(e) => set('organisation', e.target.value)}
            />
          </div>
        </section>

        {staff && (
          <section className="card stack-tight">
            <h2>Work</h2>

            <div className={fieldClass('department')}>
              <label htmlFor="department">Department</label>
              <select
                id="department"
                value={form.department}
                onChange={(e) => set('department', e.target.value)}
                aria-invalid={flagged('department')}
                aria-required="true"
              >
                <option value="">Select a department</option>
                {Object.values(Department).map((d) => (
                  <option key={d} value={d}>
                    {DEPARTMENT_LABELS[d]}
                  </option>
                ))}
              </select>
              {flagged('department') && <p className="field-error">Select your department.</p>}
            </div>

            <div className={fieldClass('responsibilities')}>
              <label htmlFor="responsibilities">Responsibilities</label>
              <textarea
                id="responsibilities"
                rows={4}
                maxLength={RESPONSIBILITIES_MAX_LENGTH}
                placeholder="Optional -- what colleagues can come to you for"
                value={form.responsibilities}
                onChange={(e) => set('responsibilities', e.target.value)}
                aria-invalid={flagged('responsibilities')}
              />
            </div>
          </section>
        )}

        <section className="card stack-tight">
          <h2>Contact details</h2>

          <div className={fieldClass('email')}>
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              value={form.email}
              onChange={(e) => set('email', e.target.value)}
              aria-invalid={flagged('email')}
            />
            {flagged('email') && <p className="field-error">Enter a valid email address.</p>}
          </div>

          <div className="form-row">
            <div className={fieldClass('phone_country_code')}>
              <label htmlFor="phone_country_code">Country code</label>
              <select
                id="phone_country_code"
                value={form.phone_country_code}
                onChange={(e) => {
                  const code = e.target.value
                  setForm((prev) => ({
                    ...prev,
                    phone_country_code: code,
                    // Clearing the country also clears the number, so the
                    // two are never sent half-set.
                    phone_number: code === '' ? '' : prev.phone_number,
                  }))
                  setSaved(false)
                }}
                aria-invalid={flagged('phone_country_code')}
              >
                <option value="">No phone number</option>
                {PHONE_COUNTRIES.map((c) => (
                  <option key={c.code} value={c.code}>
                    {c.label}
                  </option>
                ))}
              </select>
            </div>

            <div className={fieldClass('phone_number')}>
              <label htmlFor="phone_number">Phone number</label>
              <input
                id="phone_number"
                type="tel"
                inputMode="numeric"
                placeholder="Digits only"
                value={form.phone_number}
                onChange={(e) => set('phone_number', e.target.value)}
                aria-invalid={flagged('phone_number')}
                disabled={form.phone_country_code === ''}
              />
              {flagged('phone_number') ? (
                <p className="field-error">
                  Enter a valid phone number for the selected country code.
                </p>
              ) : (
                digitsHint && <p className="field-hint">{digitsHint} for this country code.</p>
              )}
            </div>
          </div>
        </section>

        <section className="card stack-tight">
          <h2>Communication preference</h2>

          <div className="field">
            <label htmlFor="communication_preference">How should we contact you?</label>
            <select
              id="communication_preference"
              value={form.communication_preference}
              onChange={(e) => set('communication_preference', e.target.value)}
            >
              <option value="">No preference</option>
              {Object.values(CommunicationPreference).map((pref) => (
                <option key={pref} value={pref}>
                  {COMMUNICATION_PREFERENCE_LABELS[pref]}
                </option>
              ))}
            </select>
          </div>
        </section>

        <div className="form-actions">
          <button type="submit" className="btn-primary" disabled={busy}>
            {busy ? 'Saving…' : 'Save changes'}
          </button>
          <button
            type="button"
            className="btn-secondary"
            onClick={onDiscard}
            disabled={busy || !dirty}
          >
            Discard changes
          </button>
        </div>
      </form>
    </div>
  )
}
