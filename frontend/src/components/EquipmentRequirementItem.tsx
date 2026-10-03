import type { ReactNode } from 'react'
import { progressText, requirementStatusLabel } from '../lib/equipmentRequirements'
import type { ReservedItem } from '../lib/equipmentRequirements'

interface Props {
  category: string
  quantity: number
  notes: string | null
  status: string
  /** How much of `quantity` is reserved, and in which items. Both sides show
   *  the same figures, so a Coordinator and Technical Support never read a
   *  different state of the same requirement. */
  reserved?: number
  reservations?: ReservedItem[]
  /** Where the requirement came from. Only the Coordinator's card passes it;
   *  Technical Support is shown what is needed, not what it was based on. */
  origin?: string
  /** Buttons for whoever may act on the row. Technical Support's record
   *  passes none; the Coordinator's card passes Edit and Remove. */
  actions?: ReactNode
  /** A panel opened on this row, shown beneath it. */
  panel?: ReactNode
}

/** One equipment requirement as a row: type, quantity, notes and status.
 *
 *  Shared by the Coordinator's card and Technical Support's event record, so
 *  the two read identically -- what the Coordinator wrote is exactly what
 *  Technical Support is shown -- and differ only in what they may do to it,
 *  which is the `actions` slot. */
export function EquipmentRequirementItem({
  category,
  quantity,
  notes,
  status,
  reserved = 0,
  reservations = [],
  origin,
  actions,
  panel,
}: Props) {
  const progress = progressText(reserved, quantity)
  return (
    <li className="requirement">
      <div className="requirement-main">
        <span className="requirement-title">{category}</span>
        {notes && <span className="request-meta">{notes}</span>}
        {progress && <span className="requirement-progress">{progress}</span>}
        {reservations.length > 0 && (
          <span className="request-meta">
            {reservations.map((item) => `${item.quantity} \u00d7 ${item.equipment_name}`).join(', ')}
          </span>
        )}
        {origin && <span className="requirement-origin">{origin}</span>}
      </div>
      <div className="requirement-side">
        {/* Quantity as a chip so it reads as a number against the type
            rather than running into it as prose. */}
        <span className="chip">&times; {quantity}</span>
        <span className="badge badge-muted">{requirementStatusLabel(status)}</span>
        {actions}
      </div>
      {panel}
    </li>
  )
}
