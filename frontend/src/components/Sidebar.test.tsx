/**
 * Component tests for the sidebar entries this story adds and removes.
 *
 * Traceability (see docs/test-cases-equipment-requirements.md):
 *   ER AC2  Technical Support can reach the event record -- from here
 *
 * Only the equipment entries are covered; the rest of the sidebar belongs
 * to the stories that added it.
 */
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Role } from '../lib/roles'
import { Sidebar } from './Sidebar'

vi.mock('../auth/useAuth', () => ({ useAuth: vi.fn() }))

import { useAuth } from '../auth/useAuth'

const mockAuth = vi.mocked(useAuth)

function signedInAs(role: Role) {
  mockAuth.mockReturnValue({
    user: {
      id: 1,
      name: 'Test User',
      email: 'test@example.com',
      role,
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
  })
  render(
    <MemoryRouter>
      <Sidebar id="sidebar" open />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('Technical Support', () => {
  it('can reach the event requirements', () => {
    signedInAs(Role.TECH_SUPPORT)

    const link = within(screen.getByRole('navigation', { name: 'Main' })).getByRole('link', {
      name: 'Equipment Requirements',
    })
    expect(link).toHaveAttribute('href', '/equipment-requirements')
  })

  it('still has the equipment catalogue', () => {
    signedInAs(Role.TECH_SUPPORT)

    expect(screen.getByRole('link', { name: 'Equipment Catalogue' })).toHaveAttribute(
      'href',
      '/equipment',
    )
  })

})

describe('Event Coordinator', () => {
  it('no longer sees "Request equipment" as planned -- it is on the event page now', () => {
    signedInAs(Role.COORDINATOR)

    expect(screen.queryByText('Request equipment')).not.toBeInTheDocument()
  })

  it('is not offered Technical Support’s page', () => {
    signedInAs(Role.COORDINATOR)

    expect(screen.queryByRole('link', { name: 'Equipment Requirements' })).not.toBeInTheDocument()
  })
})

describe('everyone else', () => {
  it.each([Role.ORGANISER, Role.VENUE_STAFF, Role.ATTENDEE])(
    'is not offered Technical Support’s page (%s)',
    (role) => {
      signedInAs(role)

      expect(screen.queryByRole('link', { name: 'Equipment Requirements' })).not.toBeInTheDocument()
    },
  )
})

describe('Event Coordinator Lead', () => {
  it('can reach the Unassigned Requests and Coordinator Assignments from the sidebar', () => {
    signedInAs(Role.COORDINATOR_LEAD)

    const nav = within(screen.getByRole('navigation', { name: 'Main' }))
    expect(nav.getByRole('link', { name: 'Unassigned Requests' })).toHaveAttribute('href', '/coordinator-lead/queue')
    expect(nav.getByRole('link', { name: 'Coordinator Assignments' })).toHaveAttribute('href', '/coordinator-lead/assignments')
  })

  it('does not show the Lead links to other roles', () => {
    signedInAs(Role.COORDINATOR)

    expect(screen.queryByRole('link', { name: 'Coordinator Assignments' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Unassigned Requests' })).not.toBeInTheDocument()
  })
})

describe('Safety Officer and Event Coordinator Lead side by side', () => {
  it('shows the Safety Officer their own link and none of the Lead links', () => {
    signedInAs(Role.SAFETY_OFFICER)

    const nav = within(screen.getByRole('navigation', { name: 'Main' }))
    expect(nav.getByRole('link', { name: 'Safety Checks' })).toHaveAttribute('href', '/safety-checks')
    expect(nav.queryByRole('link', { name: 'Coordinator Assignments' })).not.toBeInTheDocument()
    expect(nav.queryByRole('link', { name: 'Unassigned Requests' })).not.toBeInTheDocument()
  })

  it('shows the Lead their links and no Safety Checks link', () => {
    signedInAs(Role.COORDINATOR_LEAD)

    const nav = within(screen.getByRole('navigation', { name: 'Main' }))
    expect(nav.getByRole('link', { name: 'Home' })).toHaveAttribute('href', '/coordinator-lead')
    expect(nav.getByRole('link', { name: 'Coordinator Assignments' })).toBeInTheDocument()
    expect(nav.queryByRole('link', { name: 'Safety Checks' })).not.toBeInTheDocument()
  })
})
