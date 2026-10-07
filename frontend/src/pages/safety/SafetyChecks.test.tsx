/** Safety Officer stories, UI side. Whether the API accepts each decision
 *  is backend/tests/test_safety_checks.py; these cover what the pages show
 *  and send. */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SafetyCheckView } from './SafetyCheckView'
import { SafetyChecks } from './SafetyChecks'

vi.mock('../../lib/safetyChecks', async () => {
  const actual = await vi.importActual<typeof import('../../lib/safetyChecks')>('../../lib/safetyChecks')
  return {
    ...actual,
    listSafetyChecks: vi.fn(),
    getSafetyCheck: vi.fn(),
    approveSafetyCheck: vi.fn(),
    requestSafetyChanges: vi.fn(),
    rejectSafetyCheck: vi.fn(),
  }
})
import {
  approveSafetyCheck,
  getSafetyCheck,
  listSafetyChecks,
  rejectSafetyCheck,
  requestSafetyChanges,
} from '../../lib/safetyChecks'
import type { SafetyCheckDetail } from '../../lib/safetyChecks'

const DETAIL: SafetyCheckDetail = {
  id: 7,
  name: 'Regional Partner Conference',
  status: 'awaiting_safety_check',
  proposed_start: '2026-11-02T09:00:00Z',
  proposed_end: '2026-11-02T17:00:00Z',
  expected_attendance: 120,
  room_layout_preference: 'Theatre',
  accessibility_needs: 'Step-free access',
  special_arrangements: null,
  organiser: { id: 1, name: 'Olive Organiser', email: 'o@example.com' },
  coordinator: { id: 2, name: 'Cody Coordinator', email: 'c@example.com' },
  venue_bookings: [
    {
      id: 11,
      event_id: 7,
      status: 'approved',
      start_time: '2026-11-02T09:00:00Z',
      end_time: '2026-11-02T17:00:00Z',
      safety_recheck_reason: null,
      venue: {
        id: 3,
        name: 'Marina Hall',
        location: '10 Bayfront Ave',
        capacity: 250,
        supported_layouts: ['Theatre'],
        accessibility_features: ['Wheelchair access'],
        emergency_access: 'Two fire exits on the east side',
        known_restrictions: 'No open flames',
      },
    },
  ],
  equipment: [
    {
      id: 21,
      equipment_name: 'Projector',
      equipment_category: 'Projection',
      quantity_requested: 2,
      status: 'reserved',
      placement_notes: 'Back of hall',
      safety_recheck_reason: null,
    },
  ],
  activity: [],
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
  vi.mocked(getSafetyCheck).mockResolvedValue(DETAIL)
})

describe('S1 - Safety Checks queue and detail', () => {
  it('AC1: lists each awaiting event with its name, date and Event Coordinator', async () => {
    vi.mocked(listSafetyChecks).mockResolvedValue([
      {
        id: 7,
        name: 'Regional Partner Conference',
        proposed_start: DETAIL.proposed_start,
        proposed_end: DETAIL.proposed_end,
        coordinator: DETAIL.coordinator,
      },
    ])
    render(<SafetyChecks />, { wrapper: MemoryRouter })
    expect(await screen.findByText('Regional Partner Conference')).toBeInTheDocument()
    const meta = screen.getByText(/Coordinator: Cody Coordinator/)
    expect(meta).toHaveTextContent(/2026/)
  })

  it('AC2: says there are no events to review when the queue is empty', async () => {
    vi.mocked(listSafetyChecks).mockResolvedValue([])
    render(<SafetyChecks />, { wrapper: MemoryRouter })
    expect(await screen.findByText('No events to review.')).toBeInTheDocument()
  })

  it('AC3: shows attendance, venue capacity, layout, emergency access, restrictions, accessibility and placement', async () => {
    renderView()
    for (const text of [
      '120',
      '250',
      'Theatre',
      'Two fire exits on the east side',
      'No open flames',
      'Step-free access',
      /Placement: Back of hall/,
    ]) {
      expect((await screen.findAllByText(text)).length).toBeGreaterThan(0)
    }
  })

  it('renders every venue booking attached to the same event', async () => {
    vi.mocked(getSafetyCheck).mockResolvedValue({
      ...DETAIL,
      venue_bookings: [
        ...DETAIL.venue_bookings,
        {
          ...DETAIL.venue_bookings[0],
          id: 12,
          venue: {
            ...DETAIL.venue_bookings[0].venue,
            id: 4,
            name: 'Garden Pavilion',
          },
        },
      ],
    })
    renderView()

    expect(await screen.findByText(/Marina Hall/)).toBeInTheDocument()
    expect(screen.getByText(/Garden Pavilion/)).toBeInTheDocument()
  })
})

describe('S2/S3 - deciding', () => {
  it('S2 AC1: Approve sends the approval', async () => {
    vi.mocked(approveSafetyCheck).mockResolvedValue({} as never)
    renderView()
    await userEvent.click(await screen.findByRole('button', { name: 'Approve' }))
    expect(approveSafetyCheck).toHaveBeenCalledWith(7)
  })

  it('S3 AC1: a rejection without a reason is not sent', async () => {
    renderView()
    await userEvent.click(await screen.findByRole('button', { name: 'Reject' }))
    await userEvent.click(screen.getByRole('button', { name: 'Confirm rejection' }))
    expect(rejectSafetyCheck).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent('Give a reason')
  })

  it('S3 AC2: Request changes sends only the marked items with the reason', async () => {
    vi.mocked(requestSafetyChanges).mockResolvedValue({} as never)
    renderView()
    await userEvent.click(await screen.findByRole('button', { name: 'Request changes' }))
    await userEvent.click(screen.getByRole('checkbox', { name: /Projector/ }))
    await userEvent.type(screen.getByLabelText('Reason'), 'Projector blocks an exit')
    await userEvent.click(screen.getByRole('button', { name: 'Send change request' }))
    expect(requestSafetyChanges).toHaveBeenCalledWith(7, 'Projector blocks an exit', [], [21])
  })
})
