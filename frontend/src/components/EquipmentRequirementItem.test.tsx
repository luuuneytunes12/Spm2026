/**
 * Component tests for the shared requirement row.
 *
 * Traceability (see docs/test-cases-equipment-requirement-status.md):
 *   UR AC1  the status of each requirement, so the Coordinator can track
 *           progress: Requested / Unavailable (with its reason) while nothing
 *           is reserved, "Requested — 3 of 5 reserved" while only part is,
 *           "Reserved — 5 of 5", and Available once the reservation is freed
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

  it('has no In review: it is not a status', () => {
    renderRow()

    expect(screen.queryByText('In review')).not.toBeInTheDocument()
  })
})

describe('an Unavailable requirement', () => {
  it('reads Unavailable, with the reason Technical Support gave', () => {
    renderRow({ status: 'unavailable', unavailableReason: 'Mics are being repaired' })

    expect(screen.getByText('Unavailable')).toBeInTheDocument()
    expect(screen.getByRole('listitem')).toHaveTextContent('Reason: Mics are being repaired')
  })

  it('does not invent a reason when there is none on record', () => {
    renderRow({ status: 'unavailable', unavailableReason: null })

    expect(screen.getByText('Unavailable')).toBeInTheDocument()
    expect(screen.queryByText(/Reason:/)).not.toBeInTheDocument()
  })

  it('shows no reason on a requirement that is not Unavailable', () => {
    renderRow({ status: 'requested', unavailableReason: 'left over' })

    expect(screen.queryByText(/Reason:/)).not.toBeInTheDocument()
  })
})

describe('a requirement with some of it reserved', () => {
  const PART = {
    status: 'requested',
    reserved: 3,
    reservations: [
      { equipment_id: 11, equipment_name: 'Shure BLX24', quantity: 3, placement_notes: null },
    ],
  }

  it('is still Requested, with how far it has got', () => {
    renderRow(PART)

    expect(screen.getByText('Requested — 3 of 5 reserved')).toBeInTheDocument()
  })

  it('keeps what is needed distinct from what is reserved', () => {
    renderRow(PART)

    expect(screen.getByText(/× 5/)).toBeInTheDocument() // still needed: 5
    // The progress is said once, in the status, not again beside it.
    expect(screen.getAllByText(/3 of 5 reserved/)).toHaveLength(1)
  })

  it('names what is reserved, item by item', () => {
    renderRow({
      status: 'requested',
      reserved: 4,
      reservations: [
        { equipment_id: 11, equipment_name: 'Shure BLX24', quantity: 3, placement_notes: null },
        { equipment_id: 12, equipment_name: 'Yamaha PA', quantity: 1, placement_notes: null },
      ],
    })

    const row = screen.getByRole('listitem')
    expect(row).toHaveTextContent('3 × Shure BLX24')
    expect(row).toHaveTextContent('1 × Yamaha PA')
  })

  it('says where an item will be placed, when that was recorded', () => {
    renderRow({
      status: 'requested',
      reserved: 4,
      reservations: [
        { equipment_id: 11, equipment_name: 'Shure BLX24', quantity: 3, placement_notes: 'Stage left' },
        { equipment_id: 12, equipment_name: 'Yamaha PA', quantity: 1, placement_notes: null },
      ],
    })

    const row = screen.getByRole('listitem')
    expect(row).toHaveTextContent('3 × Shure BLX24 (placed: Stage left)')
    expect(row).toHaveTextContent('1 × Yamaha PA')
    expect(row).not.toHaveTextContent('Yamaha PA (placed')
  })
})

describe('a fully reserved requirement', () => {
  it('reads Reserved, with the whole of it accounted for', () => {
    renderRow({
      status: 'reserved',
      reserved: 5,
      reservations: [
        { equipment_id: 11, equipment_name: 'Shure BLX24', quantity: 5, placement_notes: null },
      ],
    })

    expect(screen.getByText('Reserved — 5 of 5')).toBeInTheDocument()
  })
})

describe('a requirement whose reservation was freed', () => {
  it('reads Available, with how much was freed', () => {
    renderRow({
      status: 'available',
      reserved: 0,
      released: 3,
      reservations: [
        { equipment_id: 11, equipment_name: 'Shure BLX24', quantity: 3, placement_notes: null },
      ],
    })

    expect(screen.getByText('Available — 3 freed')).toBeInTheDocument()
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
