/**
 * Component tests for the landing pages of the roles without a file of their
 * own: Venue Staff, Technical Support Staff and Attendee, rendered through the
 * real page components.
 *
 * Traceability:
 *   SCRUM-73  Login as Venue Staff
 *   SCRUM-74  Login as Technical Support Staff
 *   SCRUM-75  Login as Attendee
 *   AC1  welcomes them by name and role
 *   AC2  shortcuts to the features of that role, each linking to it
 *   AC3  the matching shortcut shows how many; with none, no number is shown
 *
 * The it.todo lines are acceptance criteria the page does not meet yet.
 */
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Role } from '../lib/roles'
import type { RegistrableEvent } from '../lib/registrations'

vi.mock('../auth/useAuth', () => ({ useAuth: vi.fn() }))
vi.mock('../notifications/useNotifications', () => ({ useNotifications: vi.fn() }))
vi.mock('../lib/venueBookings', async (orig) => ({
  ...(await orig<typeof import('../lib/venueBookings')>()),
  listVenueBookingQueue: vi.fn(),
  listFlaggedBookings: vi.fn(),
}))
vi.mock('../lib/registrations', async (orig) => ({
  ...(await orig<typeof import('../lib/registrations')>()),
  listMyRegistrations: vi.fn(),
}))

import { useAuth } from '../auth/useAuth'
import { useNotifications } from '../notifications/useNotifications'
import { listMyRegistrations } from '../lib/registrations'
import { listFlaggedBookings, listVenueBookingQueue } from '../lib/venueBookings'
import { Attendee } from '../pages/roles/Attendee'
import { TechSupport } from '../pages/roles/TechSupport'
import { VenueStaff } from '../pages/roles/VenueStaff'

function setUp(page: React.ReactNode, role: Role, name: string, unread = 0) {
  vi.mocked(useAuth).mockReturnValue({
    user: { id: 1, name, email: 'someone@cs.local', role },
    permissions: [],
    loading: false,
  } as unknown as ReturnType<typeof useAuth>)
  vi.mocked(useNotifications).mockReturnValue({
    items: [],
    unreadCount: unread,
    loading: false,
    error: null,
    markRead: vi.fn(),
    markAllRead: vi.fn(),
  })
  render(<MemoryRouter>{page}</MemoryRouter>)
}

const tile = (name: RegExp) => screen.getByRole('link', { name })
const tileHrefs = () => screen.getAllByRole('link').map((link) => link.getAttribute('href'))
const rows = <T,>(length: number, row: (id: number) => T) => Array.from({ length }, (_, id) => row(id))

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(listVenueBookingQueue).mockResolvedValue([])
  vi.mocked(listFlaggedBookings).mockResolvedValue([])
  vi.mocked(listMyRegistrations).mockResolvedValue([])
})

describe('SCRUM-73: Venue Staff landing page', () => {
  const open = (unread = 0) => setUp(<VenueStaff />, Role.VENUE_STAFF, 'Vera Staff', unread)

  it('AC1: welcomes them by name and role', () => {
    open()
    expect(screen.getByRole('heading', { level: 1, name: /Welcome back, Vera/ })).toBeInTheDocument()
    expect(screen.getByText('Venue Staff')).toBeInTheDocument()
  })

  it('AC2: shows the shortcuts and each links to its feature', () => {
    open()
    expect(tile(/Booking Requests/)).toHaveAttribute('href', '/venue-staff/bookings')
    expect(tile(/^Venues/)).toHaveAttribute('href', '/venues')
    expect(tile(/Notifications/)).toHaveAttribute('href', '/notifications')
    expect(tile(/My Profile/)).toHaveAttribute('href', '/profile')
  })

  it('AC2: offers nothing that belongs to another role', () => {
    open()
    expect(tileHrefs().filter((href) => /organiser|coordinator|tech|attendee|equipment|safety/.test(href ?? ''))).toEqual([])
  })

  it('AC3: shows how many pending requests and unread notifications there are', async () => {
    vi.mocked(listVenueBookingQueue).mockResolvedValue(
      rows(3, (id) => ({ id })) as unknown as Awaited<ReturnType<typeof listVenueBookingQueue>>,
    )
    open(5)
    await waitFor(() => expect(tile(/Booking Requests/)).toHaveTextContent('3'))
    expect(tile(/Notifications/)).toHaveTextContent('5')
  })

  it('AC3: shows no number when there are none', async () => {
    open()
    await waitFor(() => expect(listVenueBookingQueue).toHaveBeenCalled())
    expect(screen.queryByLabelText(/items|unread/)).not.toBeInTheDocument()
  })

  it('AC3: a failed count hides the number but keeps the shortcut', async () => {
    vi.mocked(listVenueBookingQueue).mockRejectedValue(new Error('down'))
    open()
    await waitFor(() => expect(listVenueBookingQueue).toHaveBeenCalled())
    expect(tile(/Booking Requests/)).not.toHaveTextContent(/\d/)
  })
})

