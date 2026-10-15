/**
 * Component tests for Technical Support's list of equipment requirements
 * waiting for them.
 *
 * Traceability (see docs/test-cases-view-equipment-requirements.md):
 *   AC1  each Requested requirement is listed with its Event, equipment type,
 *        quantity, date and time -- in the server's order, oldest Event first
 *   AC2  none Requested -> a "No equipment requirements" message
 *   AC3  opening one shows its technical notes and placement, and lets
 *        availability be checked or equipment reserved (the Manage panel)
 *   AC4  only Technical Support (see App.access.test.tsx for the screen guard)
 *
 * Which requirements are listed, and in what order, is the backend's rule,
 * covered by backend/tests/test_requested_requirements_list.py. These tests
 * cover what the page does with the answer. The Manage panel has its own
 * tests; here it is a stub that shows what it was given.
 */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/api'
import { formatRange } from '../../lib/events'
import { EquipmentRequirementsList } from './EquipmentRequirementsList'

vi.mock('../../components/RequirementManagePanel', () => ({
  RequirementManagePanel: ({
    requirement,
    event,
    onChanged,
    onClose,
  }: {
    requirement: RequestedRequirement
    event: { id: number; proposed_start: string | null; proposed_end: string | null }
    onChanged: (updated: RequestedRequirement) => void
    onClose: () => void
  }) => (
    <div role="region" aria-label="Manage panel">
      manage panel: {requirement.category} for event {event.id} ({event.proposed_start}) notes:{' '}
      {requirement.technical_notes ?? 'none'}
      <button
        onClick={() =>
          onChanged({
            ...requirement,
            status: 'requested',
            reserved_quantity: 3,
            reservations: [
              { equipment_id: 11, equipment_name: 'Shure BLX24', quantity: 3, placement_notes: 'Stage left' },
            ],
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
          })
        }
      >
        stub fully reserved
      </button>
      <button onClick={onClose}>stub close</button>
    </div>
  ),
}))

vi.mock('../../lib/equipmentRequirements', async () => {
  const actual = await vi.importActual<typeof import('../../lib/equipmentRequirements')>(
    '../../lib/equipmentRequirements',
  )
  return { ...actual, listRequestedRequirements: vi.fn() }
})

import { listRequestedRequirements } from '../../lib/equipmentRequirements'
import type { RequestedRequirement } from '../../lib/equipmentRequirements'

const mockList = vi.mocked(listRequestedRequirements)

const AUDIO: RequestedRequirement = {
  id: 1,
  category: 'Audio',
  quantity_needed: 6,
  technical_notes: 'Handheld wireless, for panel Q&A',
  status: 'requested',
  reserved_quantity: 0,
  released_quantity: 0,
  unavailable_reason: null,
  reservations: [],
  event: {
    id: 7,
    name: 'Regional Partner Conference',
    proposed_start: '2026-11-02T09:00:00Z',
    proposed_end: '2026-11-02T17:00:00Z',
  },
}

const PROJECTION: RequestedRequirement = {
  ...AUDIO,
  id: 2,
  category: 'Projection',
  quantity_needed: 2,
  technical_notes: null,
  event: {
    id: 9,
    name: 'Robotics Workshop',
    proposed_start: '2026-12-05T09:00:00Z',
    proposed_end: '2026-12-05T12:00:00Z',
  },
}

function renderPage() {
  return render(
    <MemoryRouter>
      <EquipmentRequirementsList />
    </MemoryRouter>,
  )
}

const rowOf = (category: string) => screen.getByText(category).closest('li')!

beforeEach(() => {
  vi.clearAllMocks()
  mockList.mockResolvedValue([AUDIO, PROJECTION])
})

describe('AC1 - the requirements waiting for me', () => {
  it('lists each with its event, equipment type, quantity and date and time', async () => {
    renderPage()

    const row = (await screen.findByText('Audio')).closest('li')!
    expect(within(row).getByText('Regional Partner Conference')).toBeInTheDocument()
    expect(within(row).getByText(/× 6/)).toBeInTheDocument()
    // The same helper the page formats with, so the test holds in any
    // timezone or locale instead of hard-coding one rendering.
    expect(
      within(row).getByText(formatRange(AUDIO.event.proposed_start, AUDIO.event.proposed_end), {
        exact: false,
      }),
    ).toBeInTheDocument()
  })

  it('lists them in the order the server gives: oldest event first', async () => {
    mockList.mockResolvedValue([PROJECTION, AUDIO]) // the server says Workshop first
    renderPage()

    await screen.findByText('Audio')

    const rows = screen.getAllByRole('listitem')
    expect(rows[0]).toHaveTextContent('Projection')
    expect(rows[1]).toHaveTextContent('Audio')
  })

  it('says each is Requested, and how far a part-reserved one has got', async () => {
    mockList.mockResolvedValue([
      { ...AUDIO, reserved_quantity: 2 },
      PROJECTION,
    ])
    renderPage()

    expect(await screen.findByText('Requested — 2 of 6 reserved')).toBeInTheDocument()
    expect(within(rowOf('Projection')).getByText('Requested')).toBeInTheDocument()
  })

  it('shows the technical notes on the row, so it can be judged at a glance', async () => {
    renderPage()

    expect(await screen.findByText('Handheld wireless, for panel Q&A')).toBeInTheDocument()
  })

  it('links each event to its full record', async () => {
    renderPage()

    const link = await screen.findByRole('link', { name: 'Regional Partner Conference' })
    expect(link).toHaveAttribute('href', '/equipment-requirements/7')
  })

  it('says so for an event with no date yet, rather than showing a blank', async () => {
    mockList.mockResolvedValue([
      { ...AUDIO, event: { ...AUDIO.event, proposed_start: null, proposed_end: null } },
    ])
    renderPage()

    expect(await screen.findByText(/No date yet/)).toBeInTheDocument()
  })

  it('labels an event that was never named rather than rendering a blank', async () => {
    mockList.mockResolvedValue([{ ...AUDIO, event: { ...AUDIO.event, name: null } }])
    renderPage()

    expect(await screen.findByText('Untitled event')).toBeInTheDocument()
  })

  it('says so when the list cannot be loaded', async () => {
    mockList.mockRejectedValue(new ApiError(500, 'Server error'))
    renderPage()

    expect(await screen.findByRole('alert')).toHaveTextContent('Server error')
  })
})

