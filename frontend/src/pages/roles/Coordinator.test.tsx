/**
 * Component tests for the Coordinator's availability toggle and history
 * -- the frontend half of the "Mark myself unavailable" story:
 *
 *   As an Event Coordinator, I want to mark myself as unavailable, so
 *   that my assigned events are automatically reassigned to another
 *   coordinator.
 *
 * The reassignment itself is entirely server-side (see
 * backend/tests/test_coordinator_availability.py); these tests cover only
 * what the screen does -- reflects current availability, lets it be
 * toggled, and records the change -- not whether the toggle actually
 * reassigns anything. The assignment notification (AC2) is shown by the
 * navbar bell and /notifications -- see NotificationBell.test.tsx and
 * pages/Notifications.test.tsx.
 */
import { render, screen, waitFor } from '@testing-library/react'
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
