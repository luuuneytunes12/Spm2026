/**
 * SCRUM-95 -- Request Replacement Venue for Affected Booking (frontend).
 * The API rules are in backend/tests/test_venue_replacement.py.
 *
 *   AC1  'Find replacement' opens Venue Search with the booking's date, time
 *        and requirements filled in
 *   AC2  Venue Staff see which booking a request replaces
 *   AC3  the replaced original shows 'Replaced' and stays in the list
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/api'
import { VenueBookingSection } from '../../components/VenueBookingSection'
import { Venues } from './Venues'
import { VenueBookingQueue } from './VenueBookingQueue'

vi.mock('../../lib/venues', () => ({
  listVenues: vi.fn(),
  listVenueFilterOptions: vi.fn(),
}))
vi.mock('../../lib/venueBookings', async () => {
  const actual = await vi.importActual<typeof import('../../lib/venueBookings')>('../../lib/venueBookings')
  return {
    ...actual,
    listEventVenueBookings: vi.fn(),
    requestReplacementVenue: vi.fn(),
    listVenueBookingQueue: vi.fn(),
    listApprovedBookings: vi.fn(),
    listFlaggedBookings: vi.fn(),
  }
})

import { listVenueFilterOptions, listVenues } from '../../lib/venues'
import {
  findReplacementPath,
  listApprovedBookings,
  listEventVenueBookings,
  listFlaggedBookings,
  listVenueBookingQueue,
  requestReplacementVenue,
} from '../../lib/venueBookings'
import type { VenueBooking } from '../../lib/venueBookings'

const FLAGGED: VenueBooking = {
  id: 11,
  status: 'approved',
  created_at: '2030-10-01T02:00:00Z',
  event: { id: 7, name: 'Conference' },
  venue: { id: 3, name: 'Marina Hall', location: '10 Bayfront Ave', capacity: 250 },
  start_time: '2030-11-02T10:00:00Z',
  end_time: '2030-11-02T12:00:00Z',
  setup_minutes: 0,
  turnaround_minutes: 0,
  occupied_start: '2030-11-02T10:00:00Z',
  occupied_end: '2030-11-02T12:00:00Z',
  expires_at: null,
  expected_attendance: 120,
  room_layout_preference: 'Theatre',
  accessibility_needs: null,
  facilities_needs: null,
  venue_requirements: null,
  requested_by: { name: 'Sam Tan', email: 'sam@connectsphere.test' },
  decision_notes: null,
  suggested_alternative: null,
  reviewed_by: null,
  reviewed_at: null,
  conflict_flagged: true,
}

const HALL = { id: 9, name: 'Bay Room', location: 'Level 2', capacity: 200, facilities: [], is_active: true }

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(listVenues).mockResolvedValue([HALL])
  vi.mocked(listVenueFilterOptions).mockResolvedValue({ layouts: ['Theatre'], facilities: [], accessibility_features: [] })
  vi.mocked(listApprovedBookings).mockResolvedValue([])
  vi.mocked(listFlaggedBookings).mockResolvedValue([])
})

describe('SCRUM-95 AC1 - Find replacement opens Venue Search pre-filled', () => {
  it('links a flagged booking to a search carrying its time and needs', async () => {
    vi.mocked(listEventVenueBookings).mockResolvedValue([FLAGGED])
    render(
      <MemoryRouter>
        <VenueBookingSection eventId={7} expectedAttendance={120} />
      </MemoryRouter>,
    )
    const link = await screen.findByRole('link', { name: 'Find replacement for Marina Hall booking' })
    expect(link).toHaveAttribute('href', findReplacementPath(FLAGGED))
  })

  it('an unflagged booking has no Find replacement link', async () => {
    vi.mocked(listEventVenueBookings).mockResolvedValue([{ ...FLAGGED, conflict_flagged: false }])
    render(
      <MemoryRouter>
        <VenueBookingSection eventId={7} expectedAttendance={120} />
      </MemoryRouter>,
    )
    await screen.findByLabelText('Venue time for Marina Hall')
    expect(screen.queryByRole('link', { name: /Find replacement/ })).not.toBeInTheDocument()
  })

  it('the search starts with the booking date, time, attendance and layout already filled in', async () => {
    render(
      <MemoryRouter initialEntries={[findReplacementPath(FLAGGED)]}>
        <Venues />
      </MemoryRouter>,
    )
    await screen.findByText('Bay Room')
    await waitFor(() => expect(listVenues).toHaveBeenCalled())
    const search = vi.mocked(listVenues).mock.calls.at(-1)?.[0]
    expect(search).toMatchObject({
      start: '2030-11-02T10:00:00.000Z',
      end: '2030-11-02T12:00:00.000Z',
      minCapacity: 120,
      layout: 'Theatre',
    })
    expect(screen.getByText(/Finding a replacement for your booking at/)).toBeInTheDocument()
  })

  it('requesting a venue sends the replacement against the original booking', async () => {
    vi.mocked(requestReplacementVenue).mockResolvedValue({ ...FLAGGED, id: 12, status: 'pending' })
    render(
      <MemoryRouter initialEntries={[findReplacementPath(FLAGGED)]}>
        <Venues />
      </MemoryRouter>,
    )
    await userEvent.click(await screen.findByRole('button', { name: 'Request as replacement: Bay Room' }))
    expect(requestReplacementVenue).toHaveBeenCalledWith(11, { venue_id: 9, expected_attendance: 120 })
    expect(await screen.findByText(/Replacement requested at Bay Room/)).toBeInTheDocument()
  })

  it('shows the server error when the request is refused', async () => {
    vi.mocked(requestReplacementVenue).mockRejectedValue(
      new ApiError(409, 'A replacement has already been requested for this booking.'),
    )
    render(
      <MemoryRouter initialEntries={[findReplacementPath(FLAGGED)]}>
        <Venues />
      </MemoryRouter>,
    )
    await userEvent.click(await screen.findByRole('button', { name: 'Request as replacement: Bay Room' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('already been requested')
  })

  it('plain venue search (no replacement) offers no replacement button', async () => {
    render(
      <MemoryRouter>
        <Venues />
      </MemoryRouter>,
    )
    await screen.findByText('Bay Room')
    expect(screen.queryByRole('button', { name: /as replacement/ })).not.toBeInTheDocument()
  })
})

describe('SCRUM-95 AC2 - Venue Staff see which booking is replaced', () => {
  it('shows the replaced booking on the request', async () => {
    vi.mocked(listVenueBookingQueue).mockResolvedValue([
      {
        ...FLAGGED,
        id: 12,
        status: 'pending',
        conflict_flagged: false,
        venue: { id: 9, name: 'Bay Room', location: 'Level 2', capacity: 200 },
        replaces: { id: 11, status: 'approved', venue: { id: 3, name: 'Marina Hall' } },
      },
    ])
    render(
      <MemoryRouter>
        <VenueBookingQueue />
      </MemoryRouter>,
    )
    expect(await screen.findByText(/Replaces the booking at/)).toHaveTextContent('Marina Hall (booking #11)')
  })
})

describe('SCRUM-95 AC3 - the replaced original stays in the history', () => {
  it("shows 'Replaced' on the original", async () => {
    vi.mocked(listEventVenueBookings).mockResolvedValue([{ ...FLAGGED, status: 'replaced', conflict_flagged: false }])
    render(
      <MemoryRouter>
        <VenueBookingSection eventId={7} expectedAttendance={120} />
      </MemoryRouter>,
    )
    expect(await screen.findByText('Replaced', { selector: '.badge' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Cancel Marina Hall booking/ })).not.toBeInTheDocument()
  })
})
