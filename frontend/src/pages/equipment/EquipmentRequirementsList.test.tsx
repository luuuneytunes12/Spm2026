/**
 * Component tests for Technical Support's list of events with equipment to
 * review.
 *
 * Traceability (see docs/test-cases-equipment-requirements.md):
 *   ER AC2  requirements are visible to Technical Support Staff from the
 *           event record -- this page is how they get to the record.
 *
 * Which events are listed (never drafts, never before approval) is the
 * backend's rule, covered by backend/tests/test_equipment_requirements.py.
 * These tests cover what the page does with the answer.
 */
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/api'
import { formatRange } from '../../lib/events'
import { EquipmentRequirementsList } from './EquipmentRequirementsList'

vi.mock('../../lib/equipmentRequirements', async () => {
  const actual = await vi.importActual<typeof import('../../lib/equipmentRequirements')>(
    '../../lib/equipmentRequirements',
  )
  return { ...actual, listSupportEvents: vi.fn(), getSupportEvent: vi.fn() }
})

import { listSupportEvents } from '../../lib/equipmentRequirements'
import type { SupportEventSummary } from '../../lib/equipmentRequirements'

const mockList = vi.mocked(listSupportEvents)

const CONFERENCE: SupportEventSummary = {
  id: 7,
  name: 'Regional Partner Conference',
  event_type: 'conference',
  proposed_start: '2026-11-02T09:00:00Z',
  proposed_end: '2026-11-02T17:00:00Z',
  expected_attendance: 120,
  status: 'approved',
  requirement_count: 3,
}

const WORKSHOP: SupportEventSummary = {
  ...CONFERENCE,
  id: 9,
  name: 'Robotics Workshop',
  event_type: 'workshop',
  expected_attendance: 40,
  status: 'confirmed',
  requirement_count: 1,
}

function renderPage() {
  return render(
    <MemoryRouter>
      <EquipmentRequirementsList />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockList.mockResolvedValue([CONFERENCE, WORKSHOP])
})

describe('ER AC2 - finding an event with equipment to review', () => {
  it('lists each event with its name, date, attendance and type', async () => {
    renderPage()

    const row = (await screen.findByText('Regional Partner Conference')).closest('li')!
    // The same helper the page formats with, so the test holds in any
    // timezone or locale instead of hard-coding one rendering.
    expect(
      within(row).getByText(formatRange(CONFERENCE.proposed_start, CONFERENCE.proposed_end), {
        exact: false,
      }),
    ).toBeInTheDocument()
    expect(within(row).getByText(/120 attendees/)).toBeInTheDocument()
    expect(within(row).getByText(/conference/)).toBeInTheDocument()
  })

  it('says how many requirements each event has', async () => {
    renderPage()

    const first = (await screen.findByText('Regional Partner Conference')).closest('li')!
    const second = screen.getByText('Robotics Workshop').closest('li')!
    expect(within(first).getByText('3 requirements')).toBeInTheDocument()
    expect(within(second).getByText('1 requirement')).toBeInTheDocument()
  })

  it('shows where each event is in its life, so a confirmed one reads differently', async () => {
    renderPage()

    const first = (await screen.findByText('Regional Partner Conference')).closest('li')!
    const second = screen.getByText('Robotics Workshop').closest('li')!
    expect(within(first).getByText('Approved')).toBeInTheDocument()
    expect(within(second).getByText('Confirmed')).toBeInTheDocument()
  })

  it('links each event to its record', async () => {
    renderPage()

    const link = await screen.findByRole('link', {
      name: 'View requirements for Regional Partner Conference',
    })
    expect(link).toHaveAttribute('href', '/equipment-requirements/7')
  })

  it('labels an event that was never named rather than rendering a blank row', async () => {
    mockList.mockResolvedValue([{ ...CONFERENCE, name: null }])
    renderPage()

    expect(await screen.findByText('Untitled event')).toBeInTheDocument()
  })

  it('explains an empty list instead of showing nothing', async () => {
    mockList.mockResolvedValue([])
    renderPage()

    expect(await screen.findByText('No events have equipment to review yet.')).toBeInTheDocument()
    expect(screen.getByText(/once an event is approved/i)).toBeInTheDocument()
  })

  it('says so when the list cannot be loaded', async () => {
    mockList.mockRejectedValue(new ApiError(500, 'Server error'))
    renderPage()

    expect(await screen.findByRole('alert')).toHaveTextContent('Server error')
  })

  it('offers no way to change anything -- reviewing is a later story', async () => {
    renderPage()
    await screen.findByText('Regional Partner Conference')

    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
