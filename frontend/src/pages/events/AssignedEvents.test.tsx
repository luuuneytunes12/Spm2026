/**
 * Component tests for the Coordinator's assigned-events list.
 *
 * Traceability (see docs/test-cases-coordinator-assigned-events.md):
 *   TC-S3-5c -- AC5 the list only ever offers events assigned to the caller
 *
 * The list is the way in to the detail screen, so these tests check it asks
 * the scoped endpoint and links each row to the right place. The scoping
 * itself is enforced server-side and covered by
 * backend/tests/test_assigned_events.py.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/api'
import { AssignedEvents } from './AssignedEvents'

vi.mock('../../lib/events', async () => {
  const actual = await vi.importActual<typeof import('../../lib/events')>('../../lib/events')
  return { ...actual, listAssignedEvents: vi.fn(), releaseAssignedEvent: vi.fn() }
})

import { listAssignedEvents, releaseAssignedEvent } from '../../lib/events'
import type { EventSummary } from '../../lib/events'

const mockList = vi.mocked(listAssignedEvents)
const mockRelease = vi.mocked(releaseAssignedEvent)

const ASSIGNED: EventSummary = {
  id: 7,
  name: 'Regional Partner Conference',
  event_type: 'conference',
  proposed_start: '2026-11-02T09:00:00Z',
  proposed_end: '2026-11-02T17:00:00Z',
  expected_attendance: 120,
  status: 'submitted',
  submitted_at: '2026-09-10T02:00:00Z',
  updated_at: '2026-09-10T02:00:00Z',
}

function renderList() {
  return render(
    <MemoryRouter initialEntries={['/coordinator/events']}>
      <AssignedEvents />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockList.mockResolvedValue([])
})

describe('marking unavailable for one event', () => {
  it('offers the action on an active event', async () => {
    mockList.mockResolvedValue([ASSIGNED])
    renderList()

    expect(
      await screen.findByRole('button', { name: 'Mark unavailable for this event' }),
    ).toBeInTheDocument()
  })

  it('does not offer it once the event has finished', async () => {
    mockList.mockResolvedValue([{ ...ASSIGNED, status: 'completed' }])
    renderList()

    await screen.findByText('Regional Partner Conference')
    expect(
      screen.queryByRole('button', { name: 'Mark unavailable for this event' }),
    ).not.toBeInTheDocument()
  })

  it('releases the event and drops it from the list', async () => {
    mockList.mockResolvedValue([ASSIGNED])
    mockRelease.mockResolvedValue({} as never)
    renderList()

    await userEvent.click(
      await screen.findByRole('button', { name: 'Mark unavailable for this event' }),
    )

    await waitFor(() => expect(mockRelease).toHaveBeenCalledWith(7))
    await waitFor(() =>
      expect(screen.queryByText('Regional Partner Conference')).not.toBeInTheDocument(),
    )
  })

  it('shows an error and keeps the row when releasing fails', async () => {
    mockList.mockResolvedValue([ASSIGNED])
    mockRelease.mockRejectedValue(new ApiError(409, "'completed' is not active, so it cannot be reassigned."))
    renderList()

    await userEvent.click(
      await screen.findByRole('button', { name: 'Mark unavailable for this event' }),
    )

    expect(await screen.findByRole('alert')).toHaveTextContent(
      "'completed' is not active, so it cannot be reassigned.",
    )
    expect(screen.getByText('Regional Partner Conference')).toBeInTheDocument()
  })
})

describe('AC5 - only events assigned to me', () => {
  it('TC-S3-5c: asks the scoped endpoint, with no "whose events" parameter', async () => {
    mockList.mockResolvedValue([ASSIGNED])
    renderList()

    await screen.findByText('Regional Partner Conference')
    expect(mockList).toHaveBeenCalledWith()
  })

  it('links each row to that event, and offers no other way in', async () => {
    mockList.mockResolvedValue([ASSIGNED])
    renderList()

    const row = await screen.findByRole('listitem')
    expect(within(row).getByRole('link', { name: /view details/i })).toHaveAttribute(
      'href',
      '/coordinator/events/7',
    )
    expect(within(row).queryByRole('link', { name: /edit/i })).toBeNull()
  })
})

describe('what the list shows', () => {
  it('summarises each event and its current status', async () => {
    mockList.mockResolvedValue([ASSIGNED])
    renderList()

    const row = await screen.findByRole('listitem')
    expect(within(row).getByText('Submitted')).toBeInTheDocument()
    expect(within(row).getByText(/120 attendees/)).toBeInTheDocument()
    expect(within(row).getByText(/conference/)).toBeInTheDocument()
  })

  it('explains the empty state rather than showing a blank page', async () => {
    renderList()

    expect(await screen.findByText('Nothing assigned to you yet.')).toBeInTheDocument()
  })

  it('reports a server it could not reach', async () => {
    mockList.mockRejectedValue(new Error('network down'))
    renderList()

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Could not reach the server. Is the backend running?',
    )
  })
})
