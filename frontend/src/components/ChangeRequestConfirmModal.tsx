import { useEffect, useId, useRef, useState } from 'react'

type Props = {
  busy: boolean
  onCancel: () => void
  onConfirm: (reason: string) => void
}

/** Last step before a change request is sent: warns that it cannot be
 *  edited afterwards and collects the reason the Coordinator will see. */
export function ChangeRequestConfirmModal({ busy, onCancel, onConfirm }: Props) {
  const titleId = useId()
  const reasonId = useId()
  const [reason, setReason] = useState('')
  const [reasonError, setReasonError] = useState<string | null>(null)
  const reasonRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    // Return focus to whatever opened the modal once it closes.
    const opener = document.activeElement as HTMLElement | null
    reasonRef.current?.focus()
    return () => opener?.focus()
  }, [])

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape' && !busy) onCancel()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [busy, onCancel])

  function confirm() {
    if (!reason.trim()) {
      setReasonError('Please explain why these changes are needed.')
      reasonRef.current?.focus()
      return
    }
    onConfirm(reason.trim())
  }

  return (
    <div className="modal-backdrop" onClick={busy ? undefined : onCancel}>
      <div
        className="modal card"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id={titleId}>Submit change request?</h2>
        <p className="modal-warning">
          Once submitted, this change request cannot be edited. Your Coordinator will
          review it, and the event stays unchanged until they approve it.
        </p>

        <div className={reasonError ? 'field field-invalid' : 'field'}>
          <label htmlFor={reasonId}>Reason for change</label>
          <textarea
            id={reasonId}
            ref={reasonRef}
            rows={4}
            maxLength={2000}
            value={reason}
            aria-invalid={reasonError ? true : undefined}
            aria-describedby={reasonError ? `${reasonId}-error` : undefined}
            onChange={(e) => {
              setReason(e.target.value)
              if (reasonError) setReasonError(null)
            }}
          />
          {reasonError && (
            <p id={`${reasonId}-error`} className="field-error" role="alert">
              {reasonError}
            </p>
          )}
        </div>

        <div className="form-actions">
          <button type="button" className="btn-primary" disabled={busy} onClick={confirm}>
            {busy ? 'Submitting…' : 'Submit change request'}
          </button>
          <button type="button" className="btn-secondary" disabled={busy} onClick={onCancel}>
            Go back
          </button>
        </div>
      </div>
    </div>
  )
}
