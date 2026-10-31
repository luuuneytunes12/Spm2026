import { useId, useState } from 'react'
import { ApiError } from '../lib/api'
import {
  OPERATIONAL_STATUS_LABELS,
  OperationalStatus,
  markOutOfService,
  returnToService,
} from '../lib/equipment'
import type { EquipmentItem, OutOfServiceCondition } from '../lib/equipment'

/** Mark part of an item Damaged or Under Maintenance, or return repaired units
 *  to service. The server decides what is allowed; the check here only saves a
 *  round trip on something that is never a quantity. */
export function EquipmentConditionForm({
  item,
  onChanged,
}: {
  item: EquipmentItem
  onChanged: (updated: EquipmentItem) => void
}) {
  const id = useId()
  const [condition, setCondition] = useState<OutOfServiceCondition>(OperationalStatus.DAMAGED)
  const [quantity, setQuantity] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  async function submit(change: typeof markOutOfService, done: string) {
    setError(null)
    setNotice(null)
    const units = Number(quantity)
    if (!Number.isInteger(units) || units <= 0) {
      setError('Enter a whole number greater than 0.')
      return
    }
    setBusy(true)
    try {
      onChanged(await change(item.id, condition, units))
      setNotice(`${units} ${done}.`)
      setQuantity('')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not save the change.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="stack-tight">
      <div className="form-row">
        <div className="field">
          <label htmlFor={`${id}-condition`}>Condition</label>
          <select
            id={`${id}-condition`}
            value={condition}
            onChange={(e) => setCondition(e.target.value as OutOfServiceCondition)}
          >
            <option value={OperationalStatus.DAMAGED}>
              {OPERATIONAL_STATUS_LABELS[OperationalStatus.DAMAGED]}
            </option>
            <option value={OperationalStatus.MAINTENANCE}>
              {OPERATIONAL_STATUS_LABELS[OperationalStatus.MAINTENANCE]}
            </option>
          </select>
        </div>
        <div className="field">
          <label htmlFor={`${id}-quantity`}>Quantity</label>
          <input
            id={`${id}-quantity`}
            type="number"
            min="1"
            step="1"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            aria-invalid={error !== null}
          />
        </div>
      </div>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="field-hint" role="status">
          {notice}
        </p>
      )}
      <div className="form-actions">
        <button
          type="button"
          className="btn-secondary"
          disabled={busy}
          onClick={() =>
            void submit(markOutOfService, `marked ${OPERATIONAL_STATUS_LABELS[condition]}`)
          }
        >
          Mark out of service
        </button>
        <button
          type="button"
          className="btn-secondary"
          disabled={busy}
          onClick={() => void submit(returnToService, 'returned to service')}
        >
          Return to service
        </button>
      </div>
    </div>
  )
}
