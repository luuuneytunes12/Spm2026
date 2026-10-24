/** SCRUM-30 AC1-AC4 and AC6 on the Organiser's event page and list. */
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { EventView } from './EventView'
import { ApiError } from '../../lib/api'

vi.mock('../../lib/events', async () => {
  const actual = await vi.importActual<typeof import('../../lib/events')>('../../lib/events')
  return { ...actual, getEvent: vi.fn(), getOwnEventActivity: vi.fn(), listOwnChangeRequests: vi.fn() }
})
vi.mock('../../lib/eventProgress', async () => {
  const actual = await vi.importActual<typeof import('../../lib/eventProgress')>('../../lib/eventProgress')
  return { ...actual, getOwnEventProgress: vi.fn() }
})

import { EVENT_STATUS_LABELS, getEvent, getOwnEventActivity, listOwnChangeRequests } from '../../lib/events'
import type { EventDetail } from '../../lib/events'
import { getOwnEventProgress } from '../../lib/eventProgress'

const BASE = {
  id: 7, organiser_id: 1, coordinator_id: null, coordinator: null, name: 'Robotics Summit',
  event_type: 'conference', purpose: 'p', description: null, programme: null,
  proposed_start: '2026-11-02T09:00:00Z', proposed_end: '2026-11-02T17:00:00Z', expected_attendance: 120,
  venue_requirements: null, room_layout_preference: null, accessibility_needs: null, equipment_requirements: null,
  equipment_items: [], special_arrangements: null, registration_enabled: false,
  status: 'under_review', submitted_at: '2026-09-10T02:00:00Z', created_at: '2026-09-09T00:00:00Z', updated_at: '2026-09-10T02:00:00Z',
} as unknown as EventDetail

function renderView() {
  return render(
    <MemoryRouter initialEntries={['/organiser/events/7']}>
      <Routes>
        <Route path="/organiser/events/:id" element={<EventView />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(getOwnEventActivity).mockResolvedValue([])
  vi.mocked(listOwnChangeRequests).mockResolvedValue([])
  vi.mocked(getOwnEventProgress).mockResolvedValue({
    status: 'planning_event' as never, venue_bookings: [], equipment: [],
    safety_check: { stage: 'Not requested', sent_back: null },
  })
})

describe('Organiser event page status', () => {
  it('ac2: the eleven status names are spelled exactly as the DoD', () => {
    expect(Object.values(EVENT_STATUS_LABELS)).toEqual([
      'Draft', 'Submitted – Awaiting Coordinator', 'Under Review', 'Awaiting Organiser Reply', 'Event Approved',
      'Planning Event', 'Awaiting Safety Check', 'Safety Check Passed (Event Confirmed)', 'Event Completed',
      'Event Rejected', 'Event Cancelled',
    ])
  })

  it.each(Object.entries(EVENT_STATUS_LABELS).filter(([s]) => s !== 'draft'))(
    'ac1: a %s event shows its status as "%s"',
    async (status, label) => {
      vi.mocked(getEvent).mockResolvedValue({ ...BASE, status } as EventDetail)
      renderView()
      const heading = await screen.findByRole('heading', { level: 1, name: 'Robotics Summit' })
      expect(heading.parentElement).toHaveTextContent(label)
    },
  )

  it('ac4: the history lists each change with its time, newest first', async () => {
    vi.mocked(getEvent).mockResolvedValue(BASE)
    vi.mocked(getOwnEventActivity).mockResolvedValue([
      { from_status: 'submitted_awaiting_coordinator', to_status: 'under_review', note: null, changed_by_name: 'Lena Lead', created_at: '2026-09-11T03:00:00Z' },
      { from_status: 'draft', to_status: 'submitted_awaiting_coordinator', note: null, changed_by_name: 'Olivia', created_at: '2026-09-10T02:00:00Z' },
    ])
    renderView()
    const log = await screen.findByRole('list', { name: 'Activity log' })
    const items = within(log).getAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(items[0]).toHaveTextContent('Submitted – Awaiting Coordinator')
    expect(items[0]).toHaveTextContent('Under Review')
    expect(items[0]).toHaveTextContent('Lena Lead')
    expect(items[0]).toHaveTextContent(/2026/)
    expect(items[1]).toHaveTextContent('Draft')
  })

  it('ac3: reopening the page shows the new status', async () => {
    vi.mocked(getEvent).mockResolvedValueOnce(BASE)
    const first = renderView()
    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent('Robotics Summit')
    expect(screen.getAllByText('Under Review').length).toBeGreaterThan(0)
    first.unmount()
    vi.mocked(getEvent).mockResolvedValueOnce({ ...BASE, status: 'event_approved' } as EventDetail)
    renderView()
    expect((await screen.findAllByText('Event Approved')).length).toBeGreaterThan(0)
  })

  it('ac5: a Planning Event shows its planning progress, and an Under Review one does not', async () => {
    vi.mocked(getEvent).mockResolvedValue({ ...BASE, status: 'planning_event' } as EventDetail)
    const view = renderView()
    expect(await screen.findByRole('heading', { name: 'Planning progress' })).toBeInTheDocument()
    view.unmount()
    vi.mocked(getEvent).mockResolvedValue(BASE)
    renderView()
    await screen.findByRole('heading', { level: 1, name: 'Robotics Summit' })
    expect(screen.queryByRole('heading', { name: 'Planning progress' })).not.toBeInTheDocument()
  })

  it("ac6: another Organiser's event is refused and nothing of it is shown", async () => {
    vi.mocked(getEvent).mockRejectedValue(new ApiError(404, 'Event not found'))
    renderView()
    expect(await screen.findByRole('alert')).toHaveTextContent('Event not found')
    expect(screen.queryByRole('heading', { name: 'Robotics Summit' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Planning progress' })).not.toBeInTheDocument()
  })
})