describe('AC2 - none waiting', () => {
  it('shows "No equipment requirements" and no rows', async () => {
    mockList.mockResolvedValue([])
    renderPage()

    expect(await screen.findByText('No equipment requirements')).toBeInTheDocument()
    expect(screen.queryByRole('listitem')).not.toBeInTheDocument()
  })

  it('does not show the message while the list is still loading, or when it failed', async () => {
    mockList.mockRejectedValue(new ApiError(500, 'Server error'))
    renderPage()

    await screen.findByRole('alert')
    expect(screen.queryByText('No equipment requirements')).not.toBeInTheDocument()
  })

  it('does not show the message when there are rows', async () => {
    renderPage()

    await screen.findByText('Audio')
    expect(screen.queryByText('No equipment requirements')).not.toBeInTheDocument()
  })
})

describe('AC3 - opening one', () => {
  it('offers one action per requirement: Manage requirement', async () => {
    renderPage()
    await screen.findByText('Audio')

    expect(screen.getByRole('button', { name: 'Manage Audio requirement' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Manage Projection requirement' })).toBeInTheDocument()
  })

  it('opens the Manage panel under that row, given the requirement and its event', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Audio')

    await user.click(screen.getByRole('button', { name: 'Manage Projection requirement' }))

    const panel = within(rowOf('Projection')).getByRole('region', { name: 'Manage panel' })
    expect(panel).toHaveTextContent('Projection for event 9 (2026-12-05T09:00:00Z)')
    expect(within(rowOf('Audio')).queryByRole('region', { name: 'Manage panel' })).not.toBeInTheDocument()
  })

  it('gives the panel the technical notes, which it shows with the placement', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Audio')

    await user.click(screen.getByRole('button', { name: 'Manage Audio requirement' }))

    expect(screen.getByRole('region', { name: 'Manage panel' })).toHaveTextContent(
      'notes: Handheld wireless, for panel Q&A',
    )
  })

  it('shows a change made in the panel straight away, and keeps the panel open', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Audio')
    await user.click(screen.getByRole('button', { name: 'Manage Audio requirement' }))

    await user.click(screen.getByRole('button', { name: 'stub part reserved' }))

    const row = rowOf('Audio')
    expect(within(row).getByText('Requested — 3 of 6 reserved')).toBeInTheDocument()
    expect(row).toHaveTextContent('3 × Shure BLX24 (placed: Stage left)')
    expect(screen.getByRole('region', { name: 'Manage panel' })).toBeInTheDocument()
  })

  it('keeps a requirement in place after it is fully reserved, showing it Reserved', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Audio')
    await user.click(screen.getByRole('button', { name: 'Manage Audio requirement' }))

    await user.click(screen.getByRole('button', { name: 'stub fully reserved' }))

    expect(within(rowOf('Audio')).getByText('Reserved — 6 of 6')).toBeInTheDocument()
  })

  it('closes the panel', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Audio')
    await user.click(screen.getByRole('button', { name: 'Manage Audio requirement' }))

    await user.click(screen.getByRole('button', { name: 'stub close' }))

    expect(screen.queryByRole('region', { name: 'Manage panel' })).not.toBeInTheDocument()
  })

  it('closes it again when Manage is pressed again, and says so with aria-expanded', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Audio')
    const manage = screen.getByRole('button', { name: 'Manage Audio requirement' })
    expect(manage).toHaveAttribute('aria-expanded', 'false')

    await user.click(manage)
    expect(manage).toHaveAttribute('aria-expanded', 'true')
    await user.click(manage)

    expect(screen.queryByRole('region', { name: 'Manage panel' })).not.toBeInTheDocument()
  })

  it('has one panel open at a time', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Audio')
    await user.click(screen.getByRole('button', { name: 'Manage Audio requirement' }))

    await user.click(screen.getByRole('button', { name: 'Manage Projection requirement' }))

    expect(screen.getAllByRole('region', { name: 'Manage panel' })).toHaveLength(1)
    expect(within(rowOf('Projection')).getByRole('region', { name: 'Manage panel' })).toBeInTheDocument()
  })

  it('offers no way to release a reservation: nothing can', async () => {
    renderPage()
    await screen.findByText('Audio')

    expect(
      screen.queryByRole('button', { name: /release|unreserve|cancel reservation|undo/i }),
    ).not.toBeInTheDocument()
  })
})
