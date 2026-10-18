/**
 * The screen guard on the Safety Officer's Past Safety Checks.
 *
 *   AC4  when a user without the Safety Officer role tries to open them on
 *        screen, access is denied. (A direct request is the backend's:
 *        backend/tests/test_past_safety_checks.py.)
 *
 * Renders the real routes in App.tsx; the page and the layout are stubs.
 */
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Role } from './lib/roles'

vi.mock('./auth/useAuth', () => ({ useAuth: vi.fn() }))
vi.mock('./components/AppLayout', async () => {
  const { Outlet } = await import('react-router')
  return { AppLayout: () => <Outlet /> }
})
vi.mock('./pages/safety/PastSafetyChecks', () => ({
  PastSafetyChecks: () => <p>the past safety checks</p>,
}))

import App from './App'
import { useAuth } from './auth/useAuth'

function signedInAs(role: Role | null) {
  vi.mocked(useAuth).mockReturnValue({
    user: role === null ? null : { id: 1, name: 'Someone', email: 'a@b.test', role },
    permissions: [],
    loading: false,
  } as unknown as ReturnType<typeof useAuth>)
}

function open(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  )
}

beforeEach(() => vi.clearAllMocks())

describe('AC4 - opening Past Safety Checks', () => {
  it('works for a Safety Officer', () => {
    signedInAs(Role.SAFETY_OFFICER)
    open('/safety-checks/history')

    expect(screen.getByText('the past safety checks')).toBeInTheDocument()
  })

  it.each([
    Role.ORGANISER,
    Role.COORDINATOR,
    Role.COORDINATOR_LEAD,
    Role.VENUE_STAFF,
    Role.TECH_SUPPORT,
    Role.ATTENDEE,
  ])('is denied to a %s', (role) => {
    signedInAs(role)
    open('/safety-checks/history')

    expect(screen.queryByText('the past safety checks')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'No Access' })).toBeInTheDocument()
  })

  it('sends someone who is not signed in to log in, not to the list', () => {
    signedInAs(null)
    open('/safety-checks/history')

    expect(screen.queryByText('the past safety checks')).not.toBeInTheDocument()
  })
})
