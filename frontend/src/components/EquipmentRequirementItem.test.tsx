/**
 * Component tests for the shared requirement row.
 *
 * Traceability (see docs/test-cases-equipment-requirement-status.md):
 *   UR AC1  the status of each requirement, so the Coordinator can track
 *           progress: Requested / In review / Unavailable while nothing is
 *           reserved, "In progress — 3 of 5 reserved", "Reserved — 5 of 5"
 *   UR AC3  the updated status and quantity visible to the Coordinator
 *
 * The row is shared by the Coordinator's card and Technical Support's
 * record, so the two read the same words. What is reserved comes from the
 * server; the row only shows it.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { EquipmentRequirementItem } from './EquipmentRequirementItem'

function renderRow(props: Partial<React.ComponentProps<typeof EquipmentRequirementItem>> = {}) {
  return render(
    <ul>
      <EquipmentRequirementItem
        category="Audio"
        quantity={5}
        notes={null}
        status="requested"
        {...props}
      />
    </ul>,
  )
}

describe('a requirement with nothing reserved', () => {
  it('shows what is needed and the status it was given', () => {
    renderRow()

    expect(screen.getByText('Audio')).toBeInTheDocument()
    expect(screen.getByText(/× 5/)).toBeInTheDocument()
    expect(screen.getByText('Requested')).toBeInTheDocument()
    expect(screen.queryByText(/reserved/i)).not.toBeInTheDocument()
  })

  it('reads In review for a requirement under review', () => {
    renderRow({ status: 'reviewing' })

    expect(screen.getByText('In review')).toBeInTheDocument()
  })

  it('shows rejected as Unavailable', () => {
    renderRow({ status: 'rejected' })

    expect(screen.getByText('Unavailable')).toBeInTheDocument()
    expect(screen.queryByText('Rejected')).not.toBeInTheDocument()
  })
})

describe('a requirement with some of it reserved', () => {
  const PART = {
    status: 'reviewing',
    reserved: 3,
    reservations: [{ equipment_id: 11, equipment_name: 'Shure BLX24', quantity: 3 }],
  }

  it('reads In progress, with how far it has got', () => {
    renderRow(PART)

    expect(screen.getByText('In progress — 3 of 5 reserved')).toBeInTheDocument()
  })

  it('keeps what is needed distinct from what is reserved', () => {
    renderRow(PART)

    expect(screen.getByText(/× 5/)).toBeInTheDocument() // still needed: 5
    // The progress is said once, in the status, not again beside it.
    expect(screen.getAllByText(/3 of 5 reserved/)).toHaveLength(1)
  })

  it('names what is reserved, item by item', () => {
    renderRow({
      status: 'reviewing',
      reserved: 4,
      reservations: [
        { equipment_id: 11, equipment_name: 'Shure BLX24', quantity: 3 },
        { equipment_id: 12, equipment_name: 'Yamaha PA', quantity: 1 },
      ],
    })

    const row = screen.getByRole('listitem')
    expect(row).toHaveTextContent('3 × Shure BLX24')
    expect(row).toHaveTextContent('1 × Yamaha PA')
  })

  it('does not call it In review: the reservations say more than the label', () => {
    renderRow(PART)

    expect(screen.queryByText('In review')).not.toBeInTheDocument()
  })
})

describe('a fully reserved requirement', () => {
  it('reads Reserved, with the whole of it accounted for', () => {
    renderRow({
      status: 'reserved',
      reserved: 5,
      reservations: [{ equipment_id: 11, equipment_name: 'Shure BLX24', quantity: 5 }],
    })

    expect(screen.getByText('Reserved — 5 of 5')).toBeInTheDocument()
  })
})

describe('a row from an older response', () => {
  it('still renders when progress is not given', () => {
    renderRow({ reserved: undefined, reservations: undefined })

    expect(screen.getByText('Audio')).toBeInTheDocument()
    expect(screen.getByText('Requested')).toBeInTheDocument()
  })
})

describe('a panel opened on the row', () => {
  it('is shown beneath it', () => {
    renderRow({ panel: <p>the panel</p> })

    expect(screen.getByRole('listitem')).toHaveTextContent('the panel')
  })
})
