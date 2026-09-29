/**
 * Component tests for the /notifications page: unread state, multi-select,
 * select all, and marking as read. Rendered inside the real
 * NotificationsProvider with the API mocked, so the page is exercised
 * against the same shared state the navbar bell reads.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../lib/api'
import type { Notification } from '../lib/notifications'
import { NotificationsProvider } from '../notifications/NotificationsProvider'
import { Notifications } from './Notifications'

vi.mock('../lib/notifications', async (importActual) => ({
  ...(await importActual<typeof import('../lib/notifications')>()),
  listMyNotifications: vi.fn(),
  markNotificationsRead: vi.fn(),
  markAllNotificationsRead: vi.fn(),
  // Never resolves: no live events in these tests.
  streamMyNotifications: vi.fn(() => new Promise(() => {})),
}))

vi.mock('../auth/useAuth', () => ({
  useAuth: () => ({ user: { id: 3, role: 'coordinator' } }),
}))

import {
  listMyNotifications,
  markAllNotificationsRead,
  markNotificationsRead,
} from '../lib/notifications'

const mockList = vi.mocked(listMyNotifications)
const mockMarkRead = vi.mocked(markNotificationsRead)
const mockMarkAll = vi.mocked(markAllNotificationsRead)

function notification(id: number, message: string, is_read = false): Notification {
  return {
    id,
    event_id: 10 + id,
    type: 'event_assigned',
    message,
    is_read,
    created_at: new Date().toISOString(),
  }
}

const ITEMS = [
  notification(3, 'Assigned: Robotics Summit'),
  notification(2, 'Assigned: Careers Fair'),
  notification(1, 'Assigned: Alumni Dinner', true),
]

function renderPage() {
  return render(
    <MemoryRouter>
      <NotificationsProvider>
        <Notifications />
      </NotificationsProvider>
    </MemoryRouter>,
  )
}

function row(message: string): HTMLElement {
  return screen.getByText(message).closest('li')!
}

beforeEach(() => {
  vi.clearAllMocks()
  mockList.mockResolvedValue(ITEMS)
  mockMarkRead.mockResolvedValue({ updated: 1 })
  mockMarkAll.mockResolvedValue({ updated: 2 })
})

describe('listing', () => {
  it('shows every notification, marking the unread ones', async () => {
    renderPage()

    expect(await screen.findByText('Assigned: Robotics Summit')).toBeInTheDocument()
    expect(screen.getByText('2 unread')).toBeInTheDocument()
    expect(row('Assigned: Robotics Summit')).toHaveClass('is-unread')
    expect(row('Assigned: Alumni Dinner')).not.toHaveClass('is-unread')
  })

  it('links each notification to its event for the reader’s role', async () => {
    renderPage()

    const link = within(await screen.findByText('Assigned: Robotics Summit').then((el) => el.closest('li')!))
      .getByRole('link', { name: 'View event' })
    expect(link).toHaveAttribute('href', '/coordinator/events/13')
  })

  it('shows an empty state when there are none', async () => {
    mockList.mockResolvedValue([])
    renderPage()

    expect(await screen.findByText('No notifications yet.')).toBeInTheDocument()
  })

  it('the Unread filter hides read notifications, with its own empty state', async () => {
    renderPage()
    await screen.findByText('Assigned: Robotics Summit')

    await userEvent.click(screen.getByRole('tab', { name: /Unread/ }))
    expect(screen.queryByText('Assigned: Alumni Dinner')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Mark all as read' }))
    expect(await screen.findByText('No unread notifications.')).toBeInTheDocument()
  })
})

describe('marking as read', () => {
  it('marks only the selected notifications', async () => {
    renderPage()
    await screen.findByText('Assigned: Robotics Summit')

    await userEvent.click(within(row('Assigned: Careers Fair')).getByRole('checkbox'))
    await userEvent.click(screen.getByRole('button', { name: 'Mark selected as read (1)' }))

    expect(mockMarkRead).toHaveBeenCalledWith([2])
    expect(row('Assigned: Careers Fair')).not.toHaveClass('is-unread')
    expect(row('Assigned: Robotics Summit')).toHaveClass('is-unread')
  })

  it('disables "Mark selected as read" until something unread is selected', async () => {
    renderPage()
    await screen.findByText('Assigned: Robotics Summit')

    expect(screen.getByRole('button', { name: 'Mark selected as read' })).toBeDisabled()
    // Selecting only an already-read one still leaves nothing to do.
    await userEvent.click(within(row('Assigned: Alumni Dinner')).getByRole('checkbox'))
    expect(screen.getByRole('button', { name: 'Mark selected as read' })).toBeDisabled()
  })

  it('select all picks every visible row, and is partially checked in between', async () => {
    renderPage()
    await screen.findByText('Assigned: Robotics Summit')
    const selectAll = screen.getByRole('checkbox', { name: 'Select all' })

    await userEvent.click(within(row('Assigned: Careers Fair')).getByRole('checkbox'))
    expect(selectAll).toHaveProperty('indeterminate', true)

    await userEvent.click(selectAll)
    expect(selectAll).toBeChecked()
    expect(selectAll).toHaveProperty('indeterminate', false)
    for (const n of ITEMS) {
      expect(within(row(n.message)).getByRole('checkbox')).toBeChecked()
    }

    await userEvent.click(screen.getByRole('button', { name: 'Mark selected as read (2)' }))
    expect(mockMarkRead).toHaveBeenCalledWith([3, 2])
    expect(screen.getByText("You're all caught up.")).toBeInTheDocument()
  })

  it('mark all as read clears every unread notification', async () => {
    renderPage()
    await screen.findByText('Assigned: Robotics Summit')

    await userEvent.click(screen.getByRole('button', { name: 'Mark all as read' }))

    expect(mockMarkAll).toHaveBeenCalled()
    expect(screen.getByText("You're all caught up.")).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Mark all as read' })).toBeDisabled()
  })

  it('puts the unread state back and explains why when the server refuses', async () => {
    mockMarkRead.mockRejectedValue(new ApiError(500, 'Something went wrong'))
    renderPage()
    await screen.findByText('Assigned: Robotics Summit')

    await userEvent.click(within(row('Assigned: Careers Fair')).getByRole('checkbox'))
    await userEvent.click(screen.getByRole('button', { name: 'Mark selected as read (1)' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Something went wrong')
    await waitFor(() => expect(row('Assigned: Careers Fair')).toHaveClass('is-unread'))
  })
})
