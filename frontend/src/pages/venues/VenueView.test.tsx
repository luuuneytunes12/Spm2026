/**
 * Component tests for viewing venues.
 *
 * Traceability (see docs/test-cases-venue-details.md): each AC's fields are
 * on screen, including the "nothing recorded" states. Who may see venues is
 * enforced server-side and covered by backend/tests/test_venues.py.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/api'
import { VenueView } from './VenueView'
import { Venues } from './Venues'

const auth = vi.hoisted(() => ({ role: 'venue_staff' }))
vi.mock('../../auth/useAuth', () => ({
  useAuth: () => ({ user: { role: auth.role } }),
}))
vi.mock('../../lib/events', () => ({
  fromDateTimeLocal: (value: string) => (value ? new Date(value).toISOString() : null),
}))

// listVenueFilterOptions: the list page also loads its filter choices
// (Search and Filter Venues). Without it in the mock the page would call
// undefined on mount.
vi.mock('../../lib/venues', () => ({
  listVenues: vi.fn(),
  getVenue: vi.fn(),
  getVenueAvailability: vi.fn(),
  listVenueFilterOptions: vi.fn().mockResolvedValue({
    layouts: [],
    facilities: [],
    accessibility_features: [],
  }),
  recordVenueUnavailability: vi.fn(),
}))

import { getVenue, listVenues, recordVenueUnavailability } from '../../lib/venues'
import type { VenueDetail } from '../../lib/venues'

const mockList = vi.mocked(listVenues)
const mockGet = vi.mocked(getVenue)
const mockRecordUnavailability = vi.mocked(recordVenueUnavailability)

const VENUE: VenueDetail = {
  id: 4,
  name: 'Marina Grand Ballroom',
  location: '10 Bayfront Ave, Level 3',
  capacity: 600,
  is_active: true,
  supported_layouts: ['Theatre', 'Banquet'],
  facilities: ['Stage', 'Built-in PA system'],
  accessibility_features: ['Wheelchair access', 'Hearing loop'],
  operating_hours: 'Mon-Fri 08:00-23:00\nSat-Sun 09:00-23:00',
}

function renderDetail() {
  render(
    <MemoryRouter initialEntries={['/venues/4']}>
      <Routes>
        <Route path="/venues/:id" element={<VenueView />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  auth.role = 'venue_staff'
})

describe('venue list', () => {
  it('shows each venue with its location and capacity, and links to its details', async () => {
    mockList.mockResolvedValue([VENUE, { ...VENUE, id: 5, name: 'Changi Suite', is_active: false }])
    render(
      <MemoryRouter>
        <Venues />
      </MemoryRouter>,
    )

    expect(await screen.findByText('Marina Grand Ballroom')).toBeInTheDocument()
    expect(screen.getAllByText('10 Bayfront Ave, Level 3 · Capacity 600')).toHaveLength(2)
    expect(screen.getByText('Inactive')).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: 'View details of Marina Grand Ballroom' }),
    ).toHaveAttribute('href', '/venues/4')
  })
})

describe('venue details', () => {
  it('AC1: shows name, location and capacity', async () => {
    mockGet.mockResolvedValue(VENUE)
    renderDetail()

    expect(await screen.findByRole('heading', { name: 'Marina Grand Ballroom' })).toBeInTheDocument()
    expect(screen.getByText('10 Bayfront Ave, Level 3')).toBeInTheDocument()
    expect(screen.getByText('600 people')).toBeInTheDocument()
    expect(mockGet).toHaveBeenCalledWith(4)
  })

  it('AC2: shows supported layouts, facilities and accessibility features', async () => {
    mockGet.mockResolvedValue(VENUE)
    renderDetail()

    const layouts = await screen.findByRole('list', { name: 'Supported room layouts' })
    expect(within(layouts).getAllByRole('listitem').map((li) => li.textContent)).toEqual([
      'Theatre',
      'Banquet',
    ])
    const facilities = screen.getByRole('list', { name: 'Facilities' })
    expect(within(facilities).getByText('Built-in PA system')).toBeInTheDocument()
    const access = screen.getByRole('list', { name: 'Accessibility features' })
    expect(within(access).getByText('Hearing loop')).toBeInTheDocument()
  })

  it('AC3: shows operating hours, one entry per line', async () => {
    mockGet.mockResolvedValue(VENUE)
    renderDetail()

    expect(await screen.findByText('Mon-Fri 08:00-23:00')).toBeInTheDocument()
    expect(screen.getByText('Sat-Sun 09:00-23:00')).toBeInTheDocument()
  })

  it('says so when layouts, facilities, accessibility or hours are not recorded', async () => {
    mockGet.mockResolvedValue({
      ...VENUE,
      supported_layouts: [],
      facilities: [],
      accessibility_features: [],
      operating_hours: null,
    })
    renderDetail()

    expect(await screen.findAllByText('None recorded')).toHaveLength(3)
    expect(screen.getByText('Not recorded')).toBeInTheDocument()
  })

  it('shows "not found" for a venue that does not exist', async () => {
    mockGet.mockRejectedValue(new ApiError(404, 'Venue not found'))
    renderDetail()

    expect(await screen.findByRole('alert')).toHaveTextContent('Venue not found.')
  })

  it('does not offer event suitability to Venue Staff', async () => {
    mockGet.mockResolvedValue(VENUE)
    renderDetail()

    expect(await screen.findByRole('heading', { name: 'Marina Grand Ballroom' }))
      .toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Check event suitability' }))
      .not.toBeInTheDocument()
  })

  it('lets Venue Staff record unavailability and confirms affected bookings remain', async () => {
    mockGet.mockResolvedValue(VENUE)
    mockRecordUnavailability.mockResolvedValue({
      id: 5,
      venue_id: VENUE.id,
      start_time: '2026-11-02T09:00:00Z',
      end_time: '2026-11-02T17:00:00Z',
      reason: 'Maintenance',
      affected_booking_ids: [22],
      affected_event_ids: [18],
    })
    renderDetail()
    fireEvent.change(await screen.findByLabelText('From'), {
      target: { value: '2026-11-02T09:00' },
    })
    fireEvent.change(screen.getByLabelText('Until'), {
      target: { value: '2026-11-02T17:00' },
    })
    fireEvent.change(screen.getByLabelText('Reason'), {
      target: { value: 'Maintenance' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Record unavailability' }))

    expect(await screen.findByRole('status')).toHaveTextContent('1 existing booking(s) are affected')
    expect(screen.getByRole('status')).toHaveTextContent('they were not cancelled')
    expect(mockRecordUnavailability).toHaveBeenCalledWith(VENUE.id, {
      start_time: new Date('2026-11-02T09:00').toISOString(),
      end_time: new Date('2026-11-02T17:00').toISOString(),
      reason: 'Maintenance',
    })
  })
})
