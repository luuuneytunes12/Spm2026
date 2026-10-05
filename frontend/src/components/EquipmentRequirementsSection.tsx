import { useEffect, useId, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError } from '../lib/api'
import { listEquipment } from '../lib/equipment'
import {
  addRequirement,
  canRecordEquipment,
  deleteRequirement,
  listRequirements,
  updateRequirement,
} from '../lib/equipmentRequirements'
import type { EquipmentRequirement } from '../lib/equipmentRequirements'
import { EventStatus } from '../lib/events'
import type { EquipmentLine } from '../lib/events'
import { EquipmentLines } from './EquipmentLines'
import { EquipmentRequirementItem } from './EquipmentRequirementItem'

interface Props {
  eventId: number
  eventStatus: EventStatus
  /** What the Organiser asked for: shown as context, and what a requirement
   *  can be based on. */
  organiserLines: EquipmentLine[]
  /** The Organiser's "Other equipment notes". Context only. */
  organiserNotes: string | null
}

/** One of the Organiser's requests, in the words used to pick and to recall it. */
function describeLine(line: EquipmentLine): string {
  return `${line.equipment_name} × ${line.quantity_requested}`
}

/** Where a requirement came from, for the row and the editor. A link to a
 *  request this page does not have (the page is older than an approved change
 *  that replaced the Organiser's list) is still a link, so it is not shown as
 *  Coordinator-added. Once the page is reloaded the database has cleared such
 *  a link, and the requirement reads as Coordinator-added from then on. */
function originOf(requirement: EquipmentRequirement, organiserLines: EquipmentLine[]): string {
  if (requirement.organiser_equipment_request_id === null) return 'Coordinator-added requirement'
  const line = organiserLines.find((l) => l.id === requirement.organiser_equipment_request_id)
  return line
    ? `Based on organiser equipment request: ${describeLine(line)}`
    : 'Based on an organiser equipment request'
}

/** Statuses before an event is approved: equipment cannot be recorded yet,
 *  but will be, so the card says so rather than just being empty. */
const BEFORE_APPROVAL: EventStatus[] = [
  EventStatus.DRAFT,
  EventStatus.SUBMITTED,
  EventStatus.UNDER_REVIEW,
  EventStatus.CHANGES_REQUESTED,
]

/** The Coordinator's "equipment this event needs" card.
 *
 *  Each requirement is an equipment TYPE (one of the catalogue's categories,
 *  never a specific model: choosing the exact item is Technical Support's
 *  job), a quantity and technical notes -- what Technical Support will
 *  review. Adding one saves it at once, visible to Technical Support.
 *
 *  What the Organiser asked for is shown above, read-only, as planning
 *  context. A requirement can be based on one of those requests, which fills
 *  in its type and quantity and remembers where it came from, or on nothing
 *  at all: the Coordinator may know of a need the Organiser never mentioned.
 *
 *  Whether anything can be changed follows the event's status, using the
 *  same window the server enforces. The server is the real gate; this just
 *  stops the card offering what it will refuse. */
