import type { EquipmentLine } from '../lib/events'

/**
 * The equipment an event asked for, read-only.
 *
 * Shared by the Organiser's own view of a submitted request and the
 * Coordinator's assigned-event screen, so the two cannot drift apart —
 * both are looking at the same facts, and a Coordinator planning an event
 * should see exactly what the Organiser believes they asked for.
 *
 * Not rendered through the surrounding `.detail-list`, which pairs a label
 * with a single string. A line is three things (item, type, quantity) plus
 * an optional note, and flattening that to "Shure BLX24 x 6, Epson x 2"
 * would undo the point of structuring it.
 */
export function EquipmentLines({ lines }: { lines: EquipmentLine[] }) {
  if (lines.length === 0) {
    return <span className="text-muted">No equipment requested.</span>
  }

  return (
    <ul className="equipment-request-list">
      {lines.map((line) => (
        <li key={line.id} className="equipment-request">
          <span className="equipment-request-main">
            <span className="equipment-request-name">{line.equipment_name}</span>
            {line.equipment_category && (
              <span className="request-meta">{line.equipment_category}</span>
            )}
            {line.technical_requirements && (
              <span className="request-meta">{line.technical_requirements}</span>
            )}
          </span>
          {/* Quantity as a chip so it reads as a number against the name
              rather than running into it as prose. */}
          <span className="chip">&times; {line.quantity_requested}</span>
        </li>
      ))}
    </ul>
  )
}
