/**
 * Component tests for the Event Coordinator Lead landing page.
 *
 * Traceability (see docs/test-cases-coordinator-lead-landing.md):
 *   AC1  welcomes the Lead with their full name and role
 *   AC2  shortcuts to Unassigned Requests, Coordinator Assignments,
 *        Notifications and My Profile, each linking to its feature
 *   AC3  Unassigned Requests and Notifications show how many there are
 *   AC4  with none, no number is shown on those shortcuts
 */
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Role } from '../lib/roles'
import type { LeadEvent } from '../lib/coordinatorLead'

vi.mock('../auth/useAuth', () => ({ useAuth: vi.fn() }))
vi.mock('../notifications/useNotifications', () => ({ useNotifications: vi.fn() }))
vi.mock('../lib/coordinatorLead', () => ({
  listUnassignedQueue: vi.fn(),
  listCoordinatorAssignments: vi.fn(),
}))

import { useAuth } from '../auth/useAuth'
import { listUnassignedQueue } from '../lib/coordinatorLead'
import { useNotifications } from '../notifications/useNotifications'
import { RoleLanding } from './RoleLanding'

function setUp({ unassigned, unread, failing = false }: { unassigned: number; unread: number; failing?: boolean }) {
  vi.mocked(useAuth).mockReturnValue({
    user: {
      id: 1,
      name: 'Lena Marie Lead',
      email: 'lead@cs.local',
      role: Role.COORDINATOR_LEAD,
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
  if (failing) vi.mocked(listUnassignedQueue).mockRejectedValue(new Error('down'))
  else {
    vi.mocked(listUnassignedQueue).mockResolvedValue(
      Array.from({ length: unassigned }, (_, id) => ({ id }) as LeadEvent),
    )
  }
  render(
    <MemoryRouter>
      <RoleLanding role={Role.COORDINATOR_LEAD} />
    </MemoryRouter>,
  )
}

const tile = (name: RegExp) => screen.getByRole('link', { name })

describe('Event Coordinator Lead landing page', () => {
  beforeEach(() => vi.clearAllMocks())

  it('AC1: welcomes the Lead with their full name and role', () => {
    setUp({ unassigned: 0, unread: 0 })
    expect(screen.getByRole('heading', { level: 1, name: 'Welcome back, Lena Marie Lead' })).toBeInTheDocument()
    expect(screen.getByText('Event Coordinator Lead')).toBeInTheDocument()
  })

  it('AC2: shows the four shortcuts and each links to its feature', () => {
    setUp({ unassigned: 0, unread: 0 })
    expect(tile(/Unassigned Requests/)).toHaveAttribute('href', '/coordinator-lead/queue')
    expect(tile(/Coordinator Assignments/)).toHaveAttribute('href', '/coordinator-lead/assignments')
    expect(tile(/Notifications/)).toHaveAttribute('href', '/notifications')
    expect(tile(/My Profile/)).toHaveAttribute('href', '/profile')
  })

  it('AC3: shows how many unassigned requests and unread notifications there are', async () => {
    setUp({ unassigned: 3, unread: 5 })
    await waitFor(() => expect(tile(/Unassigned Requests/)).toHaveTextContent('3'))
    expect(screen.getByLabelText('3 items')).toBeInTheDocument()
    expect(screen.getByLabelText('5 unread')).toBeInTheDocument()
  })

  it('AC4: shows no number when there are none', async () => {
    setUp({ unassigned: 0, unread: 0 })
    await waitFor(() => expect(listUnassignedQueue).toHaveBeenCalled())
    expect(screen.queryByLabelText(/items|unread/)).not.toBeInTheDocument()
  })

  it('AC4: a failed count hides the number but keeps the shortcut', async () => {
    setUp({ unassigned: 0, unread: 0, failing: true })
    await waitFor(() => expect(listUnassignedQueue).toHaveBeenCalled())
    expect(tile(/Unassigned Requests/)).toBeInTheDocument()
    expect(screen.queryByLabelText(/items/)).not.toBeInTheDocument()
  })

  it('AC2: the Assignments shortcut never shows a number', async () => {
    setUp({ unassigned: 4, unread: 0 })
    await waitFor(() => expect(screen.getByLabelText('4 items')).toBeInTheDocument())
    expect(tile(/Coordinator Assignments/)).not.toHaveTextContent(/\d/)
  })
})
