/**
 * Component tests for the Coordinator's availability toggle and
 * notifications list -- the frontend half of the "Mark myself
 * unavailable" story:
 *
 *   As an Event Coordinator, I want to mark myself as unavailable, so
 *   that my assigned events are automatically reassigned to another
 *   coordinator.
 *
 * The reassignment itself is entirely server-side (see
 * backend/tests/test_coordinator_availability.py); these tests cover only
 * what the screen does -- reflects current availability, lets it be
 * toggled, and surfaces notifications -- not whether the toggle actually
 * reassigns anything.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/api'
import { Coordinator } from './Coordinator'

vi.mock('../../lib/coordinators', () => ({ setMyAvailability: vi.fn() }))
vi.mock('../../lib/notifications', () => ({ listMyNotifications: vi.fn() }))

const mockRefreshUser = vi.fn()
let mockUser: { is_available: boolean } | null = { is_available: true }

vi.mock('../../auth/useAuth', () => ({
  useAuth: () => ({ user: mockUser, refreshUser: mockRefreshUser }),
}))

import { setMyAvailability } from '../../lib/coordinators'
import { listMyNotifications } from '../../lib/notifications'
import type { Notification } from '../../lib/notifications'

const mockSetAvailability = vi.mocked(setMyAvailability)
const mockListNotifications = vi.mocked(listMyNotifications)

beforeEach(() => {
  vi.clearAllMocks()
  mockUser = { is_available: true }
  mockListNotifications.mockResolvedValue([])
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

describe('AC: the assigned coordinator receives a notification', () => {
  it('renders each notification message', async () => {
    const notifications: Notification[] = [
      {
        id: 1,
        event_id: 7,
        type: 'event_assigned',
        message: "You have been assigned to coordinate 'Robotics Summit'.",
        is_read: false,
        created_at: '2026-09-10T02:00:00Z',
      },
    ]
    mockListNotifications.mockResolvedValue(notifications)

    render(<Coordinator />)

    expect(
      await screen.findByText("You have been assigned to coordinate 'Robotics Summit'."),
    ).toBeInTheDocument()
  })

  it('shows an empty state rather than an empty box when there are none', async () => {
    render(<Coordinator />)

    expect(await screen.findByText('No notifications yet.')).toBeInTheDocument()
  })
})
