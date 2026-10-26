/**
 * The screen guard on the Staff directory (SCRUM-19): internal staff only.
 * A direct request is the backend's: backend/tests/test_department_responsibilities.py.
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
vi.mock('./pages/StaffDirectory', () => ({ StaffDirectory: () => <p>the staff directory</p> }))

import App from './App'
import { useAuth } from './auth/useAuth'

function signedInAs(role: Role) {
  vi.mocked(useAuth).mockReturnValue({
    user: { id: 1, name: 'Someone', email: 'a@b.test', role },
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

describe('opening the Staff directory', () => {
  it.each([
    Role.COORDINATOR,
    Role.COORDINATOR_LEAD,
    Role.VENUE_STAFF,
    Role.TECH_SUPPORT,
    Role.SAFETY_OFFICER,
  ])('AC2: works for %s', (role) => {
    signedInAs(role)
    open('/staff')
    expect(screen.getByText('the staff directory')).toBeInTheDocument()
  })

  it.each([Role.ORGANISER, Role.ATTENDEE])('AC6: is denied to %s', (role) => {
    signedInAs(role)
    open('/staff')
    expect(screen.queryByText('the staff directory')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'No Access' })).toBeInTheDocument()
  })
})
