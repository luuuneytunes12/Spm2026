/**
 * Component tests for the Organiser's own event page -- specifically AC2
 * of the "Mark myself unavailable" story:
 *
 *   The Event Organiser can see who their assigned coordinator is on
 *   their event page.
 *
 * Whether a Coordinator actually gets assigned is the backend's job,
 * covered by backend/tests/test_coordinator_availability.py. These tests
 * cover what this screen does with the answer.
 */
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { EventView } from './EventView'

vi.mock('../../lib/events', async () => {
  const actual = await vi.importActual<typeof import('../../lib/events')>('../../lib/events')
  return { ...actual, getEvent: vi.fn() }
})

import { getEvent } from '../../lib/events'
import type { EventDetail } from '../../lib/events'

const mockGet = vi.mocked(getEvent)

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
    expect(screen.getByText('Sam Tan')).toBeInTheDocument()
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
})
