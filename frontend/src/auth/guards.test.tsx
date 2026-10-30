/**
 * The route guards and the conditional-rendering helper on their own.
 *
 * Traceability:
 *   SCRUM-62 AC1  a role that is not admitted is sent to /forbidden
 *   SCRUM-62 AC2  a role that is admitted reaches the page
 *   SCRUM-62 AC3  someone not logged in is sent to the login page
 *   SCRUM-62 AC4  the permission set of the role decides what is shown
 */
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Permission, Role } from '../lib/roles'

vi.mock('./useAuth', () => ({ useAuth: vi.fn() }))

import { Can } from './Can'
import { RequireAuth } from './RequireAuth'
import { RequirePermission } from './RequirePermission'
import { RequireRole } from './RequireRole'
import { useAuth } from './useAuth'

function session(role: Role | null, { permissions = [] as Permission[], loading = false } = {}) {
  vi.mocked(useAuth).mockReturnValue({
    user: role === null ? null : { id: 1, name: 'Someone', role },
    permissions,
    loading,
  } as unknown as ReturnType<typeof useAuth>)
}

function LoginPage() {
  const from = (useLocation().state as { from?: { pathname: string } } | null)?.from?.pathname
  return <p>{`login page, from ${from}`}</p>
}

function openBehind(guard: React.ReactElement) {
  render(
    <MemoryRouter initialEntries={['/page']}>
      <Routes>
        <Route element={guard}>
          <Route path="/page" element={<p>the page</p>} />
        </Route>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/forbidden" element={<p>forbidden</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => vi.clearAllMocks())

describe('RequireAuth', () => {
  it('AC2: lets a signed-in user through', () => {
    session(Role.ATTENDEE)
    openBehind(<RequireAuth />)
    expect(screen.getByText('the page')).toBeInTheDocument()
  })

  it('AC3: sends someone not logged in to log in, remembering where they were going', () => {
    session(null)
    openBehind(<RequireAuth />)
    expect(screen.getByText('login page, from /page')).toBeInTheDocument()
    expect(screen.queryByText('the page')).not.toBeInTheDocument()
  })

  it('shows nothing, and sends nobody away, while the session is still loading', () => {
    session(null, { loading: true })
    openBehind(<RequireAuth />)
    expect(screen.queryByText('the page')).not.toBeInTheDocument()
    expect(screen.queryByText(/login page/)).not.toBeInTheDocument()
  })
})

describe('RequireRole', () => {
  it('AC2: lets an admitted role through', () => {
    session(Role.COORDINATOR)
    openBehind(<RequireRole roles={[Role.COORDINATOR, Role.VENUE_STAFF]} />)
    expect(screen.getByText('the page')).toBeInTheDocument()
  })

  it('AC1: sends any other role to /forbidden', () => {
    session(Role.ORGANISER)
    openBehind(<RequireRole roles={[Role.COORDINATOR]} />)
    expect(screen.getByText('forbidden')).toBeInTheDocument()
    expect(screen.queryByText('the page')).not.toBeInTheDocument()
  })

  it('AC1: admits nobody when there is no user', () => {
    session(null)
    openBehind(<RequireRole roles={[Role.COORDINATOR]} />)
    expect(screen.getByText('forbidden')).toBeInTheDocument()
  })

  it('shows nothing, and sends nobody away, while the session is still loading', () => {
    session(null, { loading: true })
    openBehind(<RequireRole roles={[Role.COORDINATOR]} />)
    expect(screen.queryByText('the page')).not.toBeInTheDocument()
    expect(screen.queryByText('forbidden')).not.toBeInTheDocument()
  })
})

describe('RequirePermission', () => {
  it('AC4: lets someone holding the permission through', () => {
    session(Role.VENUE_STAFF, { permissions: [Permission.VENUE_MANAGE] })
    openBehind(<RequirePermission permission={Permission.VENUE_MANAGE} />)
    expect(screen.getByText('the page')).toBeInTheDocument()
  })

  it('AC4: sends someone without it to /forbidden', () => {
    session(Role.ATTENDEE, { permissions: [Permission.VENUE_READ] })
    openBehind(<RequirePermission permission={Permission.VENUE_MANAGE} />)
    expect(screen.getByText('forbidden')).toBeInTheDocument()
  })

  it('shows nothing, and sends nobody away, while the session is still loading', () => {
    session(null, { loading: true })
    openBehind(<RequirePermission permission={Permission.VENUE_MANAGE} />)
    expect(screen.queryByText('the page')).not.toBeInTheDocument()
    expect(screen.queryByText('forbidden')).not.toBeInTheDocument()
  })
})

describe('Can', () => {
  it('AC4: shows its children to someone holding the permission', () => {
    session(Role.VENUE_STAFF, { permissions: [Permission.VENUE_MANAGE] })
    render(<Can permission={Permission.VENUE_MANAGE}>a control</Can>)
    expect(screen.getByText('a control')).toBeInTheDocument()
  })

  it('AC4: hides them from anyone else', () => {
    session(Role.ATTENDEE, { permissions: [Permission.VENUE_READ] })
    render(<Can permission={Permission.VENUE_MANAGE}>a control</Can>)
    expect(screen.queryByText('a control')).not.toBeInTheDocument()
  })
})
