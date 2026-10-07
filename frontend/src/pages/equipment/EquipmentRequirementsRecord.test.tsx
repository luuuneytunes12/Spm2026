/**
 * Component tests for Technical Support's event record.
 *
 * Traceability (see docs/test-cases-equipment-requirements.md):
 *   ER AC2  requirements are visible to Technical Support Staff from the
 *           event record
 *   UR AC1  Technical Support manages each requirement from the record, in
 *           one panel: mark its status, or reserve equipment for it
 *   UR AC2  ... and update its quantity
 *
 * Which events can be opened, and what a requirement carries, are the
 * backend's rules (backend/tests/test_equipment_requirements.py). These
 * tests cover what the screen does with the answer, including the refusal.
 */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/api'
import { EquipmentRequirementsRecord } from './EquipmentRequirementsRecord'

vi.mock('../../lib/equipmentRequirements', async () => {
  const actual = await vi.importActual<typeof import('../../lib/equipmentRequirements')>(
    '../../lib/equipmentRequirements',
  )
  return { ...actual, getSupportEvent: vi.fn(), listSupportEvents: vi.fn() }
})

// The panel has its own tests. Here it is a stand-in, so these tests cover
// only what the PAGE does: which requirement and event it is given, when it is
// shown, and what the page does with what it reports.
vi.mock('../../components/RequirementManagePanel', () => ({
  RequirementManagePanel: ({
    requirement,
    event,
    onChanged,
    onClose,
  }: {
    requirement: SupportRequirement
    event: { id: number; proposed_start: string | null; proposed_end: string | null }
    onChanged: (updated: SupportRequirement) => void
    onClose: () => void
  }) => (
    <div role="region" aria-label="Manage panel">
      manage panel: {requirement.category} for event {event.id} ({event.proposed_start})
      <button
        onClick={() =>
          onChanged({
            ...requirement,
            status: 'reviewing',
            reserved_quantity: 3,
            reservations: [{ equipment_id: 11, equipment_name: 'Shure BLX24', quantity: 3 }],
          })
        }
      >
        stub part reserved
      </button>
      <button
        onClick={() =>
          onChanged({
            ...requirement,
            status: 'reserved',
            reserved_quantity: requirement.quantity_needed,
            reservations: [
              { equipment_id: 11, equipment_name: 'Shure BLX24', quantity: requirement.quantity_needed },
            ],
          })
        }
      >
        stub fully reserved
      </button>
      <button onClick={() => onChanged({ ...requirement, status: 'rejected', quantity_needed: 9 })}>
        stub saved
      </button>
      <button onClick={onClose}>stub close</button>
    </div>
  ),
}))

import { getSupportEvent } from '../../lib/equipmentRequirements'
import type { SupportEventRecord, SupportRequirement } from '../../lib/equipmentRequirements'

const mockGet = vi.mocked(getSupportEvent)

const RECORD: SupportEventRecord = {
  id: 7,
  name: 'Regional Partner Conference',
  event_type: 'conference',
  proposed_start: '2026-11-02T09:00:00Z',
  proposed_end: '2026-11-02T17:00:00Z',
  expected_attendance: 120,
  venue_requirements: 'Main hall, stage, podium',
  status: 'event_approved',
  coordinator: { id: 2, name: 'Sam Tan', email: 'sam@connectsphere.test' },
  requirements: [
    {
      id: 1,
      category: 'Audio',
      quantity_needed: 6,
      technical_notes: 'Handheld wireless, for panel Q&A',
      status: 'requested',
      reserved_quantity: 0,
      reservations: [],
    },
    {
      id: 2,
      category: 'Projection',
      quantity_needed: 2,
      technical_notes: null,
      status: 'requested',
      reserved_quantity: 0,
      reservations: [],
    },
  ],
}

