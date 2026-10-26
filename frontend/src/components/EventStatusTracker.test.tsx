/** SCRUM-30 AC5: the Organiser sees Venue Booking, equipment and Safety Check
 *  progress while the Event is being planned, and why a Safety Check sent it back. */
import { render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { EventStatusTracker } from './EventStatusTracker'
import { ApiError } from '../lib/api'
import { EventStatus } from '../lib/events'
import type { EventProgress } from '../lib/eventProgress'

vi.mock('../lib/eventProgress', async () => {
  const actual = await vi.importActual<typeof import('../lib/eventProgress')>('../lib/eventProgress')
  return { ...actual, getOwnEventProgress: vi.fn() }
})
import { getOwnEventProgress } from '../lib/eventProgress'

const mockProgress = vi.mocked(getOwnEventProgress)

const PROGRESS: EventProgress = {
  status: EventStatus.PLANNING_EVENT,
  venue_bookings: [
    { id: 1, venue_name: 'Marina Hall', status: 'approved', start_time: '2026-11-02T09:00:00Z', end_time: '2026-11-02T17:00:00Z', needs_replacement: false, replaces_venue_name: null },
    { id: 2, venue_name: 'Harbour Hall', status: 'hold_expired', start_time: '2026-11-02T09:00:00Z', end_time: '2026-11-02T17:00:00Z', needs_replacement: true, replaces_venue_name: null },
    { id: 3, venue_name: 'Garden Hall', status: 'pending', start_time: '2026-11-02T09:00:00Z', end_time: '2026-11-02T17:00:00Z', needs_replacement: false, replaces_venue_name: 'Harbour Hall' },
  ],
  equipment: [{ id: 9, equipment_name: 'Projector', quantity_requested: 2, status: 'reserved' }],
  safety_check: { stage: 'Not requested', sent_back: null },
}

beforeEach(() => {
  vi.clearAllMocks()
  mockProgress.mockResolvedValue(PROGRESS)
})

describe('EventStatusTracker', () => {
  it('ac5: shows each venue booking with its status, and flags one needing a replacement', async () => {
    render(<EventStatusTracker eventId={7} status={EventStatus.PLANNING_EVENT} />)
    const list = await screen.findByRole('list', { name: 'Venue bookings' })
    const items = within(list).getAllByRole('listitem')
    expect(items).toHaveLength(3)
    expect(items[0]).toHaveTextContent('Marina Hall')
    expect(items[0]).toHaveTextContent('Approved')
    expect(items[1]).toHaveTextContent('Hold Expired')
    expect(items[1]).toHaveTextContent('A replacement venue is needed')
    expect(items[0]).not.toHaveTextContent('replacement venue is needed')
    expect(items[2]).toHaveTextContent('Replacement for Harbour Hall')
  })

  it('ac5: shows equipment progress and the Safety Check stage', async () => {
    render(<EventStatusTracker eventId={7} status={EventStatus.PLANNING_EVENT} />)
    const equipment = await screen.findByRole('list', { name: 'Equipment progress' })
    expect(equipment).toHaveTextContent('Projector')
    expect(equipment).toHaveTextContent('Reserved')
    expect(screen.getByText('Not requested')).toBeInTheDocument()
  })

  it('ac5: shows the reason a Safety Check sent the event back', async () => {
    mockProgress.mockResolvedValue({
      ...PROGRESS,
      safety_check: {
        stage: 'Sent back',
        sent_back: { result: 'Changes Requested', reason: 'Fire exits are blocked.', decided_by_name: 'Sam Safety', decided_at: '2026-10-01T03:00:00Z', items_to_review: [] },
      },
    })
    render(<EventStatusTracker eventId={7} status={EventStatus.PLANNING_EVENT} />)
    const note = await screen.findByRole('note')
    expect(note).toHaveTextContent('Changes Requested')
    expect(note).toHaveTextContent('Sam Safety')
    expect(note).toHaveTextContent('Reason: Fire exits are blocked.')
  })

  it('ac5: says so when nothing is arranged yet', async () => {
    mockProgress.mockResolvedValue({ ...PROGRESS, venue_bookings: [], equipment: [] })
    render(<EventStatusTracker eventId={7} status={EventStatus.PLANNING_EVENT} />)
    expect(await screen.findByText('No venue has been requested yet.')).toBeInTheDocument()
    expect(screen.getByText('No equipment was requested.')).toBeInTheDocument()
  })

  it('shows nothing, and asks for nothing, before planning starts', () => {
    const { container } = render(<EventStatusTracker eventId={7} status={EventStatus.UNDER_REVIEW} />)
    expect(container).toBeEmptyDOMElement()
    expect(mockProgress).not.toHaveBeenCalled()
  })

  it('ac6: a refused load is shown as an error, with no progress leaked', async () => {
    mockProgress.mockRejectedValue(new ApiError(404, 'Event not found'))
    render(<EventStatusTracker eventId={7} status={EventStatus.PLANNING_EVENT} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Event not found')
    expect(screen.queryByRole('heading', { name: 'Planning progress' })).not.toBeInTheDocument()
  })
})
