/**
 * Component tests for the Drafts / Submitted Requests list.
 *
 * Traceability (see docs/test-cases-organiser-event-requests.md):
 *   TC-S2-3b -- Story 2 AC3 "it appears on the Submitted Requests page"
 *
 * Drafts and submitted requests are the same rows at different stages, so
 * this page is two tabs over one table filtered by `status`. These tests
 * check the tabs ask the API for the right status and render what comes
 * back -- the status transition itself is covered by
 * backend/tests/test_events.py.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MyRequests } from './MyRequests'

vi.mock('../../lib/events', async () => {
  const actual = await vi.importActual<typeof import('../../lib/events')>('../../lib/events')
  return { ...actual, listMyEvents: vi.fn() }
})

import { listMyEvents } from '../../lib/events'
import type { EventSummary } from '../../lib/events'

const mockList = vi.mocked(listMyEvents)

const DRAFT: EventSummary = {
  id: 1,
  name: 'Regional Partner Conference',
  event_type: 'conference',
  proposed_start: null,
  proposed_end: null,
  expected_attendance: null,
  status: 'draft',
  submitted_at: null,
  updated_at: '2026-09-10T00:00:00Z',
}

const SUBMITTED: EventSummary = {
  ...DRAFT,
  id: 2,
  name: 'Robotics Summit',
  status: 'submitted',
  submitted_at: '2026-09-10T02:00:00Z',
  expected_attendance: 80,
}

function renderAt(path = '/organiser/events') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <MyRequests />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockList.mockResolvedValue([])
})

describe('Story 2 AC3 - submitted requests appear on their own page', () => {
  it('TC-S2-3b: opens on Drafts and asks the API only for drafts', async () => {
    mockList.mockResolvedValue([DRAFT])
    renderAt()

    await waitFor(() => expect(mockList).toHaveBeenCalledWith('draft'))
    expect(mockList).not.toHaveBeenCalledWith('submitted')
    expect(await screen.findByText('Regional Partner Conference')).toBeInTheDocument()
  })

  it('TC-S2-3b: switching to Submitted Requests refetches with that status', async () => {
    const user = userEvent.setup()
    mockList.mockResolvedValue([DRAFT])
    renderAt()
    await waitFor(() => expect(mockList).toHaveBeenCalledWith('draft'))

    mockList.mockResolvedValue([SUBMITTED])
    await user.click(screen.getByRole('tab', { name: 'Submitted Requests' }))

    await waitFor(() => expect(mockList).toHaveBeenCalledWith('submitted'))
    expect(await screen.findByText('Robotics Summit')).toBeInTheDocument()
    // The draft is not on this tab.
    expect(screen.queryByText('Regional Partner Conference')).not.toBeInTheDocument()
  })

  it('can be linked to directly, which is where the form redirects after submitting', async () => {
    mockList.mockResolvedValue([SUBMITTED])
    renderAt('/organiser/events?tab=submitted')

    await waitFor(() => expect(mockList).toHaveBeenCalledWith('submitted'))
    expect(screen.getByRole('tab', { name: 'Submitted Requests' })).toHaveAttribute(
      'aria-selected',
      'true',
    )
  })

  it('offers editing for a draft and read-only viewing once submitted', async () => {
    const user = userEvent.setup()
    mockList.mockResolvedValue([DRAFT])
    renderAt()
    const draftRow = await screen.findByRole('listitem')
    expect(within(draftRow).getByRole('link', { name: /continue editing/i })).toHaveAttribute(
      'href',
      '/organiser/events/1/edit',
    )

    mockList.mockResolvedValue([SUBMITTED])
    await user.click(screen.getByRole('tab', { name: 'Submitted Requests' }))

    const submittedRow = await screen.findByRole('listitem')
    expect(within(submittedRow).getByRole('link', { name: /view/i })).toHaveAttribute(
      'href',
      '/organiser/events/2',
    )
    expect(within(submittedRow).queryByRole('link', { name: /continue editing/i })).toBeNull()
  })
})

describe('drafts that were never named', () => {
  it('labels a nameless draft rather than rendering a blank row', async () => {
    mockList.mockResolvedValue([{ ...DRAFT, name: null }])
    renderAt()

    expect(await screen.findByText('Untitled draft')).toBeInTheDocument()
  })
})

describe('empty states', () => {
  it('invites the organiser to start one when there are no drafts', async () => {
    renderAt()
    expect(await screen.findByText('No drafts yet.')).toBeInTheDocument()
  })

  it('explains the submitted tab differently', async () => {
    const user = userEvent.setup()
    renderAt()
    await screen.findByText('No drafts yet.')

    await user.click(screen.getByRole('tab', { name: 'Submitted Requests' }))

    expect(await screen.findByText('Nothing submitted yet.')).toBeInTheDocument()
  })
})
