import { useEffect, useId, useState } from 'react'
import { ApiError } from '../lib/api'
import { listEquipment } from '../lib/equipment'
import type { EquipmentItem } from '../lib/equipment'
import { checkAvailability, listReservableEvents } from '../lib/equipmentReservations'
import type { EquipmentAvailability, RequiredEquipment } from '../lib/equipmentReservations'
import { reserveForRequirement } from '../lib/equipmentRequirements'
import type { SupportRequirement } from '../lib/equipmentRequirements'
import { formatRange } from '../lib/events'

interface Props {
  requirement: SupportRequirement
  /** The event the requirement belongs to. Its date and time are the
   *  window checked, and the one a reservation holds. */
  event: { id: number; proposed_start: string | null; proposed_end: string | null }
  /** Called with the requirement as the server now holds it. */
  onReserved: (updated: SupportRequirement) => void
  onClose: () => void
}

// A line the Organiser asked for that can still be reserved. Mirrors the
// states the existing reservation will take: once it is reserved (or closed),
// it is no longer fixed at their quantity.
const RESERVABLE_LINE_STATUSES = ['requested', 'reviewing']

/** Check availability and reserve equipment for one requirement, without
 *  leaving the event record.
 *
 *  The event, the type and the date and time are all known, so only what is
 *  not is asked: which item of that type, and how many. Both the check and
 *  the reservation are the existing Equipment Reservations -- this panel is
 *  a contextual way into them, not a second implementation. Whether the
 *  stock is there is theirs to say, and their words are shown as they come. */
