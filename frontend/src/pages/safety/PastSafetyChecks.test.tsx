/** Past Safety Checks, UI side. What the API returns and who may call it is
 *  backend/tests/test_past_safety_checks.py; these cover what the pages show. */
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { PastSafetyChecks } from './PastSafetyChecks'
import { SafetyCheckView } from './SafetyCheckView'

vi.mock('../../lib/safetyChecks', async () => {
  const actual = await vi.importActual<typeof import('../../lib/safetyChecks')>('../../lib/safetyChecks')
  return { ...actual, listPastSafetyChecks: vi.fn(), getSafetyCheck: vi.fn() }
})
import { getSafetyCheck, listPastSafetyChecks } from '../../lib/safetyChecks'
import type { PastSafetyCheck, SafetyCheckDetail } from '../../lib/safetyChecks'

const ROWS: PastSafetyCheck[] = [
  {
    id: 8,
    name: 'Later Event',
    proposed_start: '2026-12-01T09:00:00Z',
    proposed_end: '2026-12-01T17:00:00Z',
    status: 'safety_check_passed',
    decision: 'Approved',
    reason: null,
    decided_at: '2026-10-12T08:00:00Z',
  },
  {
    id: 7,
    name: 'Regional Partner Conference',
    proposed_start: '2026-11-02T09:00:00Z',
    proposed_end: '2026-11-02T17:00:00Z',
    status: 'planning_event',
    decision: 'Rejected',
    reason: 'Exits blocked',
    decided_at: '2026-10-10T08:00:00Z',
  },
]

const DETAIL: SafetyCheckDetail = {
  id: 7,
  name: 'Regional Partner Conference',
  status: 'planning_event',
  proposed_start: '2026-11-02T09:00:00Z',
  proposed_end: '2026-11-02T17:00:00Z',
  expected_attendance: 120,
  room_layout_preference: 'Theatre',
  accessibility_needs: 'Step-free access',
  special_arrangements: null,
  organiser: { id: 1, name: 'Olive Organiser', email: 'o@example.com' },
  coordinator: { id: 2, name: 'Cody Coordinator', email: 'c@example.com' },
  venue_bookings: [],
  equipment: [
    {
      id: 21,
      equipment_name: 'Projector',
      equipment_category: 'Projection',
      quantity_requested: 2,
      status: 'reserved',
      placement_notes: 'Back of hall',
      safety_recheck_reason: 'Exits blocked',
    },
  ],
  activity: [],
  decisions: [
    {
      decision: 'Changes Requested',
      reason: 'Move the projector',
      decided_by_name: 'Sasha Second',
      decided_at: '2026-10-11T08:00:00Z',
    },
    {
      decision: 'Rejected',
      reason: 'Exits blocked',
      decided_by_name: 'Sam Safety',
      decided_at: '2026-10-10T08:00:00Z',
    },
  ],
}

function renderView() {
  render(
    <MemoryRouter initialEntries={['/safety-checks/7']}>
      <Routes>
        <Route path="/safety-checks/:id" element={<SafetyCheckView />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(listPastSafetyChecks).mockResolvedValue(ROWS)
  vi.mocked(getSafetyCheck).mockResolvedValue(DETAIL)
})

describe('AC1 - the list of past Safety Checks', () => {
  it('shows each event with its name, date, decision, reason and decision time, in the order given', async () => {
    render(<PastSafetyChecks />, { wrapper: MemoryRouter })

    const items = await screen.findAllByRole('listitem')
    expect(items.map((li) => li.querySelector('.request-title')?.textContent)).toEqual([
      'Later Event',
      'Regional Partner Conference',
    ])
    const rejected = items[1]
    expect(within(rejected).getByText('Rejected')).toBeInTheDocument()
    expect(within(rejected).getByText('Reason: Exits blocked')).toBeInTheDocument()
    expect(within(rejected).getByText(/Decided .*2026/)).toBeInTheDocument()
    expect(within(rejected).getByText(/Nov.*2026|2026.*Nov|11\/0?2\/2026|0?2\/11\/2026/)).toBeInTheDocument()
  })

  it('shows an approval with no reason line', async () => {
    render(<PastSafetyChecks />, { wrapper: MemoryRouter })

    const [approved] = await screen.findAllByRole('listitem')
    expect(within(approved).getByText('Approved')).toBeInTheDocument()
    expect(within(approved).queryByText(/Reason:/)).not.toBeInTheDocument()
  })

  it('says there are none when nothing has been decided', async () => {
    vi.mocked(listPastSafetyChecks).mockResolvedValue([])
    render(<PastSafetyChecks />, { wrapper: MemoryRouter })

    expect(await screen.findByText('No past safety checks.')).toBeInTheDocument()
  })

  it('links each row to its read-only view', async () => {
    render(<PastSafetyChecks />, { wrapper: MemoryRouter })

    expect(await screen.findByRole('link', { name: 'View Regional Partner Conference' })).toHaveAttribute(
      'href',
      '/safety-checks/7',
    )
  })
})

describe('AC2 - opening a decided event', () => {
  it('shows its details and current status with no way to decide or edit', async () => {
    renderView()

    expect(await screen.findByText('Step-free access')).toBeInTheDocument()
    const timeline = screen.getByRole('list', { name: 'Status timeline' })
    expect(within(timeline).getByRole('listitem', { current: 'step' })).toHaveTextContent('Planning Event')
    for (const name of ['Approve', 'Request changes', 'Reject']) {
      expect(screen.queryByRole('button', { name })).not.toBeInTheDocument()
    }
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: '← Back to past safety checks' })).toHaveAttribute(
      'href',
      '/safety-checks/history',
    )
  })
})

describe('AC3 - every earlier decision on the event', () => {
  it('lists each decision with who made it, its reason and time, newest first', async () => {
    renderView()

    const list = await screen.findByRole('list', { name: 'Safety Check decisions' })
    const items = within(list).getAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(items[0]).toHaveTextContent('Changes Requested')
    expect(items[0]).toHaveTextContent('Sasha Second')
    expect(items[0]).toHaveTextContent('Reason: Move the projector')
    expect(items[1]).toHaveTextContent('Rejected')
    expect(items[1]).toHaveTextContent('Sam Safety')
    expect(items[1]).toHaveTextContent('Reason: Exits blocked')
    expect(items[1]).toHaveTextContent(/2026/)
  })

  it('says so when the event has no decision yet', async () => {
    vi.mocked(getSafetyCheck).mockResolvedValue({ ...DETAIL, decisions: [] })
    renderView()

    expect(await screen.findByText('No Safety Check decision yet.')).toBeInTheDocument()
  })
})
