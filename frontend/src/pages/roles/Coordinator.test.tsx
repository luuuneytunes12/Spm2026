/**
 * Component tests for the Coordinator's availability toggle and history
 * -- the frontend half of SCRUM-24:
 *
 *   As an Event Coordinator, I want to mark myself as unavailable, so
 *   that I stop receiving new ones until I'm available again.
 *
 * Whether an unavailable Coordinator is actually left out of new
 * assignments is server-side (see
 * backend/tests/test_coordinator_availability.py); these tests cover only
 * what the screen does -- reflects current availability, lets it be
 * toggled, says truthfully what that means, and shows the recorded
 * history. Marking unavailable does not move events already assigned.
 */
import { render as rtlRender, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/api'
import { Coordinator } from './Coordinator'

vi.mock('../../lib/coordinators', () => ({
  setMyAvailability: vi.fn(),
  getMyAvailabilityHistory: vi.fn(),
}))

const mockRefreshUser = vi.fn()
let mockUser: { is_available: boolean } | null = { is_available: true }

vi.mock('../../auth/useAuth', () => ({
  useAuth: () => ({ user: mockUser, refreshUser: mockRefreshUser }),
}))

// The page now also carries the landing tiles, which link around the app and
// show the unread count from the navbar's provider. Neither is under test here.
vi.mock('../../notifications/useNotifications', () => ({
  useNotifications: () => ({ unreadCount: 0 }),
}))

function render(ui: React.ReactElement) {
  // `wrapper` (not wrapping `ui`) so a later `rerender` keeps the router too.
  return rtlRender(ui, { wrapper: MemoryRouter })
}

import { getMyAvailabilityHistory, setMyAvailability } from '../../lib/coordinators'
import type { AvailabilityHistoryEntry } from '../../lib/coordinators'

const mockSetAvailability = vi.mocked(setMyAvailability)
const mockGetAvailabilityHistory = vi.mocked(getMyAvailabilityHistory)

beforeEach(() => {
  vi.clearAllMocks()
  mockUser = { is_available: true }
  mockGetAvailabilityHistory.mockResolvedValue([])
})

describe('AC: available Coordinators can mark themselves unavailable', () => {
  it('shows "Available" and offers to mark unavailable when the caller is available', async () => {
    render(<Coordinator />)

    expect(await screen.findByText('Available')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Mark myself unavailable' })).toBeInTheDocument()
  })

  it('calls the API and refreshes the signed-in user when toggled off', async () => {
    mockSetAvailability.mockResolvedValue({
      id: 1,
      name: 'Sam Tan',
      email: 'sam@connectsphere.test',
      role: 'coordinator',
      is_available: false,
      created_at: '2026-09-10T00:00:00Z',
    })
    render(<Coordinator />)

    await userEvent.click(screen.getByRole('button', { name: 'Mark myself unavailable' }))

    await waitFor(() => expect(mockSetAvailability).toHaveBeenCalledWith(false))
    await waitFor(() => expect(mockRefreshUser).toHaveBeenCalled())
  })

  it('shows "Unavailable" and offers to mark available again once toggled off', async () => {
    mockUser = { is_available: false }
    render(<Coordinator />)

    expect(await screen.findByText('Unavailable')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Mark myself available' })).toBeInTheDocument()
  })

  it('shows an error rather than silently failing when the toggle is rejected', async () => {
    mockSetAvailability.mockRejectedValue(new ApiError(500, 'Something went wrong'))
    render(<Coordinator />)

    await userEvent.click(screen.getByRole('button', { name: 'Mark myself unavailable' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Something went wrong')
    // And the state was not optimistically flipped.
    expect(screen.getByText('Available')).toBeInTheDocument()
  })
})

describe('AC: an availability change is recorded with a timestamp, even with no active events', () => {
  it('shows an empty state rather than an empty box when there are none', async () => {
    render(<Coordinator />)

    expect(await screen.findByText('No changes yet.')).toBeInTheDocument()
  })

  it('renders each toggle in the history, newest first', async () => {
    const entries: AvailabilityHistoryEntry[] = [
      { id: 2, is_available: true, created_at: '2026-09-10T03:00:00Z' },
      { id: 1, is_available: false, created_at: '2026-09-10T02:00:00Z' },
    ]
    mockGetAvailabilityHistory.mockResolvedValue(entries)

    render(<Coordinator />)

    expect(await screen.findByText('Marked available')).toBeInTheDocument()
    expect(await screen.findByText('Marked unavailable')).toBeInTheDocument()
  })

  it('shows an error rather than silently failing when the history fails to load', async () => {
    mockGetAvailabilityHistory.mockRejectedValue(new ApiError(500, 'Something went wrong'))

    render(<Coordinator />)

    expect(await screen.findAllByRole('alert')).not.toHaveLength(0)
  })
})

describe('what "Unavailable" means, as the page words it', () => {
  it('says new events are not assigned and existing ones stay, once unavailable', () => {
    mockUser = { is_available: false }

    render(<Coordinator />)

    expect(screen.getByText(/will not be assigned new events/)).toBeInTheDocument()
    expect(screen.getByText(/Events already assigned to you stay with you/)).toBeInTheDocument()
    expect(screen.queryByText(/handed to another/)).not.toBeInTheDocument()
  })

  it('does not promise a hand-over when marking unavailable', () => {
    mockUser = { is_available: true }

    render(<Coordinator />)

    expect(screen.getByText('New submitted requests can be assigned to you.')).toBeInTheDocument()
    expect(screen.queryByText(/reassigned/)).not.toBeInTheDocument()
  })
})

describe('SCRUM-24 AC4 - the history follows the status without a page reload', () => {
  it('reloads the history when the availability changes, so the new entry appears at once', async () => {
    mockUser = { is_available: true }
    mockGetAvailabilityHistory.mockResolvedValueOnce([])
    const view = render(<Coordinator />)
    expect(await screen.findByText('No changes yet.')).toBeInTheDocument()

    // The toggle succeeded and the signed-in user was refreshed.
    mockUser = { is_available: false }
    mockGetAvailabilityHistory.mockResolvedValueOnce([
      { id: 1, is_available: false, created_at: '2026-09-30T09:00:00Z' },
    ])
    view.rerender(<Coordinator />)

    expect(await screen.findByText('Marked unavailable')).toBeInTheDocument()
    expect(screen.queryByText('No changes yet.')).not.toBeInTheDocument()
    expect(mockGetAvailabilityHistory).toHaveBeenCalledTimes(2)
  })

  it('does not reload the history when nothing about the availability changed', async () => {
    mockUser = { is_available: true }
    const view = render(<Coordinator />)
    await screen.findByText('No changes yet.')

    view.rerender(<Coordinator />)

    expect(mockGetAvailabilityHistory).toHaveBeenCalledTimes(1)
  })
})
