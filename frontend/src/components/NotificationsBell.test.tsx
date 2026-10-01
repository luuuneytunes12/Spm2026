/**
 * Component tests for the navbar's notifications bell dropdown -- the
 * "click the bell icon, see a dropdown of notifications" entry point onto
 * the same role-agnostic list the full /notifications page shows (see
 * pages/Notifications.test.tsx).
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { NotificationsBell } from './NotificationsBell'

vi.mock('../lib/notifications', () => ({ listMyNotifications: vi.fn() }))
vi.mock('../auth/useAuth', () => ({
  useAuth: () => ({ user: { role: 'organiser' } }),
}))

import { listMyNotifications } from '../lib/notifications'
import type { Notification } from '../lib/notifications'

const mockListNotifications = vi.mocked(listMyNotifications)

function renderBell() {
  return render(
    <MemoryRouter>
      <NotificationsBell />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('AC: clicking the bell shows a dropdown of notifications', () => {
  it('does not show the dropdown until the bell is clicked', async () => {
    mockListNotifications.mockResolvedValue([])
    renderBell()

    await waitFor(() => expect(mockListNotifications).toHaveBeenCalled())
    expect(screen.queryByRole('menu', { name: 'Notifications' })).not.toBeInTheDocument()
  })

  it('opens a dropdown of notifications on click', async () => {
    const notifications: Notification[] = [
      {
        id: 1,
        event_id: 7,
        type: 'event_coordinator_assigned',
        message: "Sam Tan (sam@connectsphere.test) is now coordinating 'Robotics Summit'.",
        is_read: false,
        created_at: '2026-09-10T02:00:00Z',
      },
    ]
    mockListNotifications.mockResolvedValue(notifications)
    renderBell()

    await userEvent.click(await screen.findByRole('button', { name: /Notifications/ }))

    expect(screen.getByRole('menu', { name: 'Notifications' })).toBeInTheDocument()
    expect(
      screen.getByText("Sam Tan (sam@connectsphere.test) is now coordinating 'Robotics Summit'."),
    ).toBeInTheDocument()
  })

  it('shows an empty state in the dropdown when there are none', async () => {
    mockListNotifications.mockResolvedValue([])
    renderBell()

    await userEvent.click(await screen.findByRole('button', { name: 'Notifications' }))

    expect(screen.getByText('No notifications yet.')).toBeInTheDocument()
  })

  it('shows a badge with the notification count', async () => {
    mockListNotifications.mockResolvedValue([
      {
        id: 1,
        event_id: 7,
        type: 'event_coordinator_assigned',
        message: 'first',
        is_read: false,
        created_at: '2026-09-10T02:00:00Z',
      },
      {
        id: 2,
        event_id: 7,
        type: 'event_coordinator_assigned',
        message: 'second',
        is_read: false,
        created_at: '2026-09-10T03:00:00Z',
      },
    ])
    renderBell()

    expect(await screen.findByText('2')).toBeInTheDocument()
  })

  it('closes the dropdown when clicked again', async () => {
    mockListNotifications.mockResolvedValue([])
    renderBell()

    const button = await screen.findByRole('button', { name: 'Notifications' })
    await userEvent.click(button)
    expect(screen.getByRole('menu', { name: 'Notifications' })).toBeInTheDocument()

    await userEvent.click(button)
    expect(screen.queryByRole('menu', { name: 'Notifications' })).not.toBeInTheDocument()
  })

  it("links a notification tied to an event to that event's page", async () => {
    mockListNotifications.mockResolvedValue([
      {
        id: 1,
        event_id: 7,
        type: 'event_coordinator_assigned',
        message: "Sam Tan (sam@connectsphere.test) is now coordinating 'Robotics Summit'.",
        is_read: false,
        created_at: '2026-09-10T02:00:00Z',
      },
    ])
    renderBell()

    await userEvent.click(await screen.findByRole('button', { name: /Notifications/ }))

    const links = screen.getAllByRole('link')
    expect(links.some((link) => link.getAttribute('href') === '/organiser/events/7')).toBe(true)
  })

  it('links to the full notifications page', async () => {
    mockListNotifications.mockResolvedValue([])
    renderBell()

    await userEvent.click(await screen.findByRole('button', { name: 'Notifications' }))

    expect(screen.getByRole('link', { name: 'View all notifications' })).toHaveAttribute(
      'href',
      '/notifications',
    )
  })
})
