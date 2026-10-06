/**
 * Component tests for the two pages the Lead's shortcuts open.
 * Traceability (docs/test-cases-coordinator-lead-landing.md): AC2 -- each
 * shortcut "takes me to that feature".
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { LeadEvent } from '../../lib/coordinatorLead'

vi.mock('../../lib/coordinatorLead', () => ({
  listUnassignedRequests: vi.fn(),
  listUnassignedQueue: vi.fn(),
  listCoordinatorAssignments: vi.fn(),
  listLeadCoordinators: vi.fn(),
}))

import { MemoryRouter } from 'react-router'
import {
  listCoordinatorAssignments,
  listLeadCoordinators,
  listUnassignedQueue,
  listUnassignedRequests,
} from '../../lib/coordinatorLead'
import { CoordinatorAssignments, UnassignedQueue, UnassignedRequests } from './LeadPages'

const event = (over: Partial<LeadEvent>): LeadEvent => ({
  id: 1,
  name: 'Partner Conference',
  event_type: 'conference',
  proposed_start: null,
  proposed_end: null,
  expected_attendance: 120,
  status: 'submitted_awaiting_coordinator',
  submitted_at: null,
  updated_at: '2026-10-01T00:00:00Z',
  organiser: { id: 2, name: 'Olivia Organiser', email: 'o@cs.local' },
  coordinator: null,
  ...over,
})

describe('Lead pages', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(listLeadCoordinators).mockResolvedValue([])
  })

  it('AC2: Unassigned Requests lists each request as not yet assigned', async () => {
    vi.mocked(listUnassignedRequests).mockResolvedValue([event({})])
    render(<UnassignedRequests />)
    expect(await screen.findByText('Partner Conference')).toBeInTheDocument()
    expect(screen.getByText(/not yet assigned/)).toBeInTheDocument()
  })

  it('AC2: Coordinator Assignments shows who holds each event', async () => {
    vi.mocked(listCoordinatorAssignments).mockResolvedValue([
      event({ coordinator: { id: 3, name: 'Sam Tan', email: 's@cs.local' }, status: 'under_review' }),
    ])
    render(
      <MemoryRouter>
        <CoordinatorAssignments />
      </MemoryRouter>,
    )
    expect(await screen.findByText(/Coordinator: Sam Tan/)).toBeInTheDocument()
  })

  it('shows an empty state when there is nothing to list', async () => {
    vi.mocked(listUnassignedRequests).mockResolvedValue([])
    render(<UnassignedRequests />)
    expect(await screen.findByText(/No unassigned requests/)).toBeInTheDocument()
  })

  it('shows the error when the server cannot be reached', async () => {
    vi.mocked(listCoordinatorAssignments).mockRejectedValue(new Error('down'))
    render(
      <MemoryRouter>
        <CoordinatorAssignments />
      </MemoryRouter>,
    )
    expect(await screen.findByRole('alert')).toHaveTextContent(/Could not reach the server/)
  })

  it('Queue AC1/AC3: lists each queued request with the review fields and the awaiting status', async () => {
    vi.mocked(listUnassignedQueue).mockResolvedValue([
      event({ id: 7, submitted_at: '2026-10-01T09:30:00Z', event_type: 'conference' }),
    ])
    render(
      <MemoryRouter>
        <UnassignedQueue />
      </MemoryRouter>,
    )
    expect(await screen.findByText('Partner Conference')).toBeInTheDocument()
    expect(screen.getByText('Submitted – Awaiting Coordinator')).toBeInTheDocument()
    expect(screen.getByText(/conference/)).toBeInTheDocument()
    expect(screen.getByText(/120 attendees/)).toBeInTheDocument()
    expect(screen.getByText(/Organiser: Olivia Organiser/)).toBeInTheDocument()
    expect(screen.getByText(/Organiser: Olivia Organiser · Submitted \S+/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Review/ })).toHaveAttribute('href', '/coordinator-lead/queue/7')
  })

  it('Queue AC3: keeps the order the server sends (oldest first)', async () => {
    vi.mocked(listUnassignedQueue).mockResolvedValue([
      event({ id: 1, name: 'First in' }),
      event({ id: 2, name: 'Second in' }),
    ])
    render(
      <MemoryRouter>
        <UnassignedQueue />
      </MemoryRouter>,
    )
    const names = (await screen.findAllByText(/in$/)).map((n) => n.textContent)
    expect(names).toEqual(['First in', 'Second in'])
  })

  it('Queue: shows an empty state', async () => {
    vi.mocked(listUnassignedQueue).mockResolvedValue([])
    render(
      <MemoryRouter>
        <UnassignedQueue />
      </MemoryRouter>,
    )
    expect(await screen.findByText(/The queue is empty/)).toBeInTheDocument()
  })

  it('SCRUM-82 AC1: lists each active Event with its name, Coordinator and status', async () => {
    vi.mocked(listCoordinatorAssignments).mockResolvedValue([
      event({ id: 4, name: 'Held by Sam', status: 'planning_event', coordinator: { id: 3, name: 'Sam Tan', email: 's@cs.local' } }),
    ])
    render(
      <MemoryRouter>
        <CoordinatorAssignments />
      </MemoryRouter>,
    )
    expect(await screen.findByText('Held by Sam')).toBeInTheDocument()
    expect(screen.getByText(/Coordinator: Sam Tan/)).toBeInTheDocument()
    expect(screen.getByText('Planning Event')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Review/ })).toHaveAttribute('href', '/coordinator-lead/assignments/4')
  })

  it('SCRUM-82 AC2: filtering by a Coordinator reloads only theirs and shows how many', async () => {
    vi.mocked(listLeadCoordinators).mockResolvedValue([
      { id: 3, name: 'Sam Tan', email: 's@cs.local', active_events: 2 },
      { id: 5, name: 'Priya Nair', email: 'p@cs.local', active_events: 0 },
    ])
    vi.mocked(listCoordinatorAssignments).mockImplementation(async (id?: number) =>
      id === 3
        ? [event({ id: 1, name: 'S1' }), event({ id: 2, name: 'S2' })]
        : [event({ id: 1, name: 'S1' }), event({ id: 2, name: 'S2' }), event({ id: 9, name: 'P1' })],
    )
    render(
      <MemoryRouter>
        <CoordinatorAssignments />
      </MemoryRouter>,
    )
    expect(await screen.findByText('3 active Events')).toBeInTheDocument()
    await screen.findByRole('option', { name: 'Sam Tan (2)' })

    await screen.findByRole('option', { name: 'Sam Tan (2)' })
    await userEvent.selectOptions(screen.getByLabelText('Filter by Coordinator'), 'Sam Tan (2)')

    await waitFor(() => expect(listCoordinatorAssignments).toHaveBeenLastCalledWith(3))
    expect(await screen.findByText('2 active Events')).toBeInTheDocument()
    expect(screen.queryByText('P1')).not.toBeInTheDocument()
  })

  it('SCRUM-82 AC2: a Coordinator with no active Events shows 0 and the empty state', async () => {
    vi.mocked(listLeadCoordinators).mockResolvedValue([{ id: 5, name: 'Priya Nair', email: 'p@cs.local', active_events: 0 }])
    vi.mocked(listCoordinatorAssignments).mockImplementation(async (id?: number) => (id === 5 ? [] : [event({})]))
    render(
      <MemoryRouter>
        <CoordinatorAssignments />
      </MemoryRouter>,
    )
    await screen.findByRole('option', { name: 'Priya Nair (0)' })
    await userEvent.selectOptions(screen.getByLabelText('Filter by Coordinator'), 'Priya Nair (0)')
    expect(await screen.findByText('0 active Events')).toBeInTheDocument()
    expect(screen.getByText('No active Events match.')).toBeInTheDocument()
  })

  it('SCRUM-82: the full list still works when the Coordinator filter cannot load', async () => {
    vi.mocked(listLeadCoordinators).mockRejectedValue(new Error('down'))
    vi.mocked(listCoordinatorAssignments).mockResolvedValue([event({ name: 'Still here' })])
    render(
      <MemoryRouter>
        <CoordinatorAssignments />
      </MemoryRouter>,
    )
    expect(await screen.findByText('Still here')).toBeInTheDocument()
  })
})
