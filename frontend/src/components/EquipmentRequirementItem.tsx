import type { ReactNode } from 'react'
import { requirementStatusLabel } from '../lib/equipmentRequirements'

interface Props {
  category: string
  quantity: number
  notes: string | null
  status: string
  /** Where the requirement came from. Only the Coordinator's card passes it;
   *  Technical Support is shown what is needed, not what it was based on. */
  origin?: string
  /** Buttons for whoever may act on the row. Technical Support's record
   *  passes none; the Coordinator's card passes Edit and Remove. */
  actions?: ReactNode
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
  origin,
  actions,
}: Props) {
  return (
    <li className="requirement">
      <div className="requirement-main">
        <span className="requirement-title">{category}</span>
        {notes && <span className="request-meta">{notes}</span>}
        {origin && <span className="requirement-origin">{origin}</span>}
      </div>
      <div className="requirement-side">
        {/* Quantity as a chip so it reads as a number against the type
            rather than running into it as prose. */}
        <span className="chip">&times; {quantity}</span>
        <span className="badge badge-muted">{requirementStatusLabel(status)}</span>
        {actions}
      </div>
    </li>
  )
}
