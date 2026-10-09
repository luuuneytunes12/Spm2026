/**
 * Component tests for the Event Organiser landing page.
 *
 * Traceability:
 *   AC1  welcomes the Organiser with their name and role
 *   AC2  shortcuts to a new Event Request, drafts, submitted requests,
 *        Notifications and My Profile, each linking to its feature
 *   AC3  drafts, submitted requests and unread Notifications show how many
 *   AC4  with none, no number is shown on any of them
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
  listMyEvents: vi.fn(),
}))

import { useAuth } from '../auth/useAuth'
import { listMyEvents } from '../lib/events'
import { useNotifications } from '../notifications/useNotifications'
import { RoleLanding } from './RoleLanding'

const summary = (id: number, status: string) => ({ id, status }) as EventSummary

function setUp({
  drafts,
  submitted,
  unread,
  failing = false,
}: {
  drafts: number
  submitted: number
  unread: number
  failing?: boolean
}) {
  vi.mocked(useAuth).mockReturnValue({
    user: {
      id: 1,
      name: 'Olivia Organiser',
      email: 'org@cs.local',
      role: Role.ORGANISER,
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
  const draftRows = Array.from({ length: drafts }, (_, i) => summary(i + 1, 'draft'))
  const submittedRows = Array.from({ length: submitted }, (_, i) =>
    summary(100 + i, 'submitted_awaiting_coordinator'),
  )
  if (failing) vi.mocked(listMyEvents).mockRejectedValue(new Error('down'))
  else {
    vi.mocked(listMyEvents).mockImplementation(async (status) =>
      status === 'draft' ? draftRows : [...draftRows, ...submittedRows],
    )
  }
  render(
    <MemoryRouter>
      <RoleLanding role={Role.ORGANISER} />
    </MemoryRouter>,
  )
}

const tile = (name: RegExp) => screen.getByRole('link', { name })

describe('Event Organiser landing page', () => {
  beforeEach(() => vi.clearAllMocks())

  it('AC1: welcomes the Organiser with their name and role', () => {
    setUp({ drafts: 0, submitted: 0, unread: 0 })
    expect(screen.getByRole('heading', { level: 1, name: 'Welcome back, Olivia Organiser' })).toBeInTheDocument()
    expect(screen.getByText('Event Organiser')).toBeInTheDocument()
  })

  it('AC2: shows the five shortcuts and each links to its feature', () => {
    setUp({ drafts: 0, submitted: 0, unread: 0 })
    expect(tile(/New Event Request/)).toHaveAttribute('href', '/organiser/events/new')
    expect(tile(/Drafted Requests/)).toHaveAttribute('href', '/organiser/events')
    expect(tile(/Submitted Requests/)).toHaveAttribute('href', '/organiser/events?tab=submitted')
    expect(tile(/Notifications/)).toHaveAttribute('href', '/notifications')
    expect(tile(/My Profile/)).toHaveAttribute('href', '/profile')
  })

  it('AC3: shows how many drafts, submitted requests and unread notifications there are', async () => {
    setUp({ drafts: 2, submitted: 3, unread: 5 })
    await waitFor(() => expect(tile(/Drafted Requests/)).toHaveTextContent('2'))
    await waitFor(() => expect(tile(/Submitted Requests/)).toHaveTextContent('3'))
    expect(tile(/Notifications/)).toHaveTextContent('5')
    expect(screen.getByLabelText('2 items')).toBeInTheDocument()
    expect(screen.getByLabelText('3 items')).toBeInTheDocument()
    expect(screen.getByLabelText('5 unread')).toBeInTheDocument()
  })

  it('AC3: the submitted count excludes drafts', async () => {
    setUp({ drafts: 4, submitted: 1, unread: 0 })
    await waitFor(() => expect(tile(/Submitted Requests/)).toHaveTextContent('1'))
    expect(tile(/Drafted Requests/)).toHaveTextContent('4')
  })

  it('AC4: shows no number when there are none', async () => {
    setUp({ drafts: 0, submitted: 0, unread: 0 })
    await waitFor(() => expect(listMyEvents).toHaveBeenCalled())
    expect(screen.queryByLabelText(/items|unread/)).not.toBeInTheDocument()
  })

  it('AC4: a failed count hides the number but keeps the shortcuts', async () => {
    setUp({ drafts: 0, submitted: 0, unread: 0, failing: true })
    await waitFor(() => expect(listMyEvents).toHaveBeenCalled())
    expect(tile(/Drafted Requests/)).toBeInTheDocument()
    expect(tile(/Submitted Requests/)).toBeInTheDocument()
    expect(screen.queryByLabelText(/items/)).not.toBeInTheDocument()
  })

  it('AC2: the New Event Request shortcut never shows a number', async () => {
    setUp({ drafts: 2, submitted: 3, unread: 1 })
    await waitFor(() => expect(tile(/Drafted Requests/)).toHaveTextContent('2'))
    expect(tile(/New Event Request/)).not.toHaveTextContent(/\d/)
    expect(tile(/My Profile/)).not.toHaveTextContent(/\d/)
  })
})
