import { useId, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError } from '../lib/api'
import { TECH_SUPPORT_STATUS_OPTIONS, updateSupportRequirement } from '../lib/equipmentRequirements'
import type { SupportRequirement, SupportRequirementChanges } from '../lib/equipmentRequirements'

interface Props {
  requirement: SupportRequirement
  /** Called with the requirement as the server now holds it. */
  onSaved: (updated: SupportRequirement) => void
  onCancel: () => void
}

/** Technical Support's editor for the two things they own on a requirement:
 *  its status, and the quantity needed. The type and the notes are the
 *  Coordinator's.
 *
 *  The rules are the server's (a reserved status cannot be chosen; the
 *  quantity cannot go below what is reserved). The editor mirrors them so
 *  nothing is offered that will be refused, and shows the server's own
 *  reason if it refuses anyway. */
export function RequirementStatusEditor({ requirement, onSaved, onCancel }: Props) {
  const ids = useId()
  const reserved = requirement.reserved_quantity
  const settable = TECH_SUPPORT_STATUS_OPTIONS.some((o) => o.value === requirement.status)
  const [status, setStatus] = useState(settable ? requirement.status : 'requested')
  const [quantity, setQuantity] = useState(String(requirement.quantity_needed))
  const [problem, setProblem] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // Once something is reserved the status is whatever the reservations say,
  // so there is no choice to make.
  const statusChanged = reserved === 0 && status !== requirement.status
  const quantityChanged = quantity !== String(requirement.quantity_needed)

  async function submit(event: FormEvent) {
    event.preventDefault()
    const needed = Number(quantity)
    if (!Number.isInteger(needed) || needed < 1) {
      setProblem('Quantity must be at least 1.')
      return
    }
    if (needed < reserved) {
      setProblem(`${reserved} already reserved; the quantity needed cannot be less than that.`)
      return
    }

    const changes: SupportRequirementChanges = {}
    if (statusChanged) changes.status = status
    if (quantityChanged) changes.quantity_needed = needed

    setProblem(null)
    setBusy(true)
    try {
      onSaved(await updateSupportRequirement(requirement.id, changes))
    } catch (err) {
      setProblem(err instanceof ApiError ? err.message : 'Could not save this requirement.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={(e) => void submit(e)} noValidate className="requirement-panel">
      <fieldset className="field-group requirement-editor">
        <legend className="visually-hidden">{`Update ${requirement.category} requirement`}</legend>
        <div className="form-row">
          {reserved === 0 ? (
            <div className="field">
              <label htmlFor={`${ids}-status`}>Status</label>
              <select id={`${ids}-status`} value={status} onChange={(e) => setStatus(e.target.value)}>
                {TECH_SUPPORT_STATUS_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <p className="field-hint">
              The status follows the reservations: {reserved} of {requirement.quantity_needed} reserved.
            </p>
          )}
          <div className={problem ? 'field field-invalid' : 'field'}>
            <label htmlFor={`${ids}-qty`}>Quantity needed</label>
            <input
              id={`${ids}-qty`}
              type="number"
              min={reserved > 0 ? reserved : 1}
              inputMode="numeric"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              aria-invalid={problem ? true : undefined}
            />
            {reserved > 0 && (
              <p className="field-hint">
                {reserved} already reserved; the quantity needed cannot go below that.
              </p>
            )}
          </div>
        </div>
        {problem && (
          <p className="field-error" role="alert">
            {problem}
          </p>
        )}
        <div className="form-actions">
          <button
            type="submit"
            className="btn-secondary"
            disabled={busy || !(statusChanged || quantityChanged)}
          >
            Save changes
          </button>
          <button type="button" className="btn-link-muted" onClick={onCancel}>
            Cancel
          </button>
        </div>
      </fieldset>
    </form>
  )
}
