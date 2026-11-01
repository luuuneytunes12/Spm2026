/**
 * Logging in, as far as the routing goes: the real Login page, the real "/"
 * redirect (My) and the real RequireAuth guard, with only the session mocked.
 *
 * Traceability:
 *   SCRUM-71 AC1  an Event Organiser who logs in is taken to the Event Organiser landing page
 *   SCRUM-72 AC1  an Event Coordinator who logs in is taken to the Event Coordinator landing page
 *   SCRUM-14      wrong details do not sign in and say nothing about the account;
 *                 a visitor who is not logged in is sent to the login page
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../lib/api'
import { Role } from '../lib/roles'

vi.mock('../auth/useAuth', () => ({ useAuth: vi.fn() }))

import { useAuth } from '../auth/useAuth'
import { RequireAuth } from '../auth/RequireAuth'
import { Login } from './Login'
import { My } from './My'

type Session = { id: number; name: string; role: Role } | null
let session: Session

/** Render the real login and authentication redirect with an isolated, mocked session. */
function setUp(loginImpl: () => Promise<void>, startAt = '/login') {
  vi.mocked(useAuth).mockImplementation(
    () =>
      ({
        user: session,
        permissions: [],
        loading: false,
        login: loginImpl,
      }) as unknown as ReturnType<typeof useAuth>,
  )
  render(
    <MemoryRouter initialEntries={[startAt]}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<RequireAuth />}>
          <Route path="/" element={<My />} />
          <Route path="/organiser" element={<h1>Event Organiser landing page</h1>} />
          <Route path="/coordinator" element={<h1>Event Coordinator landing page</h1>} />
          <Route path="/venue-staff" element={<h1>Venue Staff landing page</h1>} />
          <Route path="/tech-support" element={<h1>Technical Support landing page</h1>} />
          <Route path="/attendee" element={<h1>Attendee landing page</h1>} />
          <Route path="/coordinator-lead" element={<h1>Coordinator Lead landing page</h1>} />
          <Route path="/safety-checks" element={<h1>Safety checks page</h1>} />
          <Route path="/profile" element={<h1>Profile</h1>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

/** Enter test credentials and submit the actual login form. */
async function signIn() {
  await userEvent.type(screen.getByLabelText('Email'), 'someone@cs.local')
  await userEvent.type(screen.getByLabelText('Password'), 'a-password')
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
}

describe('logging in', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    session = null
  })

  it('SCRUM-71 AC1: an Event Organiser who logs in is taken to the Event Organiser landing page', async () => {
    setUp(async () => {
      session = { id: 1, name: 'Olivia Organiser', role: Role.ORGANISER }
    })
    await signIn()
    expect(await screen.findByRole('heading', { name: 'Event Organiser landing page' })).toBeInTheDocument()
  })

  it('SCRUM-72 AC1: an Event Coordinator who logs in is taken to the Event Coordinator landing page', async () => {
    setUp(async () => {
      session = { id: 2, name: 'Sam Tan', role: Role.COORDINATOR }
    })
    await signIn()
    expect(await screen.findByRole('heading', { name: 'Event Coordinator landing page' })).toBeInTheDocument()
  })

  // SCRUM-14: each valid role must reach its own home, not a generic page.
  // The session is the controlled boundary; these tests exercise real routing.
  it.each([
    [Role.VENUE_STAFF, 'Venue Staff landing page'],
    [Role.TECH_SUPPORT, 'Technical Support landing page'],
    [Role.ATTENDEE, 'Attendee landing page'],
    [Role.COORDINATOR_LEAD, 'Coordinator Lead landing page'],
    [Role.SAFETY_OFFICER, 'Safety checks page'],
  ])('SCRUM-14: %s is redirected to its role home after login', async (role, heading) => {
    setUp(async () => { session = { id: 3, name: 'Test User', role } })
    await signIn()
    expect(await screen.findByRole('heading', { name: heading })).toBeInTheDocument()
  })

  it('SCRUM-14: wrong details do not sign in, and the error does not say whether the account exists', async () => {
    setUp(async () => {
      throw new ApiError(401, 'Incorrect email or password')
    })
    await signIn()
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid credentials')
    expect(screen.queryByRole('heading', { name: /landing page/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('SCRUM-14: a visitor who is not logged in is sent to the login page, not shown the page', async () => {
    setUp(async () => undefined, '/organiser')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument())
    expect(screen.queryByRole('heading', { name: /landing page/ })).not.toBeInTheDocument()
  })
})

describe('SCRUM-14 AC4 wording (not yet built)', () => {
  // Jira AC4 says a visitor who is not logged in is "told to log in first".
  // RequireAuth redirects silently to /login, which the test above proves;
  // no message is shown. Recorded as a todo, not a pass, until someone decides
  // whether the redirect alone is enough.
  it.todo('SCRUM-14 AC4: a visitor sent to log in is told they must log in first')
})
