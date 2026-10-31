/**
 * The screen guards around every role's pages, through the real routes in
 * App.tsx. A refused role never reaches the page, so only the pages let through
 * by the "allowed" cases are stubbed. The API's own refusals are the backend's:
 * backend/tests/test_scrum62_rbac.py.
 *
 * Traceability:
 *   SCRUM-62 AC1  an Event Organiser is denied internal staff pages
 *   SCRUM-62 AC2  an Event Coordinator can open coordinator features
 *   SCRUM-62 AC3  someone not logged in is sent to the login page
 *   SCRUM-62 AC4  every other role keeps to its own pages
 *   SCRUM-77 AC4  a signed-in Safety Officer opening another role's page is told
 *                 they do not have access
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
vi.mock('./pages/events/AssignedEvents', () => ({ AssignedEvents: () => <p>the assigned events</p> }))

import App from './App'
import { useAuth } from './auth/useAuth'

function open(path: string, role: Role | null) {
  vi.mocked(useAuth).mockReturnValue({
    user: role === null ? null : { id: 1, name: 'Someone', email: 'a@b.test', role },
    permissions: [],
    loading: false,
  } as unknown as ReturnType<typeof useAuth>)
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  )
}

const noAccess = () => screen.queryByRole('heading', { name: 'No Access' })

beforeEach(() => vi.clearAllMocks())

describe('SCRUM-62: role-based access on screen', () => {
  it.each(['/staff', '/coordinator/events', '/venue-staff/bookings', '/equipment', '/safety-checks'])(
    'AC1: an Event Organiser is denied %s',
    (path) => {
      open(path, Role.ORGANISER)
      expect(noAccess()).toBeInTheDocument()
    },
  )

  it('AC2: an Event Coordinator can open coordinator features', () => {
    open('/coordinator/events', Role.COORDINATOR)
    expect(screen.getByText('the assigned events')).toBeInTheDocument()
    expect(noAccess()).not.toBeInTheDocument()
  })

  it.each(['/', '/profile', '/notifications', '/organiser', '/coordinator/events', '/venues', '/safety-checks'])(
    'AC3: someone not logged in who opens %s is sent to the login page',
    (path) => {
      open(path, null)
      expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument()
      expect(noAccess()).not.toBeInTheDocument()
    },
  )

  it.each([
    [Role.COORDINATOR, '/organiser'],
    [Role.VENUE_STAFF, '/coordinator/events'],
    [Role.TECH_SUPPORT, '/venues'],
    [Role.ATTENDEE, '/equipment'],
    [Role.COORDINATOR_LEAD, '/coordinator/events'],
    [Role.ATTENDEE, '/staff'],
  ])('AC4: %s is denied %s', (role, path) => {
    open(path, role)
    expect(noAccess()).toBeInTheDocument()
  })
})

describe('SCRUM-77: a Safety Officer on another role\'s page', () => {
  it.each([
    '/organiser',
    '/coordinator',
    '/coordinator-lead/queue',
    '/venue-staff/bookings',
    '/venues',
    '/tech-support',
    '/equipment',
    '/attendee/events',
  ])('AC4: is told they do not have access to %s', (path) => {
    open(path, Role.SAFETY_OFFICER)
    expect(noAccess()).toBeInTheDocument()
    expect(screen.getByText(/belongs to a different role/)).toBeInTheDocument()
  })

  it('AC4: is offered a way back', () => {
    open('/organiser', Role.SAFETY_OFFICER)
    expect(screen.getByRole('link', { name: 'Back to dashboard' })).toHaveAttribute('href', '/')
  })
})
