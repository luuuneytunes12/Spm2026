/**
 * Logging in takes every role to its own landing page: the real Login page,
 * the real "/" redirect (My) and the real RequireAuth guard, with only the
 * session mocked. LoginRedirect.test.tsx covers Organiser and Coordinator.
 *
 * Traceability:
 *   SCRUM-73 AC1  Venue Staff
 *   SCRUM-74 AC1  Technical Support Staff
 *   SCRUM-75 AC1  Attendee
 *   SCRUM-76 AC1  Event Coordinator Lead
 *   SCRUM-77 AC1  Safety Officer, whose home is the Safety Checks queue
 *
 * The it.todo lines are acceptance criteria the app does not meet yet.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { ROLE_HOME_PATH, Role } from '../lib/roles'

vi.mock('../auth/useAuth', () => ({ useAuth: vi.fn() }))

import { RequireAuth } from '../auth/RequireAuth'
import { useAuth } from '../auth/useAuth'
import { Login } from './Login'
import { My } from './My'

type Session = { id: number; name: string; role: Role } | null

function setUp(role: Role) {
  let session: Session = null
  vi.mocked(useAuth).mockImplementation(
    () =>
      ({
        user: session,
        permissions: [],
        loading: false,
        login: async () => {
          session = { id: 1, name: 'Someone', role }
        },
      }) as unknown as ReturnType<typeof useAuth>,
  )
  render(
    <MemoryRouter initialEntries={['/login']}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<RequireAuth />}>
          <Route path="/" element={<My />} />
          {Object.values(ROLE_HOME_PATH).map((path) => (
            <Route key={path} path={path} element={<h1>{`landing at ${path}`}</h1>} />
          ))}
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

describe('logging in', () => {
  it.each([
    ['SCRUM-73', Role.VENUE_STAFF, '/venue-staff'],
    ['SCRUM-74', Role.TECH_SUPPORT, '/tech-support'],
    ['SCRUM-75', Role.ATTENDEE, '/attendee'],
    ['SCRUM-76', Role.COORDINATOR_LEAD, '/coordinator-lead'],
    ['SCRUM-77', Role.SAFETY_OFFICER, '/safety-checks'],
  ])('%s AC1: %s is taken to %s', async (_story, role, path) => {
    setUp(role)
    const user = userEvent.setup({ delay: null })
    await user.type(screen.getByLabelText('Email'), 'a@cs.local')
    await user.type(screen.getByLabelText('Password'), 'pw')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('heading', { name: `landing at ${path}` })).toBeInTheDocument()
  })

  it.todo('SCRUM-77 AC1: the Safety Officer lands on a page welcoming them by name and role (it opens the queue)')
  it.todo('SCRUM-77 AC2: that page has shortcuts to Safety Checks, Notifications and My Profile')
  it.todo('SCRUM-77 AC3: those shortcuts show how many Events await a check and how many notifications are unread')
})
