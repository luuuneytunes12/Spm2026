import { useEffect, useId, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError } from '../lib/api'
import { listEquipment } from '../lib/equipment'
import type { EquipmentItem } from '../lib/equipment'
import { checkAvailability, listReservableEvents } from '../lib/equipmentReservations'
import type { EquipmentAvailability, RequiredEquipment } from '../lib/equipmentReservations'
import {
  TECH_SUPPORT_STATUS_OPTIONS,
  requirementStatusText,
  reserveForRequirement,
  updateSupportRequirement,
} from '../lib/equipmentRequirements'
import type { SupportRequirement, SupportRequirementChanges } from '../lib/equipmentRequirements'
import { formatRange } from '../lib/events'

interface Props {
  requirement: SupportRequirement
  /** The event the requirement belongs to. Its date and time are the window
   *  checked, and the one a reservation holds. */
  event: { id: number; proposed_start: string | null; proposed_end: string | null }
  /** Called with the requirement as the server now holds it, after a save or
   *  a reservation. The panel stays open: the work usually goes on. */
  onChanged: (updated: SupportRequirement) => void
  onClose: () => void
}

// A line the Organiser asked for that can still be reserved. Mirrors the
// states the existing reservation will take: once it is reserved (or closed)
// it is no longer fixed at their quantity.
const RESERVABLE_LINE_STATUSES = ['requested', 'reviewing']

function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="detail-row">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  )
}

/** Technical Support's one panel on a requirement: what it is and how far it
 *  has got, the status and quantity they may change, and the choice of exact
 *  equipment with its availability and the reservation.
 *
 *  Managing the request and reserving equipment stay separate in the backend
 *  -- they are different responsibilities, and the reservation is the
 *  existing Equipment Reservations -- but one task to the person doing it, so
 *  they are one panel. The event, the type and the date and time are all
 *  known from the requirement, so none of them is asked for again; what is
 *  left to choose is the exact catalogue item, which is Technical Support's
 *  call, and how many.
 *
 *  The rules are the server's. The panel mirrors them where it can, so
 *  nothing is offered that will be refused, and shows the server's own words
 *  when it refuses anyway. */
