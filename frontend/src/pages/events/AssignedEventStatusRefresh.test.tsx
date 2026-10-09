/**
 * The Coordinator's event page shows the event's new status as soon as a
 * venue is requested or equipment is recorded -- the first of either moves an
 * 'Event Approved' event into 'Planning Event', and the page must not keep
 * saying 'Event Approved' until it is reloaded by hand.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AssignedEventView } from './AssignedEventView'

// Each stub stands in for its real section and simply reports a change.
vi.mock('../../components/VenueBookingSection', () => ({
  VenueBookingSection: ({ onChanged }: { onChanged?: () => void }) => (
    <button type="button" onClick={() => onChanged?.()}>
      stub: venue requested
    </button>
  ),
}))
vi.mock('../../components/EquipmentRequirementsSection', () => ({
  EquipmentRequirementsSection: ({ onChanged }: { onChanged?: () => void }) => (
    <button type="button" onClick={() => onChanged?.()}>
      stub: equipment recorded
    </button>
  ),
}))
vi.mock('../../lib/events', async () => {
  const actual = await vi.importActual<typeof import('../../lib/events')>('../../lib/events')
  return { ...actual, getAssignedEvent: vi.fn() }
})

import { getAssignedEvent } from '../../lib/events'
import type { AssignedEventDetail } from '../../lib/events'

const mockGet = vi.mocked(getAssignedEvent)

const APPROVED = {
  id: 7,
  organiser_id: 1,
  coordinator_id: 2,
  coordinator: { id: 2, name: 'Sam Tan', email: 'sam@connectsphere.test' },
  name: 'Regional Partner Conference',
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
  equipment_requirements: null,
  equipment_items: [],
  special_arrangements: null,
  registration_enabled: false,
  registration_opens_at: null,
  registration_closes_at: null,
  status: 'event_approved',
  submitted_at: '2026-09-10T02:00:00Z',
  created_at: '2026-09-09T00:00:00Z',
  updated_at: '2026-09-10T02:00:00Z',
  organiser: { id: 1, name: 'Priya Menon', email: 'priya@connectsphere.test' },
  activity: [],
  change_requests: [],
  confirmation_outstanding: [],
} as AssignedEventDetail

function renderView() {
  return render(
    <MemoryRouter initialEntries={['/coordinator/events/7']}>
      <Routes>
        <Route path="/coordinator/events/:id" element={<AssignedEventView />} />
      </Routes>
    </MemoryRouter>,
  )
}

/** The status badge under the event's name. */
const badge = () => screen.getByRole('heading', { level: 1 }).parentElement!.querySelector('.badge')

beforeEach(() => {
  vi.clearAllMocks()
  mockGet.mockResolvedValue(APPROVED)
})

describe('the event page after something that can move its status', () => {
  it.each(['stub: venue requested', 'stub: equipment recorded'])(
    'shows Planning Event right after %s, without a reload',
    async (button) => {
      renderView()
      await screen.findByRole('heading', { level: 1, name: 'Regional Partner Conference' })
      expect(badge()).toHaveTextContent('Event Approved')

      mockGet.mockResolvedValue({ ...APPROVED, status: 'planning_event' })
      await userEvent.click(screen.getByRole('button', { name: button }))

      await waitFor(() => expect(badge()).toHaveTextContent('Planning Event'))
      expect(screen.getByRole('listitem', { current: 'step' })).toHaveTextContent('Planning Event')
    },
  )

  it('keeps what is on screen if the reload fails', async () => {
    renderView()
    await screen.findByRole('heading', { level: 1, name: 'Regional Partner Conference' })

    mockGet.mockRejectedValue(new Error('offline'))
    await userEvent.click(screen.getByRole('button', { name: 'stub: venue requested' }))

    await waitFor(() => expect(mockGet).toHaveBeenCalledTimes(2))
    expect(badge()).toHaveTextContent('Event Approved')
  })
})