export function EquipmentRequirementsSection({
  eventId,
  eventStatus,
  organiserLines,
  organiserNotes,
}: Props) {
  const editable = canRecordEquipment(eventStatus)

  const [requirements, setRequirements] = useState<EquipmentRequirement[] | null>(null)
  const [loadFailed, setLoadFailed] = useState(false)
  const [types, setTypes] = useState<string[]>([])
  const [typesFailed, setTypesFailed] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<number | null>(null)

  useEffect(() => {
    let cancelled = false
    listRequirements(eventId)
      .then((rows) => {
        if (!cancelled) setRequirements(rows)
      })
      .catch(() => {
        if (cancelled) return
        setRequirements([])
        setLoadFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [eventId])

  useEffect(() => {
    // Only needed to fill a form, so not fetched where nothing can be added.
    if (!editable) return
    let cancelled = false
    listEquipment()
      .then((catalogue) => {
        if (!cancelled) setTypes(catalogue.types)
      })
      .catch(() => {
        if (!cancelled) setTypesFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [editable])

  function reason(err: unknown, fallback: string): string {
    return err instanceof ApiError ? err.message : fallback
  }

  async function remove(requirement: EquipmentRequirement) {
    setError(null)
    try {
      await deleteRequirement(requirement.id)
      setRequirements((current) => current?.filter((r) => r.id !== requirement.id) ?? null)
    } catch (err) {
      setError(reason(err, 'Could not remove this requirement.'))
    }
  }

  return (
    <section className="card stack-tight">
      <h2>Equipment Requirements</h2>

      <OrganiserContext lines={organiserLines} notes={organiserNotes} />

      <h3 className="requirement-subtitle">Coordinator requirements</h3>

      {loadFailed && (
        <p className="form-error" role="alert">
          Could not load the equipment requirements.
        </p>
      )}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      {requirements !== null && requirements.length === 0 && !loadFailed && (
        <p className="text-muted">No Coordinator equipment requirements recorded yet.</p>
      )}

      {requirements !== null && requirements.length > 0 && (
        <ul className="requirement-list" aria-label="Recorded equipment requirements">
          {requirements.map((requirement) =>
            editingId === requirement.id ? (
              <li key={requirement.id} className="requirement requirement-editing">
                <RequirementEditor
                  requirement={requirement}
                  origin={originOf(requirement, organiserLines)}
                  types={types}
                  onCancel={() => setEditingId(null)}
                  onSave={async (changes) => {
                    setError(null)
                    try {
                      const saved = await updateRequirement(requirement.id, changes)
                      setRequirements(
                        (current) => current?.map((r) => (r.id === saved.id ? saved : r)) ?? null,
                      )
                      setEditingId(null)
                    } catch (err) {
                      setError(reason(err, 'Could not save this requirement.'))
                    }
                  }}
                />
              </li>
            ) : (
              <EquipmentRequirementItem
                key={requirement.id}
                category={requirement.category}
                quantity={requirement.quantity_needed}
                notes={requirement.technical_notes}
                status={requirement.status}
                reserved={requirement.reserved_quantity}
                reservations={requirement.reservations}
                origin={originOf(requirement, organiserLines)}
                actions={
                  editable && (
                    <>
                      <button
                        type="button"
                        className="btn-link-muted"
                        aria-label={`Edit ${requirement.category} requirement`}
                        onClick={() => {
                          setError(null)
                          setEditingId(requirement.id)
                        }}
                      >
                        Edit
                      </button>
                      {/* Nothing can release a reservation, so a requirement
                          with equipment reserved is not offered for removal.
                          The server refuses it regardless. */}
                      {requirement.reserved_quantity === 0 && (
                        <button
                          type="button"
                          className="btn-link-muted"
                          aria-label={`Remove ${requirement.category} requirement`}
                          onClick={() => void remove(requirement)}
                        >
                          Remove
                        </button>
                      )}
                    </>
                  )
                }
              />
            ),
          )}
        </ul>
      )}

      {editable ? (
        <AddRequirementForm
          types={types}
          typesFailed={typesFailed}
          organiserLines={organiserLines}
          onAdd={async (input) => {
            setError(null)
            try {
              const added = await addRequirement(eventId, input)
              setRequirements((current) => [...(current ?? []), added])
              return true
            } catch (err) {
              setError(reason(err, 'Could not add this requirement.'))
              return false
            }
          }}
        />
      ) : (
        <p className="field-hint">
          {BEFORE_APPROVAL.includes(eventStatus)
            ? 'Equipment can be recorded once the event is approved.'
            : 'Equipment can no longer be changed for this event.'}
        </p>
      )}
    </section>
  )
}

/** What the Organiser asked for, read-only: the Coordinator plans against it.
 *  Never copied into a requirement -- the Coordinator writes their own. */
function OrganiserContext({ lines, notes }: { lines: EquipmentLine[]; notes: string | null }) {
  const headingId = useId()
  const written = notes?.trim()
  return (
    <section className="requirement-context stack-tight" aria-labelledby={headingId}>
      <h3 id={headingId} className="requirement-subtitle">
        Requested by the Organiser
      </h3>
      <EquipmentLines lines={lines} />
      {written && (
        <div className="requirement-context-notes">
          <span className="requirement-context-label">Other equipment notes</span>
          <p>{written}</p>
        </div>
      )}
      <p className="field-hint">For reference. It is not copied into your requirements.</p>
    </section>
  )
}

interface AddFormProps {
  types: string[]
  typesFailed: boolean
  organiserLines: EquipmentLine[]
  /** Resolves true when the requirement was recorded, so the form can clear. */
  onAdd: (input: {
    category: string
    quantity_needed: number
    technical_notes: string | null
    organiser_equipment_request_id: number | null
  }) => Promise<boolean>
}

function AddRequirementForm({ types, typesFailed, organiserLines, onAdd }: AddFormProps) {
  const ids = useId()
  const [basedOn, setBasedOn] = useState('')
  const [category, setCategory] = useState('')
  const [quantity, setQuantity] = useState('1')
  const [notes, setNotes] = useState('')
  const [problem, setProblem] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  function chooseBasedOn(value: string) {
    setBasedOn(value)
    const pick = organiserLines.find((line) => String(line.id) === value)
    // Type and quantity are what can be derived from a request. Technical
    // notes are the Coordinator's own, so they are left as they are. Filling
    // in is a convenience, never a lock: every field stays editable, and
    // going back to "not based on an organiser request" keeps what was typed.
    if (!pick) return
    setCategory(pick.equipment_category ?? '')
    setQuantity(String(pick.quantity_requested))
    setProblem(null)
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!category) {
      setProblem('Choose an equipment type.')
      return
    }
    const needed = Number(quantity)
    if (!Number.isInteger(needed) || needed < 1) {
      setProblem('Quantity must be at least 1.')
      return
    }
    setProblem(null)
    setBusy(true)
    const recorded = await onAdd({
      category,
      quantity_needed: needed,
      technical_notes: notes.trim() || null,
      organiser_equipment_request_id: basedOn ? Number(basedOn) : null,
    })
    setBusy(false)
    if (recorded) {
      setBasedOn('')
      setCategory('')
      setQuantity('1')
      setNotes('')
    }
  }

  return (
    <form onSubmit={submit} noValidate className="requirement-form stack-tight">
      {/* Headed, because while a row is being edited this and the editor are
          on screen together with the same labels -- without a title the two
          forms are indistinguishable. */}
      <h3 className="requirement-form-title">Add a requirement</h3>
      {organiserLines.length > 0 && (
        <div className="field">
          <label htmlFor={`${ids}-based`}>Based on organiser equipment request (optional)</label>
          <select id={`${ids}-based`} value={basedOn} onChange={(e) => chooseBasedOn(e.target.value)}>
            <option value="">Not based on an organiser request</option>
            {organiserLines.map((line) => (
              <option key={line.id} value={line.id}>
                {describeLine(line)}
              </option>
            ))}
          </select>
        </div>
      )}

      <div className="form-row">
        <div className={problem?.startsWith('Choose') ? 'field field-invalid' : 'field'}>
          <label htmlFor={`${ids}-type`}>Equipment type</label>
          <select
            id={`${ids}-type`}
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            aria-invalid={problem?.startsWith('Choose') ? true : undefined}
          >
            <option value="">Choose a type</option>
            {types.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
          {typesFailed && (
            <p className="field-hint">Could not load the equipment types. Reload to try again.</p>
          )}
        </div>
        <div className={problem?.startsWith('Quantity') ? 'field field-invalid' : 'field'}>
          <label htmlFor={`${ids}-qty`}>Quantity needed</label>
          <input
            id={`${ids}-qty`}
            type="number"
            min={1}
            inputMode="numeric"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            aria-invalid={problem?.startsWith('Quantity') ? true : undefined}
          />
        </div>
      </div>

      <div className="field">
        <label htmlFor={`${ids}-notes`}>Technical notes</label>
        <textarea
          id={`${ids}-notes`}
          rows={2}
          placeholder="Anything Technical Support should know -- model, connectors, setup"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </div>

      {problem && <p className="field-error">{problem}</p>}

      <p className="field-hint">Once added, this requirement will be visible to Technical Support.</p>

      <div className="form-actions">
        <button type="submit" className="btn-secondary" disabled={busy}>
          Add requirement
        </button>
      </div>
    </form>
  )
}

interface EditorProps {
  requirement: EquipmentRequirement
  /** Where it came from. Shown, never editable: it is a fact about the
   *  requirement, not a field. */
  origin: string
  types: string[]
  onCancel: () => void
  onSave: (changes: {
    category: string
    quantity_needed: number
    technical_notes: string | null
  }) => Promise<void>
}

function RequirementEditor({ requirement, origin, types, onCancel, onSave }: EditorProps) {
  const ids = useId()
  // Equipment reserved for it cannot be given back, so the type it was
  // reserved as is fixed and the quantity cannot drop below what is held.
  const reserved = requirement.reserved_quantity
  const [category, setCategory] = useState(requirement.category)
  const [quantity, setQuantity] = useState(String(requirement.quantity_needed))
  const [notes, setNotes] = useState(requirement.technical_notes ?? '')
  const [problem, setProblem] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // A category the catalogue no longer lists (or one still loading) must not
  // vanish from its own editor.
  const options = types.includes(category) ? types : [category, ...types]

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
    setProblem(null)
    setBusy(true)
    await onSave({ category, quantity_needed: needed, technical_notes: notes.trim() || null })
    setBusy(false)
  }

  return (
    <form onSubmit={submit} noValidate>
      <fieldset className="field-group requirement-editor">
        <legend className="visually-hidden">{`Edit ${requirement.category} requirement`}</legend>
        <p className="requirement-origin">{origin}</p>
        <div className="form-row">
          <div className="field">
            <label htmlFor={`${ids}-type`}>Equipment type</label>
            <select
              id={`${ids}-type`}
              value={category}
              disabled={reserved > 0}
              onChange={(e) => setCategory(e.target.value)}
            >
              {options.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
            {reserved > 0 && (
              <p className="field-hint">
                Equipment is reserved for this requirement, so its type cannot be changed.
              </p>
            )}
          </div>
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
              <p className="field-hint">The quantity cannot go below the {reserved} reserved.</p>
            )}
          </div>
        </div>
        <div className="field">
          <label htmlFor={`${ids}-notes`}>Technical notes</label>
          <textarea
            id={`${ids}-notes`}
            rows={2}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </div>
        {problem && <p className="field-error">{problem}</p>}
        <div className="form-actions">
          <button type="submit" className="btn-secondary" disabled={busy}>
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
