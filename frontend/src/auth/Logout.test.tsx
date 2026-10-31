/**
 * Logging out from the navbar, through the real AuthProvider, Navbar and
 * RequireAuth, with only the network mocked. What the server does with the
 * cookie is backend/tests/test_scrum63_logout.py.
 *
 * Traceability (SCRUM-63):
 *   AC1  logging out ends the session
 *   AC2  afterwards a page that needs an account is not shown
 *   AC3  they are taken back to the login page
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getAccessToken, hasSessionHint, setAccessToken, setSessionHint } from '../lib/api'
import { Role } from '../lib/roles'

vi.mock('../lib/api', async (orig) => ({
  ...(await orig<typeof import('../lib/api')>()),
  apiFetch: vi.fn(),
}))
vi.mock('../components/NotificationBell', () => ({ NotificationBell: () => null }))
vi.mock('../components/ThemeToggle', () => ({ ThemeToggle: () => null }))

import { apiFetch } from '../lib/api'
import { Navbar } from '../components/Navbar'
import { AuthProvider } from './AuthContext'
import { RequireAuth } from './RequireAuth'
import { useAuth } from './useAuth'

const ME = {
  user: { id: 1, name: 'Vera Staff', email: 'vera@cs.local', role: Role.VENUE_STAFF },
  permissions: [],
}

function LogoutFailingQuietly() {
  const { logout } = useAuth()
  return <button onClick={() => void logout().catch(() => undefined)}>log out, server down</button>
}

function Page() {
  return (
    <>
      <Navbar sidebarOpen onToggleSidebar={() => undefined} sidebarId="sidebar" />
      <LogoutFailingQuietly />
      <p>the private page</p>
    </>
  )
}

async function signedIn() {
  setSessionHint(true)
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: true, json: async () => ({ access_token: 'a-token', token_type: 'bearer' }) }),
  )
  vi.mocked(apiFetch).mockImplementation(async (path: string) => (path === '/auth/me' ? ME : undefined))
  render(
    <AuthProvider>
      <MemoryRouter initialEntries={['/private']}>
        <Routes>
          <Route path="/login" element={<p>the login page</p>} />
          <Route element={<RequireAuth />}>
            <Route path="/private" element={<Page />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  )
  await screen.findByText('the private page')
  expect(getAccessToken()).toBe('a-token')
}

const logOut = () => userEvent.click(screen.getByRole('button', { name: 'Log out' }))

beforeEach(() => vi.clearAllMocks())

afterEach(() => {
  vi.unstubAllGlobals()
  setAccessToken(null)
  setSessionHint(false)
})

describe('SCRUM-63: logging out', () => {
  it('AC1: asks the server to end the session', async () => {
    await signedIn()
    await logOut()
    await waitFor(() => expect(apiFetch).toHaveBeenCalledWith('/auth/logout', { method: 'POST' }))
  })

  it('AC1: forgets the access token and that this browser had a session', async () => {
    await signedIn()
    await logOut()
    await screen.findByText('the login page')
    expect(getAccessToken()).toBeNull()
    expect(hasSessionHint()).toBe(false)
  })

  it('AC2: no longer shows the page that needs an account', async () => {
    await signedIn()
    await logOut()
    await screen.findByText('the login page')
    expect(screen.queryByText('the private page')).not.toBeInTheDocument()
    expect(screen.queryByText('Vera Staff')).not.toBeInTheDocument()
  })

  it('AC3: takes them back to the login page', async () => {
    await signedIn()
    await logOut()
    expect(await screen.findByText('the login page')).toBeInTheDocument()
  })

  it('AC1: ends the session in this browser even when the server cannot be reached', async () => {
    await signedIn()
    vi.mocked(apiFetch).mockRejectedValue(new Error('down'))
    await userEvent.click(screen.getByRole('button', { name: 'log out, server down' }))
    expect(await screen.findByText('the login page')).toBeInTheDocument()
    expect(getAccessToken()).toBeNull()
    expect(hasSessionHint()).toBe(false)
  })
})
