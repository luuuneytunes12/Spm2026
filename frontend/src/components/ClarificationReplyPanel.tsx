import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError } from '../lib/api'
import { listClarifications, replyToClarification } from '../lib/clarifications'
import type { ClarificationOut, ClarificationUpdates } from '../lib/clarifications'
import { EventStatus } from '../lib/events'
import type { EventDetail } from '../lib/events'
import { ClarificationThread } from './ClarificationThread'

type TextField = Exclude<keyof ClarificationUpdates, 'expected_attendance'>

const TEXT_FIELDS: [TextField, string][] = [
  ['name', 'Event name'],
  ['purpose', 'Purpose'],
  ['description', 'Description'],
  ['venue_requirements', 'Venue requirements'],
  ['accessibility_needs', 'Accessibility requirements'],
  ['equipment_requirements', 'Other equipment notes'],
  ['special_arrangements', 'Special arrangements'],
]

/** Organiser side of "Respond to Clarification Request" (SCRUM-103).
 *
 *  Offered only while the event is Awaiting Organiser Reply. Amended fields
 *  are sent as `updates` -- only the ones that differ from the saved event. */
export function ClarificationReplyPanel({
  event,
  onChanged,
}: {
  event: EventDetail
  onChanged?: () => void
}) {
  const eventId = event.id
  const [items, setItems] = useState<ClarificationOut[]>([])
  const [message, setMessage] = useState('')
  const [fieldError, setFieldError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sent, setSent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [amend, setAmend] = useState(false)
  const [text, setText] = useState<Record<TextField, string>>(() => fromEvent(event))
  const [attendance, setAttendance] = useState(event.expected_attendance?.toString() ?? '')

  const load = useCallback(async () => {
    setItems(await listClarifications(eventId).catch(() => []))
  }, [eventId])

  useEffect(() => {
    let cancelled = false
    listClarifications(eventId)
      .then((list) => {
        if (!cancelled) setItems(list)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [eventId, event.status])

  const canReply = event.status === EventStatus.AWAITING_ORGANISER_REPLY
  if (!canReply && items.length === 0) return null
  const latestRequest = [...items].reverse().find((c) => c.kind === 'request')

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSent(false)
    if (!message.trim()) {
      setFieldError('Enter your reply.')
      return
    }
    setFieldError(null)

    const updates: ClarificationUpdates = {}
    if (amend) {
      const saved = fromEvent(event)
      for (const [key] of TEXT_FIELDS) {
        const value = text[key].trim()
        if (value !== saved[key].trim() && value !== '') updates[key] = value
      }
      const n = Number(attendance)
      if (attendance.trim() !== '' && n !== event.expected_attendance) {
        updates.expected_attendance = n
      }
    }

    setBusy(true)
    try {
      await replyToClarification(eventId, {
        message: message.trim(),
        ...(Object.keys(updates).length > 0 ? { updates } : {}),
      })
      setMessage('')
      setSent(true)
      setAmend(false)
      await load()
      onChanged?.()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not send your reply.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card stack-tight" aria-labelledby="clarification-heading">
      <h2 id="clarification-heading">Clarification</h2>
      {canReply && latestRequest && (
        <p className="page-subtitle">
          Your Event Coordinator needs more information before the review can continue.
        </p>
      )}
      <ClarificationThread items={items} />
      {sent && (
        <p className="notice" role="status">
          Your reply has been sent. The request is back under review.
        </p>
      )}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {canReply && (
        <form onSubmit={onSubmit} noValidate className="stack-tight">
          <div className={fieldError ? 'field field-invalid' : 'field'}>
            <label htmlFor="clarification-reply">Your reply</label>
            <textarea
              id="clarification-reply"
              rows={4}
              value={message}
              onChange={(e) => {
                setMessage(e.target.value)
                setSent(false)
              }}
              aria-invalid={fieldError !== null}
              aria-describedby={fieldError ? 'clarification-reply-error' : undefined}
            />
            {fieldError && (
              <p id="clarification-reply-error" className="field-error">
                {fieldError}
              </p>
            )}
          </div>

          <div className="field">
            <label className="checkbox-label">
              <input type="checkbox" checked={amend} onChange={(e) => setAmend(e.target.checked)} />{' '}
              Update the request fields
            </label>
          </div>
          {amend && (
            <fieldset className="stack-tight">
              <legend>Amend the request</legend>
              {TEXT_FIELDS.map(([key, label]) => (
                <div className="field" key={key}>
                  <label htmlFor={`amend-${key}`}>{label}</label>
                  <textarea
                    id={`amend-${key}`}
                    rows={2}
                    value={text[key]}
                    onChange={(e) => setText((prev) => ({ ...prev, [key]: e.target.value }))}
                  />
                </div>
              ))}
              <div className="field">
                <label htmlFor="amend-expected_attendance">Expected attendees</label>
                <input
                  id="amend-expected_attendance"
                  type="number"
                  min={1}
                  value={attendance}
                  onChange={(e) => setAttendance(e.target.value)}
                />
              </div>
            </fieldset>
          )}

          <div className="form-actions">
            <button type="submit" className="btn-primary" disabled={busy}>
              {busy ? 'Sending…' : 'Send reply'}
            </button>
          </div>
        </form>
      )}
    </section>
  )
}

function fromEvent(event: EventDetail): Record<TextField, string> {
  return {
    name: event.name ?? '',
    purpose: event.purpose ?? '',
    description: event.description ?? '',
    venue_requirements: event.venue_requirements ?? '',
    accessibility_needs: event.accessibility_needs ?? '',
    equipment_requirements: event.equipment_requirements ?? '',
    special_arrangements: event.special_arrangements ?? '',
  }
}
