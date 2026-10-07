import { useEffect, useState } from 'react'
import { ApiError } from '../../lib/api'
import { listLeadCoordinators } from '../../lib/coordinatorLead'
import type { LeadCoordinator } from '../../lib/coordinatorLead'

interface Props {
  heading: string
  label: string
  confirmLabel: string
  /** A Coordinator to leave out of the list (e.g. the one who already has the Event). */
  excludeId?: number | null
  /** Makes the move. Resolves with the name of the Coordinator to show in the confirmation. */
  onConfirm: (coordinatorId: number) => Promise<string>
  /** Wording of the confirmation line, given the Coordinator's name. */
  doneText: (name: string) => string
  /** Shown once done, to carry on from here. */
  next?: React.ReactNode
}

/** Pick a Coordinator, with how many active Events each holds, and confirm.
 *  Shared by Assign (Unassigned Queue) and Reassign (Coordinator Assignments). */
export function CoordinatorPicker({ heading, label, confirmLabel, excludeId, onConfirm, doneText, next }: Props) {
  const [coordinators, setCoordinators] = useState<LeadCoordinator[]>([])
  const [selected, setSelected] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    listLeadCoordinators()
      .then((rows) => {
        if (!cancelled) setCoordinators(rows)
      })
      .catch(() => {
        if (!cancelled) setError('Could not load the Event Coordinators.')
      })
    return () => {
      cancelled = true
    }
  }, [])

  const choices = coordinators.filter((c) => c.id !== excludeId)

  async function confirm() {
    setBusy(true)
    setError(null)
    try {
      setDone(await onConfirm(Number(selected)))
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Could not reach the server. Is the backend running?',
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card" aria-labelledby="picker-heading">
      <h2 id="picker-heading">{heading}</h2>
      {done ? (
        <>
          <p role="status">{doneText(done)}</p>
          {next}
        </>
      ) : (
        <>
          <div className="field">
            <label htmlFor="coordinator-picker">{label}</label>
            <select id="coordinator-picker" value={selected} onChange={(e) => setSelected(e.target.value)}>
              <option value="">Choose an Event Coordinator</option>
              {choices.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.active_events} active {c.active_events === 1 ? 'Event' : 'Events'})
                </option>
              ))}
            </select>
          </div>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <button type="button" className="btn btn-primary" disabled={!selected || busy} onClick={confirm}>
            {busy ? 'Saving…' : confirmLabel}
          </button>
        </>
      )}
    </section>
  )
}
