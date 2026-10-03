/**
 * Component tests for the shared requirement row.
 *
 * Traceability (see docs/test-cases-equipment-requirements.md):
 *   UR AC1  the status of each requirement, so the Coordinator can track
 *           progress ("Reviewing", "3 of 5 reserved", "Unavailable")
 *   UR AC3  the updated status and quantity visible to the Coordinator
 *
 * The row is shared by the Coordinator's card and Technical Support's
 * record, so the two read the same figures. What is reserved comes from the
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
  it('shows what is needed and its status, with no progress', () => {
    renderRow()

    expect(screen.getByText('Audio')).toBeInTheDocument()
    expect(screen.getByText(/5/)).toBeInTheDocument()
    expect(screen.getByText('Requested')).toBeInTheDocument()
    expect(screen.queryByText(/reserved/i)).not.toBeInTheDocument()
  })

  it('shows rejected as Unavailable', () => {
    renderRow({ status: 'rejected' })

    expect(screen.getByText('Unavailable')).toBeInTheDocument()
    expect(screen.queryByText('Rejected')).not.toBeInTheDocument()
  })
})

describe('a requirement with some of it reserved', () => {
  it('shows how far it has got, and keeps what is needed distinct', () => {
    renderRow({
      status: 'reviewing',
      reserved: 3,
      reservations: [{ equipment_id: 11, equipment_name: 'Shure BLX24', quantity: 3 }],
    })

    expect(screen.getByText('Reviewing')).toBeInTheDocument()
    expect(screen.getByText('3 of 5 reserved')).toBeInTheDocument()
    expect(screen.getByText(/× 5/)).toBeInTheDocument() // still needed: 5
  })

  it('names what is reserved, item by item', () => {
    renderRow({
      status: 'reviewing',
      reserved: 5,
      reservations: [
        { equipment_id: 11, equipment_name: 'Shure BLX24', quantity: 3 },
        { equipment_id: 12, equipment_name: 'Yamaha PA', quantity: 2 },
      ],
    })

    const row = screen.getByRole('listitem')
    expect(row).toHaveTextContent('3 × Shure BLX24')
    expect(row).toHaveTextContent('2 × Yamaha PA')
  })
})

describe('a fully reserved requirement', () => {
  it('reads Reserved, with the whole of it accounted for', () => {
    renderRow({
      status: 'reserved',
      reserved: 5,
      reservations: [{ equipment_id: 11, equipment_name: 'Shure BLX24', quantity: 5 }],
    })

    expect(screen.getByText('Reserved')).toBeInTheDocument()
    expect(screen.getByText('5 of 5 reserved')).toBeInTheDocument()
  })
})

describe('a row from an older response', () => {
  it('still renders when progress is not given', () => {
    renderRow({ reserved: undefined, reservations: undefined })

    expect(screen.getByText('Audio')).toBeInTheDocument()
  })
})