export function RequirementReservePanel({ requirement, event, onReserved, onClose }: Props) {
  const ids = useId()
  const remaining = Math.max(requirement.quantity_needed - requirement.reserved_quantity, 0)
  const dated = event.proposed_start !== null && event.proposed_end !== null
  const canReserve = dated && remaining > 0

  const [items, setItems] = useState<EquipmentItem[]>([])
  const [asked, setAsked] = useState<RequiredEquipment[]>([])
  const [loadFailed, setLoadFailed] = useState(false)

  const [equipmentId, setEquipmentId] = useState('')
  const [quantity, setQuantity] = useState('')
  const [availability, setAvailability] = useState<EquipmentAvailability | null>(null)
  const [checking, setChecking] = useState(false)
  const [reserving, setReserving] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)

  useEffect(() => {
    // Nothing to choose from where nothing can be reserved.
    if (!canReserve) return
    let cancelled = false
    Promise.all([
      listEquipment({ type: requirement.category }),
      // What the Organiser asked for tells which items are reserved at THEIR
      // quantity. If it cannot be read, every item is simply treated as one
      // the quantity is chosen for -- and the server still decides.
      listReservableEvents().catch(() => []),
    ])
      .then(([catalogue, events]) => {
        if (cancelled) return
        setItems(catalogue.items)
        setAsked(events.find((e) => e.id === event.id)?.equipment_items ?? [])
      })
      .catch(() => {
        if (!cancelled) setLoadFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [canReserve, requirement.category, event.id])

  /** The Organiser's line for this item, if it will be reserved at their
   *  quantity. */
  function fixedLine(id: number): RequiredEquipment | undefined {
    return asked.find((l) => l.equipment_id === id && RESERVABLE_LINE_STATUSES.includes(l.status))
  }

  const item = items.find((i) => String(i.id) === equipmentId) ?? null
  const fixed = item ? fixedLine(item.id) : undefined
  const toReserve = fixed ? fixed.quantity_requested : Number(quantity)

  function choose(value: string) {
    setEquipmentId(value)
    setQuantity(String(remaining))
    setAvailability(null)
    setProblem(null)
    setDone(null)
  }

  async function check() {
    setProblem(null)
    setDone(null)
    if (!item || !event.proposed_start || !event.proposed_end) {
      setProblem('Select equipment first.')
      return
    }
    setChecking(true)
    try {
      setAvailability(await checkAvailability(item.id, event.proposed_start, event.proposed_end, event.id))
    } catch (err) {
      setProblem(err instanceof ApiError ? err.message : 'Could not check availability.')
    } finally {
      setChecking(false)
    }
  }

  async function reserve() {
    if (!item) return
    setProblem(null)
    setDone(null)
    setReserving(true)
    try {
      const updated = await reserveForRequirement(
        requirement.id,
        item.id,
        fixed ? undefined : Number(quantity) || undefined,
      )
      const taken = updated.reservations.find((r) => r.equipment_id === item.id)?.quantity
      setDone(`Reserved ${taken ?? toReserve} × ${item.name}.`)
      setEquipmentId('')
      setQuantity('')
      setAvailability(null)
      onReserved(updated)
    } catch (err) {
      setProblem(err instanceof ApiError ? err.message : 'Could not reserve the equipment.')
    } finally {
      setReserving(false)
    }
  }

  return (
    <section className="requirement-panel stack-tight" aria-labelledby={`${ids}-heading`}>
      <h3 id={`${ids}-heading`} className="requirement-subtitle">
        Reserve {requirement.category} equipment
      </h3>
      <p className="field-hint">
        Needs {requirement.quantity_needed}
        {requirement.reserved_quantity > 0 && ` · ${requirement.reserved_quantity} reserved`}
        {remaining > 0 && ` · ${remaining} still to reserve`}
      </p>

      {done && (
        <p role="status" className="field-hint">
          {done}
        </p>
      )}

      {!dated ? (
        <p className="text-muted">
          This event has no date and time yet, so equipment cannot be checked or reserved.
        </p>
      ) : remaining === 0 ? (
        <p className="text-muted">This requirement is fully reserved.</p>
      ) : (
        <>
          <p className="field-hint">
            Held for the event’s date and time, {formatRange(event.proposed_start, event.proposed_end)},
            and freed when it ends.
          </p>

          {loadFailed && (
            <p className="form-error" role="alert">
              Could not load the equipment.
            </p>
          )}

          <div className="form-row">
            <div className="field">
              <label htmlFor={`${ids}-equipment`}>Equipment</label>
              <select
                id={`${ids}-equipment`}
                value={equipmentId}
                onChange={(e) => choose(e.target.value)}
              >
                <option value="">Select equipment…</option>
                {items.map((i) => {
                  const line = fixedLine(i.id)
                  return (
                    <option key={i.id} value={i.id}>
                      {i.name}
                      {line ? ` (the Organiser asked for ${line.quantity_requested})` : ''}
                    </option>
                  )
                })}
              </select>
            </div>
            {item &&
              (fixed ? (
                <p className="field-hint">
                  The Organiser asked for {fixed.quantity_requested}; that quantity will be reserved.
                </p>
              ) : (
                <div className="field">
                  <label htmlFor={`${ids}-qty`}>Quantity to reserve</label>
                  <input
                    id={`${ids}-qty`}
                    type="number"
                    min={1}
                    max={remaining}
                    inputMode="numeric"
                    value={quantity}
                    onChange={(e) => setQuantity(e.target.value)}
                  />
                </div>
              ))}
          </div>

          {availability && (
            <div role="status" className="stack-tight">
              <p>
                <strong>
                  {availability.available_quantity} of {availability.total_quantity}
                </strong>{' '}
                {availability.equipment_name} available for{' '}
                {formatRange(availability.start_time, availability.end_time)}
                {availability.reserved_quantity > 0 &&
                  ` (${availability.reserved_quantity} reserved for overlapping events)`}
                .
              </p>
              {availability.available_quantity >= toReserve ? (
                <p>Enough for the {toReserve} to reserve.</p>
              ) : (
                <p className="form-error">
                  Only {availability.available_quantity} available; {toReserve} to reserve.
                </p>
              )}
            </div>
          )}

          {problem && (
            <p className="form-error" role="alert">
              {problem}
            </p>
          )}

          <div className="form-actions">
            <button type="button" className="btn-secondary" disabled={checking} onClick={() => void check()}>
              {checking ? 'Checking…' : 'Check availability'}
            </button>
            <button
              type="button"
              className="btn-primary"
              disabled={!item || reserving}
              onClick={() => void reserve()}
            >
              {reserving ? 'Reserving…' : 'Reserve'}
            </button>
            <button type="button" className="btn-link-muted" onClick={onClose}>
              Close
            </button>
          </div>
        </>
      )}

      {(!dated || remaining === 0) && (
        <div className="form-actions">
          <button type="button" className="btn-link-muted" onClick={onClose}>
            Close
          </button>
        </div>
      )}
    </section>
  )
}
