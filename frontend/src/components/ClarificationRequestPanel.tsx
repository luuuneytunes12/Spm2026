import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError } from '../lib/api'
import { listClarifications, requestClarification } from '../lib/clarifications'
import type { ClarificationOut } from '../lib/clarifications'
import { EventStatus } from '../lib/events'
import { ClarificationThread } from './ClarificationThread'

/** Coordinator side of "Request Event Clarification" (SCRUM-27).
 *
 *  A request can be sent only while the event is Under Review; while it is
 *  Awaiting Organiser Reply the outstanding request is shown read-only. The
 *  server enforces all of this -- this only decides what to offer. */
export function ClarificationRequestPanel({
  eventId,
  status,
  onChanged,
}: {
  eventId: number
  status: string
  onChanged?: () => void
}) {
  const [items, setItems] = useState<ClarificationOut[]>([])
  const [message, setMessage] = useState('')
  const [fieldError, setFieldError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sent, setSent] = useState(false)
  const [busy, setBusy] = useState(false)

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
  }, [eventId, status])

  const canSend = status === EventStatus.UNDER_REVIEW
  if (!canSend && items.length === 0 && status !== EventStatus.AWAITING_ORGANISER_REPLY) return null

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSent(false)
    if (!message.trim()) {
      setFieldError('Enter a message for the Event Organiser.')
      return
    }
    setFieldError(null)
    setBusy(true)
    try {
      await requestClarification(eventId, message.trim())
      setMessage('')
      setSent(true)
      await load()
      onChanged?.()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not send the clarification request.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card stack-tight" aria-labelledby="clarification-heading">
      <h2 id="clarification-heading">Clarification</h2>
      {status === EventStatus.AWAITING_ORGANISER_REPLY && (
        <p className="page-subtitle">Waiting for the Event Organiser to reply.</p>
      )}
      <ClarificationThread items={items} />
      {sent && (
        <p className="notice" role="status">
          Clarification request sent to the Event Organiser.
        </p>
      )}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {canSend && (
        <form onSubmit={onSubmit} noValidate className="stack-tight">
          <div className={fieldError ? 'field field-invalid' : 'field'}>
            <label htmlFor="clarification-message">Clarification request</label>
            <textarea
              id="clarification-message"
              rows={4}
              value={message}
              onChange={(e) => {
                setMessage(e.target.value)
                setSent(false)
              }}
              aria-invalid={fieldError !== null}
              aria-describedby={fieldError ? 'clarification-message-error' : undefined}
            />
            {fieldError && (
              <p id="clarification-message-error" className="field-error">
                {fieldError}
              </p>
            )}
          </div>
          <div className="form-actions">
            <button type="submit" className="btn-primary" disabled={busy}>
              {busy ? 'Sending…' : 'Send clarification request'}
            </button>
          </div>
        </form>
      )}
    </section>
  )
}
