/**
 * Component tests for the Event Coordinator landing page.
 *
 * Traceability:
 *   AC1  welcomes the Coordinator with their name and role
 *   AC2  shortcuts to the assigned Events, Venues, Notifications and My Profile,
 *        each linking to its feature
 *   AC3  assigned Events and unread Notifications show how many there are
 *   AC4  with none, no number is shown on either
 */
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Role } from '../lib/roles'
import type { EventSummary } from '../lib/events'

vi.mock('../auth/useAuth', () => ({ useAuth: vi.fn() }))
vi.mock('../notifications/useNotifications', () => ({ useNotifications: vi.fn() }))
vi.mock('../lib/events', async (orig) => ({
  ...(await orig<typeof import('../lib/events')>()),
  listAssignedEvents: vi.fn(),
}))

import { useAuth } from '../auth/useAuth'
import { listAssignedEvents } from '../lib/events'
import { useNotifications } from '../notifications/useNotifications'
import { RoleLanding } from './RoleLanding'

function setUp({ assigned, unread, failing = false }: { assigned: number; unread: number; failing?: boolean }) {
  vi.mocked(useAuth).mockReturnValue({
    user: {
      id: 1,
      name: 'Sam Tan',
      email: 'sam@cs.local',
      role: Role.COORDINATOR,
      is_available: true,
      organisation: null,
      phone_country_code: null,
      phone_number: null,
      communication_preference: null,
      created_at: '2026-09-01T00:00:00Z',
    },
    permissions: [],
    loading: false,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    refreshUser: vi.fn(),
  } as unknown as ReturnType<typeof useAuth>)
  vi.mocked(useNotifications).mockReturnValue({
    items: [],
    unreadCount: unread,
    loading: false,
    error: null,
    markRead: vi.fn(),
    markAllRead: vi.fn(),
  })
  if (failing) vi.mocked(listAssignedEvents).mockRejectedValue(new Error('down'))
  else {
    vi.mocked(listAssignedEvents).mockResolvedValue(
      Array.from({ length: assigned }, (_, id) => ({ id }) as EventSummary),
    )
  }
  render(
    <MemoryRouter>
      <RoleLanding role={Role.COORDINATOR} />
    </MemoryRouter>,
  )
}

const tile = (name: RegExp) => screen.getByRole('link', { name })

describe('Event Coordinator landing page', () => {
  beforeEach(() => vi.clearAllMocks())

  it('AC1: welcomes the Coordinator with their name and role', () => {
    setUp({ assigned: 0, unread: 0 })
    expect(screen.getByRole('heading', { level: 1, name: 'Welcome back, Sam Tan' })).toBeInTheDocument()
    expect(screen.getByText('Event Coordinator')).toBeInTheDocument()
  })

  it('AC2: shows the four shortcuts and each links to its feature', () => {
    setUp({ assigned: 0, unread: 0 })
    expect(tile(/My Assigned Events/)).toHaveAttribute('href', '/coordinator/events')
    expect(tile(/Venues/)).toHaveAttribute('href', '/venues')
    expect(tile(/Notifications/)).toHaveAttribute('href', '/notifications')
    expect(tile(/My Profile/)).toHaveAttribute('href', '/profile')
  })

  it('AC3: shows how many events are assigned and how many notifications are unread', async () => {
    setUp({ assigned: 3, unread: 5 })
    await waitFor(() => expect(tile(/My Assigned Events/)).toHaveTextContent('3'))
    expect(screen.getByLabelText('3 items')).toBeInTheDocument()
    expect(screen.getByLabelText('5 unread')).toBeInTheDocument()
  })

  it('AC4: shows no number when there are none', async () => {
    setUp({ assigned: 0, unread: 0 })
    await waitFor(() => expect(listAssignedEvents).toHaveBeenCalled())
    expect(screen.queryByLabelText(/items|unread/)).not.toBeInTheDocument()
  })

  it('AC4: a failed count hides the number but keeps the shortcut', async () => {
    setUp({ assigned: 0, unread: 0, failing: true })
    await waitFor(() => expect(listAssignedEvents).toHaveBeenCalled())
    expect(tile(/My Assigned Events/)).toBeInTheDocument()
    expect(screen.queryByLabelText(/items/)).not.toBeInTheDocument()
  })

  it('AC2: the Venues and My Profile shortcuts never show a number', async () => {
    setUp({ assigned: 2, unread: 1 })
    await waitFor(() => expect(tile(/My Assigned Events/)).toHaveTextContent('2'))
    expect(tile(/Venues/)).not.toHaveTextContent(/\d/)
    expect(tile(/My Profile/)).not.toHaveTextContent(/\d/)
  })
})
