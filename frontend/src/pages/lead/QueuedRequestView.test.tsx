/**
 * Component tests for the Lead's read-only review of a queued request.
 * Traceability (Unassigned Queue story):
 *   AC4  everything the Organiser entered is shown, and nothing is editable
 *   AC5  a request that is not in the queue is refused, nothing shown
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/api'
import type { LeadEventDetail } from '../../lib/coordinatorLead'

vi.mock('../../lib/coordinatorLead', () => ({
  getQueuedRequest: vi.fn(),
  assignEvent: vi.fn(),
  listLeadCoordinators: vi.fn(),
}))

import { assignEvent, getQueuedRequest, listLeadCoordinators } from '../../lib/coordinatorLead'
import { QueuedRequestView } from './QueuedRequestView'

const DETAIL: LeadEventDetail = {
  id: 7,
  name: 'Regional Partner Conference',
  event_type: 'conference',
  proposed_start: '2026-11-02T09:00:00Z',
  proposed_end: '2026-11-02T17:00:00Z',
  expected_attendance: 120,
  status: 'submitted',
  submitted_at: '2026-10-01T09:30:00Z',
  updated_at: '2026-10-01T09:30:00Z',
  organiser_id: 2,
  coordinator_id: null,
  coordinator: null,
  purpose: 'Annual partner briefing',
  description: 'A full-day briefing for our regional partners.',
  programme: null,
  venue_requirements: 'Main hall, stage, podium',
  room_layout_preference: null,
  accessibility_needs: 'Step-free access, hearing loop',
  equipment_requirements: '2 projectors, 4 radio mics',
  equipment_items: [],
  special_arrangements: null,
  registration_enabled: true,
  created_at: '2026-10-01T09:00:00Z',
  organiser: { id: 2, name: 'Olivia Organiser', email: 'olivia@cs.local' },
}

function renderAt(id: string) {
  render(
    <MemoryRouter initialEntries={[`/coordinator-lead/queue/${id}`]}>
      <Routes>
        <Route path="/coordinator-lead/queue/:id" element={<QueuedRequestView />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('QueuedRequestView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(listLeadCoordinators).mockResolvedValue([
      { id: 3, name: 'Sam Tan', email: 's@cs.local', active_events: 2 },
      { id: 5, name: 'Priya Nair', email: 'p@cs.local', active_events: 0 },
    ])
  })

  it('AC4: shows everything the Organiser entered', async () => {
    vi.mocked(getQueuedRequest).mockResolvedValue(DETAIL)
    renderAt('7')
    expect(await screen.findByRole('heading', { level: 1, name: 'Regional Partner Conference' })).toBeInTheDocument()
    for (const text of [
      'Annual partner briefing',
      'A full-day briefing for our regional partners.',
      'conference',
      '120',
      'Main hall, stage, podium',
      'Step-free access, hearing loop',
      '2 projectors, 4 radio mics',
      'Olivia Organiser',
    ]) {
      expect(screen.getByText(text)).toBeInTheDocument()
    }
    for (const label of ['Event name', 'Purpose', 'Description', 'Type', 'Proposed date and time', 'Expected attendance', 'Venue requirements', 'Accessibility needs', 'Equipment requirements', 'Registration needed']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
    expect(screen.getByText('Yes')).toBeInTheDocument() // registration needed
  })

  it('AC4: the request itself is read-only -- the only control is the assign panel', async () => {
    vi.mocked(getQueuedRequest).mockResolvedValue(DETAIL)
    renderAt('7')
    await screen.findByRole('heading', { level: 1 })
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    expect(document.querySelector('textarea, input, form')).toBeNull()
    expect(screen.getAllByRole('button').map((b) => b.textContent)).toEqual(['Assign'])
    expect(screen.getAllByRole('combobox')).toHaveLength(1)
  })

  it('SCRUM-80 AC2: the assign list shows each Coordinator with their active Events', async () => {
    vi.mocked(getQueuedRequest).mockResolvedValue(DETAIL)
    renderAt('7')
    expect(await screen.findByRole('option', { name: 'Sam Tan (2 active Events)' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Priya Nair (0 active Events)' })).toBeInTheDocument()
  })

  it('SCRUM-80 AC1: Assign is disabled until a Coordinator is chosen, then assigns and confirms', async () => {
    vi.mocked(getQueuedRequest).mockResolvedValue(DETAIL)
    vi.mocked(assignEvent).mockResolvedValue({ ...DETAIL, coordinator: { id: 3, name: 'Sam Tan', email: 's@cs.local' } } as never)
    renderAt('7')
    const assign = await screen.findByRole('button', { name: 'Assign' })
    expect(assign).toBeDisabled()
    await screen.findByRole('option', { name: 'Sam Tan (2 active Events)' })
    await userEvent.selectOptions(screen.getByLabelText('Event Coordinator'), 'Sam Tan (2 active Events)')
    expect(assign).toBeEnabled()
    await userEvent.click(assign)
    await waitFor(() => expect(assignEvent).toHaveBeenCalledWith(7, 3))
    expect(await screen.findByRole('status')).toHaveTextContent('Assigned to Sam Tan')
    expect(screen.getByRole('status')).toHaveTextContent('Under Review')
  })

  it('SCRUM-80 AC5: a refusal is shown and nothing is confirmed', async () => {
    vi.mocked(getQueuedRequest).mockResolvedValue(DETAIL)
    vi.mocked(assignEvent).mockRejectedValue(new ApiError(409, 'This request is not in the Unassigned Queue; its assignment is unchanged'))
    renderAt('7')
    await screen.findByRole('option', { name: 'Priya Nair (0 active Events)' })
    await userEvent.selectOptions(screen.getByLabelText('Event Coordinator'), 'Priya Nair (0 active Events)')
    await userEvent.click(screen.getByRole('button', { name: 'Assign' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('not in the Unassigned Queue')
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Assign' })).toBeEnabled() // can retry
  })

  it('AC5: a request that is not in the queue shows a refusal and no details', async () => {
    vi.mocked(getQueuedRequest).mockRejectedValue(new ApiError(404, 'Request not found in the queue'))
    renderAt('3')
    expect(await screen.findByRole('alert')).toHaveTextContent('not in the Unassigned Queue')
    expect(screen.queryByText('Annual partner briefing')).not.toBeInTheDocument()
  })
})
