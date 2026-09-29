/**
 * Component tests for the navbar bell: unread badge, the dropdown preview,
 * mark all as read, and live notifications arriving from the stream.
 */
import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { badgeLabel } from '../lib/notifications'
import type { Notification } from '../lib/notifications'
import { NotificationsProvider } from '../notifications/NotificationsProvider'
import { NotificationBell } from './NotificationBell'

vi.mock('../lib/notifications', async (importActual) => ({
  ...(await importActual<typeof import('../lib/notifications')>()),
  listMyNotifications: vi.fn(),
  markNotificationsRead: vi.fn(),
  markAllNotificationsRead: vi.fn(),
  streamMyNotifications: vi.fn(),
}))

vi.mock('../auth/useAuth', () => ({
  useAuth: () => ({ user: { id: 3, role: 'coordinator' } }),
}))

import {
  listMyNotifications,
  markAllNotificationsRead,
  streamMyNotifications,
} from '../lib/notifications'

const mockList = vi.mocked(listMyNotifications)
const mockMarkAll = vi.mocked(markAllNotificationsRead)
const mockStream = vi.mocked(streamMyNotifications)

function notification(id: number, message: string, is_read = false): Notification {
  return {
    id,
    event_id: 10 + id,
    type: 'event_assigned',
    message,
    is_read,
    created_at: '2026-09-29T02:00:00Z',
  }
}

/** Whatever the provider passed as the stream's "new notification" callback. */
let pushLive: (n: Notification) => void = () => {}

function renderBell() {
  return render(
    <MemoryRouter>
      <NotificationsProvider>
        <NotificationBell />
      </NotificationsProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockList.mockResolvedValue([
    notification(2, 'Assigned: Careers Fair'),
    notification(1, 'Assigned: Alumni Dinner', true),
  ])
  mockMarkAll.mockResolvedValue({ updated: 1 })
  mockStream.mockImplementation((onNotification) => {
    pushLive = onNotification
    return new Promise(() => {})
  })
})

describe('badge', () => {
  it('shows the unread count in the button’s name', async () => {
    renderBell()

    expect(await screen.findByRole('button', { name: 'Notifications, 1 unread' })).toBeInTheDocument()
  })

  it('caps the badge at 99+', () => {
    expect(badgeLabel(5)).toBe('5')
    expect(badgeLabel(120)).toBe('99+')
  })

  it('goes up when a notification arrives live, without a reload', async () => {
    renderBell()
    await screen.findByRole('button', { name: 'Notifications, 1 unread' })

    act(() => pushLive(notification(3, 'Assigned: Robotics Summit')))

    expect(screen.getByRole('button', { name: 'Notifications, 2 unread' })).toBeInTheDocument()
  })
})

describe('dropdown', () => {
  it('opens with the latest notifications and a link to the full page', async () => {
    renderBell()
    const bell = await screen.findByRole('button', { name: 'Notifications, 1 unread' })

    await userEvent.click(bell)

    expect(bell).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('Assigned: Careers Fair')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'View all notifications' })).toHaveAttribute(
      'href',
      '/notifications',
    )
  })

  it('mark all as read clears the badge', async () => {
    renderBell()
    await userEvent.click(await screen.findByRole('button', { name: 'Notifications, 1 unread' }))

    await userEvent.click(screen.getByRole('button', { name: 'Mark all as read' }))

    expect(mockMarkAll).toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Notifications' })).toBeInTheDocument()
  })

  it('closes on Escape and returns focus to the bell', async () => {
    renderBell()
    const bell = await screen.findByRole('button', { name: 'Notifications, 1 unread' })
    await userEvent.click(bell)

    await userEvent.keyboard('{Escape}')

    expect(screen.queryByText('View all notifications')).not.toBeInTheDocument()
    expect(bell).toHaveFocus()
  })
})
