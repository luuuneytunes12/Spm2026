/**
 * The screen guard on Technical Support's list of equipment requirements.
 *
 * Traceability (see docs/test-cases-view-equipment-requirements.md):
 *   AC4  when a user other than Technical Support Staff tries to open the list
 *        on screen, access is denied. (A direct request is the backend's:
 *        backend/tests/test_requested_requirements_list.py.)
 *
 * This renders the real routes in App.tsx, so it fails if the list is ever
 * moved outside the Technical Support guard. The page itself and the layout
 * are stubs: only the guard is under test.
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
vi.mock('./pages/equipment/EquipmentRequirementsList', () => ({
  EquipmentRequirementsList: () => <p>the requirements list</p>,
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

describe('opening the list of equipment requirements', () => {
  it('works for Technical Support', () => {
    signedInAs(Role.TECH_SUPPORT)
    open('/equipment-requirements')

    expect(screen.getByText('the requirements list')).toBeInTheDocument()
  })

  it.each([
    Role.COORDINATOR,
    Role.COORDINATOR_LEAD,
    Role.ORGANISER,
    Role.VENUE_STAFF,
    Role.ATTENDEE,
    Role.SAFETY_OFFICER,
  ])('is denied to a %s', (role) => {
    signedInAs(role)
    open('/equipment-requirements')

    expect(screen.queryByText('the requirements list')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'No Access' })).toBeInTheDocument()
  })

  it('sends someone who is not signed in to log in, not to the list', () => {
    signedInAs(null)
    open('/equipment-requirements')

    expect(screen.queryByText('the requirements list')).not.toBeInTheDocument()
  })
})