export function RequirementManagePanel({ requirement, event, onChanged, onClose }: Props) {
  const ids = useId()
  const needed = requirement.quantity_needed
  const reserved = requirement.reserved_quantity
  const remaining = Math.max(needed - reserved, 0)
  const dated = event.proposed_start !== null && event.proposed_end !== null
  const canReserve = dated && remaining > 0

  // --- the request: status and quantity needed ---
  const settable = TECH_SUPPORT_STATUS_OPTIONS.some((o) => o.value === requirement.status)
  const [status, setStatus] = useState(settable ? requirement.status : 'requested')
  const [neededInput, setNeededInput] = useState(String(needed))
  const [saving, setSaving] = useState(false)
  const [saveProblem, setSaveProblem] = useState<string | null>(null)

  // Once something is reserved the status is whatever the reservations say,
  // so there is no choice to make.
  const statusChanged = reserved === 0 && status !== requirement.status
  const neededChanged = neededInput !== String(needed)

  // --- the reservation: exact equipment, its availability, how many ---
  const [items, setItems] = useState<EquipmentItem[]>([])
  const [asked, setAsked] = useState<RequiredEquipment[]>([])
  const [loadFailed, setLoadFailed] = useState(false)
  const [equipmentId, setEquipmentId] = useState('')
  const [quantity, setQuantity] = useState('')
  const [availability, setAvailability] = useState<EquipmentAvailability | null>(null)
  const [checking, setChecking] = useState(false)
  const [checkProblem, setCheckProblem] = useState<string | null>(null)
  const [reserving, setReserving] = useState(false)
  const [reserveProblem, setReserveProblem] = useState<string | null>(null)

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

  const itemId = equipmentId ? Number(equipmentId) : null

  // Checked as soon as an item is chosen, with the existing availability
  // check and the event's own window -- nothing to press.
  useEffect(() => {
    if (itemId === null || !event.proposed_start || !event.proposed_end) return
    let cancelled = false
    checkAvailability(itemId, event.proposed_start, event.proposed_end, event.id)
      .then((result) => {
        if (cancelled) return
        setAvailability(result)
        setChecking(false)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setCheckProblem(err instanceof ApiError ? err.message : 'Could not check availability.')
        setChecking(false)
      })
    return () => {
      cancelled = true
    }
  }, [itemId, event.id, event.proposed_start, event.proposed_end])

  /** The Organiser's line for this item, if it will be reserved at their
   *  quantity. */
  function fixedLine(id: number): RequiredEquipment | undefined {
    return asked.find((l) => l.equipment_id === id && RESERVABLE_LINE_STATUSES.includes(l.status))
  }

  const item = items.find((i) => i.id === itemId) ?? null
  const fixed = item ? fixedLine(item.id) : undefined
  const toReserve = fixed ? fixed.quantity_requested : Number(quantity)
  const quantityValid = fixed !== undefined || (Number.isInteger(toReserve) && toReserve >= 1)
  const overFills = item !== null && quantityValid && toReserve > remaining
  const notEnoughFree = availability !== null && quantityValid && availability.available_quantity < toReserve
  // Left to the server when the check itself failed: only what is KNOWN to be
  // refused is held back.
  const canPressReserve =
    item !== null && quantityValid && !overFills && !notEnoughFree && !checking && !reserving

  function choose(value: string) {
    setEquipmentId(value)
    setQuantity(String(remaining))
    setAvailability(null)
    setCheckProblem(null)
    setReserveProblem(null)
    setChecking(value !== '')
    setDone(null)
  }

  async function save(e: FormEvent) {
    e.preventDefault()
    const value = Number(neededInput)
    if (!Number.isInteger(value) || value < 1) {
      setSaveProblem('Quantity must be at least 1.')
      return
    }
    if (value < reserved) {
      setSaveProblem(`${reserved} already reserved; the quantity needed cannot be less than that.`)
      return
    }

    const changes: SupportRequirementChanges = {}
    if (statusChanged) changes.status = status
    if (neededChanged) changes.quantity_needed = value

    setSaveProblem(null)
    setDone(null)
    setSaving(true)
    try {
      const saved = await updateSupportRequirement(requirement.id, changes)
      setDone('Changes saved.')
      onChanged(saved)
    } catch (err) {
      setSaveProblem(err instanceof ApiError ? err.message : 'Could not save this requirement.')
    } finally {
      setSaving(false)
    }
  }

  async function reserve() {
    if (!item) return
    setReserveProblem(null)
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
      setChecking(false)
      onChanged(updated)
    } catch (err) {
      setReserveProblem(err instanceof ApiError ? err.message : 'Could not reserve the equipment.')
    } finally {
      setReserving(false)
    }
  }

  return (
    <section className="requirement-panel stack-tight" aria-labelledby={`${ids}-heading`}>
      <h3 id={`${ids}-heading`} className="requirement-subtitle">
        Manage {requirement.category} requirement
      </h3>

      <dl className="detail-list">
        <DetailRow label="Equipment type">{requirement.category}</DetailRow>
        <DetailRow label="Quantity">
          {needed} needed · {reserved} reserved · {remaining} remaining
        </DetailRow>
        <DetailRow label="Status">{requirementStatusText(requirement.status, reserved, needed)}</DetailRow>
        <DetailRow label="Technical notes">
          {requirement.technical_notes ?? <span className="text-muted">None</span>}
        </DetailRow>
        <DetailRow label="Event date and time">
          {formatRange(event.proposed_start, event.proposed_end)}
        </DetailRow>
      </dl>

      {done && (
        <p role="status" aria-label="Result" className="field-hint">
          {done}
        </p>
      )}

      <h4 className="requirement-subtitle">Requirement</h4>
      <form onSubmit={(e) => void save(e)} noValidate className="stack-tight">
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
            <p className="field-hint">The status follows the reservations.</p>
          )}
          <div className={saveProblem ? 'field field-invalid' : 'field'}>
            <label htmlFor={`${ids}-needed`}>Quantity needed</label>
            <input
              id={`${ids}-needed`}
              type="number"
              min={reserved > 0 ? reserved : 1}
              inputMode="numeric"
              value={neededInput}
              onChange={(e) => setNeededInput(e.target.value)}
              aria-invalid={saveProblem ? true : undefined}
            />
            {reserved > 0 && (
              <p className="field-hint">The quantity cannot go below the {reserved} reserved.</p>
            )}
          </div>
        </div>
        {saveProblem && (
          <p className="field-error" role="alert">
            {saveProblem}
          </p>
        )}
        <div className="form-actions">
          <button
            type="submit"
            className="btn-secondary"
            disabled={saving || !(statusChanged || neededChanged)}
          >
            Save changes
          </button>
        </div>
      </form>

      <h4 className="requirement-subtitle">Reserve equipment</h4>
      {!dated ? (
        <p className="text-muted">
          This event has no date and time yet, so equipment cannot be checked or reserved.
        </p>
      ) : remaining === 0 ? (
        <p className="text-muted">This requirement is fully reserved.</p>
      ) : (
        <div className="stack-tight">
          <p className="field-hint">
            Held for the event’s date and time, and freed when it ends. Choose the exact{' '}
            {requirement.category} item to reserve.
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
                    onChange={(e) => {
                      setQuantity(e.target.value)
                      setDone(null)
                    }}
                  />
                </div>
              ))}
          </div>

          {checking && <p className="field-hint">Checking availability…</p>}

          {availability && (
            <div role="status" aria-label="Availability" className="stack-tight">
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
              {quantityValid &&
                (notEnoughFree ? (
                  <p className="form-error">
                    Only {availability.available_quantity} available; {toReserve} to reserve. You can
                    choose another {requirement.category} item.
                  </p>
                ) : (
                  <p>Enough for the {toReserve} to reserve.</p>
                ))}
            </div>
          )}

          {checkProblem && (
            <p className="form-error" role="alert">
              {checkProblem}
            </p>
          )}

          {overFills && (
            <p className="form-error">
              {fixed
                ? `The Organiser asked for ${fixed.quantity_requested}, and a reservation takes that whole quantity; this requirement needs only ${remaining} more.`
                : `This requirement needs only ${remaining} more.`}
            </p>
          )}

          {reserveProblem && (
            <p className="form-error" role="alert">
              {reserveProblem}
            </p>
          )}

          <div className="form-actions">
            <button
              type="button"
              className="btn-primary"
              disabled={!canPressReserve}
              onClick={() => void reserve()}
            >
              {reserving ? 'Reserving…' : 'Reserve'}
            </button>
          </div>
        </div>
      )}

      <div className="form-actions">
        <button type="button" className="btn-link-muted" onClick={onClose}>
          Close
        </button>
      </div>
    </section>
  )
}
