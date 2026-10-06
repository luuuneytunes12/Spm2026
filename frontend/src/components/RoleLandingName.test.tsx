/**
 * Every role's landing page welcomes the user by their FULL name.
 * (Previously only the first name was shown.)
 */
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ROLE_LABELS, Role } from '../lib/roles'

vi.mock('../auth/useAuth', () => ({ useAuth: vi.fn() }))
vi.mock('../notifications/useNotifications', () => ({ useNotifications: vi.fn() }))
// Tile counts call the API; a failure just hides the number, which is all this test needs.
vi.mock('../lib/api', async (orig) => ({
  ...(await orig<typeof import('../lib/api')>()),
  apiFetch: vi.fn().mockRejectedValue(new Error('offline')),
}))

import { useAuth } from '../auth/useAuth'
import { useNotifications } from '../notifications/useNotifications'
import { RoleLanding } from './RoleLanding'

function signedInAs(role: Role, name: string | null) {
  vi.mocked(useAuth).mockReturnValue({
    user: name === null ? null : { id: 1, name, email: 'x@cs.local', role },
    permissions: [],
    loading: false,
  } as unknown as ReturnType<typeof useAuth>)
  vi.mocked(useNotifications).mockReturnValue({
    items: [],
    unreadCount: 0,
    loading: false,
    error: null,
    markRead: vi.fn(),
    markAllRead: vi.fn(),
  })
}

describe('landing page welcome', () => {
  beforeEach(() => vi.clearAllMocks())

  it.each(Object.values(Role))('%s: shows the full name, not just the first', (role) => {
    signedInAs(role, 'Lena Marie Lead')
    render(
      <MemoryRouter>
        <RoleLanding role={role} />
      </MemoryRouter>,
    )
    expect(screen.getByRole('heading', { level: 1, name: 'Welcome back, Lena Marie Lead' })).toBeInTheDocument()
    expect(screen.getByText(ROLE_LABELS[role])).toBeInTheDocument()
  })

  it('a single-word name is shown as is', () => {
    signedInAs(Role.ATTENDEE, 'Madonna')
    render(
      <MemoryRouter>
        <RoleLanding role={Role.ATTENDEE} />
      </MemoryRouter>,
    )
    expect(screen.getByRole('heading', { level: 1, name: 'Welcome back, Madonna' })).toBeInTheDocument()
  })

  it('extra spaces around the name are trimmed', () => {
    signedInAs(Role.VENUE_STAFF, '  Ann Lee  ')
    render(
      <MemoryRouter>
        <RoleLanding role={Role.VENUE_STAFF} />
      </MemoryRouter>,
    )
    expect(screen.getByRole('heading', { level: 1, name: 'Welcome back, Ann Lee' })).toBeInTheDocument()
  })

  it('without a user it falls back to a plain welcome', () => {
    signedInAs(Role.ORGANISER, null)
    render(
      <MemoryRouter>
        <RoleLanding role={Role.ORGANISER} />
      </MemoryRouter>,
    )
    expect(screen.getByRole('heading', { level: 1, name: 'Welcome back' })).toBeInTheDocument()
  })
})