function renderPage(id = '7') {
  return render(
    <MemoryRouter initialEntries={[`/equipment-requirements/${id}`]}>
      <Routes>
        <Route path="/equipment-requirements/:eventId" element={<EquipmentRequirementsRecord />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockGet.mockResolvedValue(RECORD)
})

describe('ER AC2 - the event record', () => {
  it('asks for the event named in the address', async () => {
    renderPage('7')

    await screen.findByRole('heading', { name: 'Regional Partner Conference' })
    expect(mockGet).toHaveBeenCalledWith(7)
  })

  it('shows what the event is, so the equipment can be judged against it', async () => {
    renderPage()

    await screen.findByRole('heading', { name: 'Regional Partner Conference' })
    for (const [label, value] of [
      ['Expected attendance', '120'],
      ['Venue requirements', 'Main hall, stage, podium'],
      ['Event type', 'conference'],
    ]) {
      expect(screen.getByText(label).parentElement).toHaveTextContent(value)
    }
    expect(screen.getByText('Event Approved')).toBeInTheDocument()
  })

  it('names the Coordinator to ask about it', async () => {
    renderPage()

    await screen.findByRole('heading', { name: 'Regional Partner Conference' })
    expect(screen.getByText('Event Coordinator').parentElement).toHaveTextContent('Sam Tan')
    expect(screen.getByText('Event Coordinator').parentElement).toHaveTextContent(
      'sam@connectsphere.test',
    )
  })

  it('says so when no Coordinator is assigned, rather than leaving a blank', async () => {
    mockGet.mockResolvedValue({ ...RECORD, coordinator: null })
    renderPage()

    await screen.findByRole('heading', { name: 'Regional Partner Conference' })
    expect(screen.getByText('Event Coordinator').parentElement).toHaveTextContent('Not assigned')
  })

  it('marks a detail the Organiser never gave rather than rendering a blank row', async () => {
    mockGet.mockResolvedValue({ ...RECORD, venue_requirements: null })
    renderPage()

    await screen.findByRole('heading', { name: 'Regional Partner Conference' })
    expect(screen.getByText('Venue requirements').parentElement).toHaveTextContent('Not provided')
  })

  it('shows each requirement with its type, quantity, notes and status', async () => {
    renderPage()

    const list = await screen.findByRole('list', { name: 'Equipment requirements' })
    const audio = within(list).getByText('Audio').closest('li')!
    expect(within(audio).getByText(/6/)).toBeInTheDocument()
    expect(within(audio).getByText('Handheld wireless, for panel Q&A')).toBeInTheDocument()
    expect(within(audio).getByText('Requested')).toBeInTheDocument()
    expect(within(list).getByText('Projection')).toBeInTheDocument()
  })

  it('says so when nothing has been recorded yet', async () => {
    mockGet.mockResolvedValue({ ...RECORD, requirements: [] })
    renderPage()

    expect(await screen.findByText('No equipment recorded yet.')).toBeInTheDocument()
  })

  it('links back to the list', async () => {
    renderPage()

    const link = await screen.findByRole('link', { name: /equipment requirements/i })
    expect(link).toHaveAttribute('href', '/equipment-requirements')
  })

  it('shows how far a requirement has got, and what is reserved for it', async () => {
    mockGet.mockResolvedValue({
      ...RECORD,
      requirements: [
        {
          ...RECORD.requirements[0],
          status: 'reviewing',
          reserved_quantity: 3,
          reservations: [{ equipment_id: 11, equipment_name: 'Shure BLX24', quantity: 3 }],
        },
      ],
    })
    renderPage()

    const row = (await screen.findByText('Audio')).closest('li')!
    expect(within(row).getByText('In progress — 3 of 6 reserved')).toBeInTheDocument()
    expect(row).toHaveTextContent('3 × Shure BLX24')
  })

  it('shows an Unavailable requirement as Unavailable', async () => {
    mockGet.mockResolvedValue({
      ...RECORD,
      requirements: [{ ...RECORD.requirements[0], status: 'rejected' }],
    })
    renderPage()

    expect(await screen.findByText('Unavailable')).toBeInTheDocument()
  })
})

describe('managing a requirement from the record', () => {
  async function openRecord() {
    renderPage()
    await screen.findByRole('heading', { name: 'Regional Partner Conference' })
  }

  const rowOf = (category: string) =>
    screen.getAllByRole('listitem').find((li) => li.textContent?.includes(category))!

  it('offers one Manage action on each requirement, and nothing else to press', async () => {
    await openRecord()

    for (const category of ['Audio', 'Projection']) {
      expect(screen.getByRole('button', { name: `Manage ${category} requirement` })).toBeInTheDocument()
    }
    expect(screen.getAllByRole('button')).toHaveLength(2)
  })

  it('does not split it into separate Reserve equipment and Update actions', async () => {
    await openRecord()

    expect(screen.queryByRole('button', { name: /reserve equipment/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^update/i })).not.toBeInTheDocument()
  })

  it('offers no action where there is no requirement', async () => {
    mockGet.mockResolvedValue({ ...RECORD, requirements: [] })
    renderPage()
    await screen.findByText('No equipment recorded yet.')

    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('opens the panel with this requirement and this event already filled in', async () => {
    const user = userEvent.setup()
    await openRecord()

    await user.click(screen.getByRole('button', { name: 'Manage Audio requirement' }))

    const panel = screen.getByRole('region', { name: 'Manage panel' })
    expect(panel).toHaveTextContent('Audio for event 7')
    expect(panel).toHaveTextContent('2026-11-02T09:00:00Z') // the event's own date and time
  })

  it('shows the panel under the requirement it belongs to', async () => {
    const user = userEvent.setup()
    await openRecord()

    await user.click(screen.getByRole('button', { name: 'Manage Projection requirement' }))

    expect(within(rowOf('Projection')).getByRole('region', { name: 'Manage panel' })).toBeInTheDocument()
    expect(within(rowOf('Audio')).queryByRole('region', { name: 'Manage panel' })).not.toBeInTheDocument()
  })

  it('shows In progress as soon as part of it is reserved', async () => {
    const user = userEvent.setup()
    await openRecord()
    await user.click(screen.getByRole('button', { name: 'Manage Audio requirement' }))

    await user.click(screen.getByRole('button', { name: 'stub part reserved' }))

    expect(within(rowOf('Audio')).getByText('In progress — 3 of 6 reserved')).toBeInTheDocument()
  })

  it('shows Reserved as soon as all of it is', async () => {
    const user = userEvent.setup()
    await openRecord()
    await user.click(screen.getByRole('button', { name: 'Manage Audio requirement' }))

    await user.click(screen.getByRole('button', { name: 'stub fully reserved' }))

    expect(within(rowOf('Audio')).getByText('Reserved — 6 of 6')).toBeInTheDocument()
  })

  it('shows a saved status and quantity straight away', async () => {
    const user = userEvent.setup()
    await openRecord()
    await user.click(screen.getByRole('button', { name: 'Manage Audio requirement' }))

    await user.click(screen.getByRole('button', { name: 'stub saved' }))

    const row = rowOf('Audio')
    expect(within(row).getByText('Unavailable')).toBeInTheDocument()
    expect(within(row).getByText(/× 9/)).toBeInTheDocument()
  })

  it('keeps the panel open after a change, so the work can go on', async () => {
    const user = userEvent.setup()
    await openRecord()
    await user.click(screen.getByRole('button', { name: 'Manage Audio requirement' }))

    await user.click(screen.getByRole('button', { name: 'stub part reserved' }))

    expect(screen.getByRole('region', { name: 'Manage panel' })).toBeInTheDocument()
  })

  it('closes the panel without changing the row', async () => {
    const user = userEvent.setup()
    await openRecord()
    await user.click(screen.getByRole('button', { name: 'Manage Audio requirement' }))

    await user.click(screen.getByRole('button', { name: 'stub close' }))

    expect(screen.queryByRole('region', { name: 'Manage panel' })).not.toBeInTheDocument()
    expect(screen.getAllByText('Requested')).toHaveLength(2)
  })

  it('closes the panel when Manage is pressed again, and says whether it is open', async () => {
    const user = userEvent.setup()
    await openRecord()
    const manage = screen.getByRole('button', { name: 'Manage Audio requirement' })
    expect(manage).toHaveAttribute('aria-expanded', 'false')

    await user.click(manage)
    expect(manage).toHaveAttribute('aria-expanded', 'true')
    await user.click(manage)

    expect(screen.queryByRole('region', { name: 'Manage panel' })).not.toBeInTheDocument()
    expect(manage).toHaveAttribute('aria-expanded', 'false')
  })

  it('has one panel open at a time', async () => {
    const user = userEvent.setup()
    await openRecord()
    await user.click(screen.getByRole('button', { name: 'Manage Audio requirement' }))

    await user.click(screen.getByRole('button', { name: 'Manage Projection requirement' }))

    expect(screen.getAllByRole('region', { name: 'Manage panel' })).toHaveLength(1)
    expect(within(rowOf('Projection')).getByRole('region', { name: 'Manage panel' })).toBeInTheDocument()
  })

  it('offers no way to release a reservation: nothing can', async () => {
    mockGet.mockResolvedValue({
      ...RECORD,
      requirements: [
        {
          ...RECORD.requirements[0],
          status: 'reserved',
          reserved_quantity: 6,
          reservations: [{ equipment_id: 11, equipment_name: 'Shure BLX24', quantity: 6 }],
        },
      ],
    })
    renderPage()
    await screen.findByText('Audio')

    expect(
      screen.queryByRole('button', { name: /release|unreserve|cancel reservation|undo/i }),
    ).not.toBeInTheDocument()
  })
})

describe('an event that cannot be shown', () => {
  it('says so for an event that does not exist or is not yet approved', async () => {
    mockGet.mockRejectedValue(new ApiError(404, 'Event not found'))
    renderPage('999')

    expect(await screen.findByRole('alert')).toHaveTextContent('Event not found')
    expect(screen.queryByRole('list', { name: 'Equipment requirements' })).not.toBeInTheDocument()
  })

  it('still offers a way back from an event that is not found', async () => {
    mockGet.mockRejectedValue(new ApiError(404, 'Event not found'))
    renderPage('999')

    await screen.findByRole('alert')
    expect(screen.getByRole('link', { name: /equipment requirements/i })).toHaveAttribute(
      'href',
      '/equipment-requirements',
    )
  })

  it('says something useful when the server cannot be reached', async () => {
    mockGet.mockRejectedValue(new Error('network down'))
    renderPage()

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not/i)
  })
})