describe('SCRUM-74: Technical Support Staff landing page', () => {
  const open = (unread = 0) => setUp(<TechSupport />, Role.TECH_SUPPORT, 'Tess Tech', unread)

  it('AC1: welcomes them by name and role', () => {
    open()
    expect(screen.getByRole('heading', { level: 1, name: /Welcome back, Tess/ })).toBeInTheDocument()
    expect(screen.getByText('Technical Support Staff')).toBeInTheDocument()
  })

  it('AC2: shows the shortcuts it has and each links to its feature', () => {
    open()
    expect(tile(/Equipment Catalogue/)).toHaveAttribute('href', '/equipment')
    expect(tile(/Notifications/)).toHaveAttribute('href', '/notifications')
    expect(tile(/My Profile/)).toHaveAttribute('href', '/profile')
  })

  it('AC3: shows how many unread notifications there are', () => {
    open(4)
    expect(tile(/Notifications/)).toHaveTextContent('4')
  })

  it('AC3: shows no number when nothing is unread', () => {
    open()
    expect(screen.queryByLabelText(/unread/)).not.toBeInTheDocument()
  })

  it.todo('AC2: has an Equipment Requests shortcut to /equipment-requirements (not on the page yet)')
  it.todo('AC3: the Equipment Requests shortcut counts the Requested requirements (not on the page yet)')
})

describe('SCRUM-75: Attendee landing page', () => {
  const open = (unread = 0) => setUp(<Attendee />, Role.ATTENDEE, 'Amir Attendee', unread)

  it('AC1: welcomes them by name and role', () => {
    open()
    expect(screen.getByRole('heading', { level: 1, name: /Welcome back, Amir/ })).toBeInTheDocument()
    expect(screen.getByText('Attendee')).toBeInTheDocument()
  })

  it('AC2: shows the shortcuts and each links to its feature', () => {
    open()
    expect(tile(/^Events/)).toHaveAttribute('href', '/attendee/events')
    expect(tile(/My Registrations/)).toHaveAttribute('href', '/attendee/registrations')
    expect(tile(/Notifications/)).toHaveAttribute('href', '/notifications')
    expect(tile(/My Profile/)).toHaveAttribute('href', '/profile')
  })

  it('AC3: counts current registrations only, not ones withdrawn from', async () => {
    vi.mocked(listMyRegistrations).mockResolvedValue([
      { id: 1, my_status: 'registered' },
      { id: 2, my_status: 'registered' },
      { id: 3, my_status: 'withdrawn' },
    ] as RegistrableEvent[])
    open(1)
    await waitFor(() => expect(tile(/My Registrations/)).toHaveTextContent('2'))
    expect(tile(/Notifications/)).toHaveTextContent('1')
  })

  it('AC3: shows no number when there are none', async () => {
    vi.mocked(listMyRegistrations).mockResolvedValue([{ id: 3, my_status: 'withdrawn' }] as RegistrableEvent[])
    open()
    await waitFor(() => expect(listMyRegistrations).toHaveBeenCalled())
    expect(screen.queryByLabelText(/items|unread/)).not.toBeInTheDocument()
  })
})
