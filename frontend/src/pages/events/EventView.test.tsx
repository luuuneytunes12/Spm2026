/**
 * Component tests for the Organiser's own event page -- specifically AC2
 * of the "Mark myself unavailable" story, and AC1/AC3 of "View Coordinator
 * Assignment" (SCRUM-23):
 *
 *   The Event Organiser can see who their assigned coordinator is on
 *   their event page -- and, after a reassignment, who the NEW one is.
 *
 * Whether a Coordinator actually gets assigned is the backend's job,
 * covered by backend/tests/test_coordinator_availability.py. These tests
 * cover what this screen does with the answer.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { EventView } from './EventView'

// The count is a separate, best-effort request -- covered by its own test.
vi.mock('../../lib/coordinators', () => ({
  getAssignmentPool: vi.fn().mockResolvedValue({
    available: 2,
    coordinators: [
      { id: 8, name: 'Alex Kim', email: 'alex@connectsphere.test' },
      { id: 9, name: 'Jordan Lee', email: 'jordan@connectsphere.test' },
    ],
  }),
}))

vi.mock('../../lib/events', async () => {
  const actual = await vi.importActual<typeof import('../../lib/events')>('../../lib/events')
  return { ...actual, getEvent: vi.fn(), getOwnEventActivity: vi.fn() }
})

import { getEvent, getOwnEventActivity } from '../../lib/events'
import type { ActivityEntry, EventDetail } from '../../lib/events'

const mockGet = vi.mocked(getEvent)
const mockActivity = vi.mocked(getOwnEventActivity)

const BASE: EventDetail = {
  id: 7,
  organiser_id: 1,
  coordinator_id: null,
  coordinator: null,
  name: 'Robotics Summit',
  event_type: 'conference',
  purpose: 'Annual partner briefing',
  description: null,
  programme: null,
  proposed_start: '2026-11-02T09:00:00Z',
  proposed_end: '2026-11-02T17:00:00Z',
  expected_attendance: 120,
  venue_requirements: 'Main hall',
  room_layout_preference: null,
  accessibility_needs: 'Step-free access',
  equipment_requirements: '2 projectors',
  equipment_items: [],
  special_arrangements: null,
  registration_enabled: false,
  status: 'submitted',
  submitted_at: '2026-09-10T02:00:00Z',
  created_at: '2026-09-09T00:00:00Z',
  updated_at: '2026-09-10T02:00:00Z',
}

function renderView(id = '7') {
  return render(
    <MemoryRouter initialEntries={[`/organiser/events/${id}`]}>
      <Routes>
        <Route path="/organiser/events/:id" element={<EventView />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockActivity.mockResolvedValue([])
})

describe('AC2 - the assigned coordinator is visible on the event page', () => {
  it('names the Coordinator and links their email once one is assigned', async () => {
    mockGet.mockResolvedValue({
      ...BASE,
      coordinator_id: 2,
      coordinator: { id: 2, name: 'Sam Tan', email: 'sam@connectsphere.test' },
    })

    renderView()

    await waitFor(() => expect(screen.getByText('Your Assigned Event Coordinator')).toBeInTheDocument())
    expect(screen.getByText(/Sam Tan/)).toBeInTheDocument()
    const link = screen.getByRole('link', { name: 'sam@connectsphere.test' })
    expect(link).toHaveAttribute('href', 'mailto:sam@connectsphere.test')
  })

  it('says plainly that nobody is assigned yet, rather than showing a blank section', async () => {
    mockGet.mockResolvedValue({ ...BASE })

    renderView()

    await waitFor(() => expect(screen.getByText('Your Assigned Event Coordinator')).toBeInTheDocument())
    expect(screen.getByText(/Not yet assigned/)).toBeInTheDocument()
  })

  it('does not show a Coordinator section for a draft, which has none to assign', async () => {
    mockGet.mockResolvedValue({
      ...BASE,
      status: 'draft',
      submitted_at: null,
    })

    renderView()

    await waitFor(() => expect(screen.getByText('Robotics Summit')).toBeInTheDocument())
    expect(screen.queryByText('Your Assigned Event Coordinator')).not.toBeInTheDocument()
  })

  it('offers correction while a submitted request awaits a decision', async () => {
    mockGet.mockResolvedValue({ ...BASE, status: 'under_review' })

    renderView()

    expect(await screen.findByRole('link', { name: 'Correct request' })).toHaveAttribute(
      'href',
      '/organiser/events/7/edit',
    )
  })

  it('does not offer correction after the Coordinator decides', async () => {
    mockGet.mockResolvedValue({ ...BASE, status: 'approved' })

    renderView()

    await screen.findByText('Approved')
    expect(screen.queryByRole('link', { name: 'Correct request' })).not.toBeInTheDocument()
  })

  it('shows the Coordinator rejection reason in the event activity log', async () => {
    const rejection: ActivityEntry = {
      from_status: 'under_review',
      to_status: 'rejected',
      note: 'The requested venue is unavailable on that date.',
      changed_by_name: 'Sam Tan',
      created_at: '2026-09-12T09:00:00Z',
    }
    mockGet.mockResolvedValue({ ...BASE, status: 'rejected' })
    mockActivity.mockResolvedValue([rejection])

    renderView()

    expect(
      await screen.findByText('The requested venue is unavailable on that date.'),
    ).toBeInTheDocument()
    expect(screen.getByText(/Sam Tan/)).toBeInTheDocument()
  })
})

describe('SCRUM-23 AC3 - the new coordinator is shown after a reassignment', () => {
  const PRIYA = { id: 3, name: 'Priya Nair', email: 'priya@connectsphere.test' }

  it('shows the new Coordinator, not the one who handed the event over', async () => {
    mockGet.mockResolvedValue({
      ...BASE,
      status: 'under_review',
      coordinator_id: PRIYA.id,
      coordinator: PRIYA,
    })
    mockActivity.mockResolvedValue([
      {
        from_status: 'under_review',
        to_status: 'under_review',
        note: 'Reassigned from Sam Tan to Priya Nair: Sam Tan declined this event.',
        changed_by_name: 'Sam Tan',
        created_at: '2026-09-12T09:00:00Z',
      },
    ])

    renderView()

    const card = (await screen.findByText('Your Assigned Event Coordinator')).closest('section')!
    expect(within(card).getByText(/Priya Nair/)).toBeInTheDocument()
    expect(within(card).getByRole('link', { name: 'priya@connectsphere.test' })).toHaveAttribute(
      'href',
      'mailto:priya@connectsphere.test',
    )
    expect(within(card).queryByText(/Sam Tan/)).not.toBeInTheDocument()
  })

  it('says nobody is assigned when the hand-off found no replacement', async () => {
    mockGet.mockResolvedValue({ ...BASE, status: 'under_review', coordinator_id: null, coordinator: null })

    renderView()

    expect(await screen.findByText(/Not yet assigned/)).toBeInTheDocument()
  })
})

describe('SCRUM-23 - the activity log records who was assigned', () => {
  it('lists the assignment and the reassignment, newest first', async () => {
    mockGet.mockResolvedValue({
      ...BASE,
      status: 'under_review',
      coordinator_id: 3,
      coordinator: { id: 3, name: 'Priya Nair', email: 'priya@connectsphere.test' },
    })
    mockActivity.mockResolvedValue([
      {
        from_status: 'under_review',
        to_status: 'under_review',
        note: 'Reassigned from Sam Tan to Priya Nair: Sam Tan declined this event.',
        changed_by_name: 'Sam Tan',
        created_at: '2026-09-12T09:00:00Z',
      },
      {
        from_status: 'submitted',
        to_status: 'under_review',
        note: 'Assigned to Sam Tan.',
        changed_by_name: 'Priya Menon',
        created_at: '2026-09-10T02:00:00Z',
      },
    ])

    renderView()

    const log = await screen.findByRole('list', { name: 'Activity log' })
    const items = within(log).getAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(items[0]).toHaveTextContent('Reassigned from Sam Tan to Priya Nair')
    expect(items[1]).toHaveTextContent('Assigned to Sam Tan.')
  })
})

describe('coordinators available (debugging aid)', () => {
  it('shows the count beside the Coordinator card, including when nobody is assigned', async () => {
    mockGet.mockResolvedValue({ ...BASE })

    renderView()

    expect(await screen.findByText(/Not yet assigned/)).toBeInTheDocument()
    // The count arrives on its own request, so wait for it rather than assume.
    expect(await screen.findByTestId('available-coordinators')).toHaveTextContent(
      'Coordinators currently available for assignment: 2',
    )
    await userEvent.click(screen.getByText(/Coordinators currently available/))
    expect(screen.getByText('Alex Kim')).toBeVisible()
  })

  it('has no count on a draft, which has no Coordinator section', async () => {
    mockGet.mockResolvedValue({ ...BASE, status: 'draft', submitted_at: null })

    renderView()

    await screen.findByText('Robotics Summit')
    expect(screen.queryByTestId('available-coordinators')).not.toBeInTheDocument()
  })
})
