/**
 * Component tests for the Lead's read-only review of an active, assigned Event.
 * Traceability (SCRUM-82):
 *   AC3  everything the Organiser entered, the Organiser's contact details and
 *        the current status are shown, and nothing is editable
 *   AC4  an Event that is not an active assignment is refused, nothing shown
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/api'
import type { LeadEventDetail } from '../../lib/coordinatorLead'

vi.mock('../../lib/coordinatorLead', () => ({
  getAssignedEventForLead: vi.fn(),
  reassignEvent: vi.fn(),
  listLeadCoordinators: vi.fn(),
}))

import { getAssignedEventForLead, listLeadCoordinators, reassignEvent } from '../../lib/coordinatorLead'
import { AssignedEventReview } from './AssignedEventReview'

const DETAIL: LeadEventDetail = {
  id: 7,
  name: 'Regional Partner Conference',
  event_type: 'conference',
  proposed_start: '2026-11-02T09:00:00Z',
  proposed_end: '2026-11-02T17:00:00Z',
  expected_attendance: 120,
  status: 'planning_event',
  submitted_at: '2026-10-01T09:30:00Z',
  updated_at: '2026-10-02T09:30:00Z',
  organiser_id: 2,
  coordinator_id: 3,
  coordinator: { id: 3, name: 'Sam Tan', email: 'sam@cs.local' },
  purpose: 'Annual partner briefing',
  description: 'A full-day briefing for our regional partners.',
  programme: null,
  venue_requirements: 'Main hall, stage, podium',
  room_layout_preference: null,
  accessibility_needs: 'Step-free access, hearing loop',
  equipment_requirements: '2 projectors, 4 radio mics',
  equipment_items: [],
  special_arrangements: null,
  registration_enabled: false,
  created_at: '2026-10-01T09:00:00Z',
  organiser: { id: 2, name: 'Olivia Organiser', email: 'olivia@cs.local' },
}

function renderAt(id: string) {
  render(
    <MemoryRouter initialEntries={[`/coordinator-lead/assignments/${id}`]}>
      <Routes>
        <Route path="/coordinator-lead/assignments/:id" element={<AssignedEventReview />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('AssignedEventReview', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(listLeadCoordinators).mockResolvedValue([
      { id: 3, name: 'Sam Tan', email: 's@cs.local', active_events: 3 },
      { id: 5, name: 'Priya Nair', email: 'p@cs.local', active_events: 1 },
    ])
  })

  it('AC3: shows what the Organiser entered, their contact details and the current status', async () => {
    vi.mocked(getAssignedEventForLead).mockResolvedValue(DETAIL)
    renderAt('7')
    expect(await screen.findByRole('heading', { level: 1, name: 'Regional Partner Conference' })).toBeInTheDocument()
    for (const text of [
      'Annual partner briefing',
      'A full-day briefing for our regional partners.',
      '120',
      'Main hall, stage, podium',
      'Step-free access, hearing loop',
      '2 projectors, 4 radio mics',
      'Olivia Organiser',
      'olivia@cs.local',
      'Sam Tan',
    ]) {
      expect(screen.getByText(text)).toBeInTheDocument()
    }
    expect(screen.getByText('Planning Event')).toBeInTheDocument() // current status, not the queue's badge
    expect(screen.queryByText('Submitted – Awaiting Coordinator')).not.toBeInTheDocument()
    expect(screen.getByText('No')).toBeInTheDocument() // registration needed
    expect(screen.getByRole('link', { name: /Back to Coordinator Assignments/ })).toHaveAttribute(
      'href',
      '/coordinator-lead/assignments',
    )
  })

  it('AC3: the Event itself is read-only -- the only control is the reassign panel', async () => {
    vi.mocked(getAssignedEventForLead).mockResolvedValue(DETAIL)
    renderAt('7')
    await screen.findByRole('heading', { level: 1 })
    expect(document.querySelector('textarea, input, form')).toBeNull()
    expect(screen.getAllByRole('button').map((b) => b.textContent)).toEqual(['Reassign'])
  })

  it('SCRUM-81: the new-Coordinator list leaves out the one who already has the Event', async () => {
    vi.mocked(getAssignedEventForLead).mockResolvedValue(DETAIL) // held by Sam (id 3)
    renderAt('7')
    expect(await screen.findByRole('option', { name: 'Priya Nair (1 active Event)' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /Sam Tan/ })).not.toBeInTheDocument()
  })

  it('SCRUM-81 AC1: Reassign is disabled until a Coordinator is chosen, then moves the Event', async () => {
    vi.mocked(getAssignedEventForLead).mockResolvedValue(DETAIL)
    vi.mocked(reassignEvent).mockResolvedValue({ ...DETAIL, coordinator: { id: 5, name: 'Priya Nair', email: 'p@cs.local' } } as never)
    renderAt('7')
    const button = await screen.findByRole('button', { name: 'Reassign' })
    expect(button).toBeDisabled()
    await screen.findByRole('option', { name: 'Priya Nair (1 active Event)' })
    await userEvent.selectOptions(screen.getByLabelText('New Event Coordinator'), 'Priya Nair (1 active Event)')
    await userEvent.click(button)
    await waitFor(() => expect(reassignEvent).toHaveBeenCalledWith(7, 5))
    expect(await screen.findByRole('status')).toHaveTextContent('Reassigned to Priya Nair')
    expect(screen.getByRole('status')).toHaveTextContent('status and history are unchanged')
  })

  it('SCRUM-81 AC4: a refusal for a finished Event is shown and nothing is confirmed', async () => {
    vi.mocked(getAssignedEventForLead).mockResolvedValue(DETAIL)
    vi.mocked(reassignEvent).mockRejectedValue(new ApiError(409, 'A finished Event cannot be reassigned'))
    renderAt('7')
    await screen.findByRole('option', { name: 'Priya Nair (1 active Event)' })
    await userEvent.selectOptions(screen.getByLabelText('New Event Coordinator'), 'Priya Nair (1 active Event)')
    await userEvent.click(screen.getByRole('button', { name: 'Reassign' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('finished Event cannot be reassigned')
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('AC4: an Event that is not an active assignment shows a refusal and no details', async () => {
    vi.mocked(getAssignedEventForLead).mockRejectedValue(new ApiError(404, 'Event not found in the assignments'))
    renderAt('3')
    expect(await screen.findByRole('alert')).toHaveTextContent('not an active Coordinator assignment')
    expect(screen.queryByText('Annual partner briefing')).not.toBeInTheDocument()
  })
})
