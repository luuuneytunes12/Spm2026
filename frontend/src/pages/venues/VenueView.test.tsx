/**
 * Component tests for viewing venues.
 *
 * Traceability (see docs/test-cases-venue-details.md): each AC's fields are
 * on screen, including the "nothing recorded" states. Who may see venues is
 * enforced server-side and covered by backend/tests/test_venues.py.
 */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/api'
import { VenueView } from './VenueView'
import { Venues } from './Venues'

// The suitability panel a Coordinator sees loads their assigned events.
vi.mock('../../lib/events', async () => {
  const actual = await vi.importActual<typeof import('../../lib/events')>('../../lib/events')
  return { ...actual, listAssignedEvents: vi.fn().mockResolvedValue([]) }
})

// listVenueFilterOptions: the list page also loads its filter choices
// (Search and Filter Venues). Without it in the mock the page would call
// undefined on mount.
vi.mock('../../lib/venues', async () => {
  const actual = await vi.importActual<typeof import('../../lib/venues')>('../../lib/venues')
  return {
    ...actual,
    listVenues: vi.fn(),
    getVenue: vi.fn(),
    saveSetupTurnaround: vi.fn(),
    getVenueAvailability: vi.fn(),
    listUnavailability: vi.fn().mockResolvedValue([]),
    listVenueFilterOptions: vi.fn().mockResolvedValue({
      layouts: [],
      facilities: [],
      accessibility_features: [],
    }),
  }
})
vi.mock('../../auth/useAuth', () => ({ useAuth: vi.fn() }))

import { useAuth } from '../../auth/useAuth'
import { getVenue, getVenueAvailability, listVenues, saveSetupTurnaround } from '../../lib/venues'
import type { VenueDetail } from '../../lib/venues'

const mockList = vi.mocked(listVenues)
const mockGet = vi.mocked(getVenue)
const mockSave = vi.mocked(saveSetupTurnaround)
const mockAvail = vi.mocked(getVenueAvailability)
const mockAuth = vi.mocked(useAuth)

function signInAs(role: string) {
  mockAuth.mockReturnValue({ user: { role } } as unknown as ReturnType<typeof useAuth>)
}

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
  setup_minutes: null,
  turnaround_minutes: null,
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
  signInAs('coordinator')
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
    signInAs('venue_staff')
    mockGet.mockResolvedValue(VENUE)
    renderDetail()

    expect(await screen.findByRole('heading', { name: 'Marina Grand Ballroom' }))
      .toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Check event suitability' }))
      .not.toBeInTheDocument()
  })
})

describe('SCRUM-78 setup and turnaround', () => {
  it('AC3: says not set, and that 0 minutes is used, when none is saved', async () => {
    signInAs('venue_staff')
    mockGet.mockResolvedValue(VENUE)
    renderDetail()

    expect(await screen.findAllByText('Not set - 0 minutes is used')).toHaveLength(2)
  })

  it('AC4: a Coordinator sees both values and the occupancy, read-only', async () => {
    mockGet.mockResolvedValue({ ...VENUE, setup_minutes: 30, turnaround_minutes: 45 })
    renderDetail()

    expect(await screen.findByText('30 minutes')).toBeInTheDocument()
    expect(screen.getByText('45 minutes')).toBeInTheDocument()
    expect(
      screen.getByText(/From the Event start minus 30 minutes to the Event end plus 45 minutes/),
    ).toBeInTheDocument()
    expect(screen.queryByLabelText('Setup time (minutes)')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Save setup/ })).not.toBeInTheDocument()
  })

  it('AC1: Venue Staff save whole minutes and see them on the venue', async () => {
    signInAs('venue_staff')
    mockGet.mockResolvedValue(VENUE)
    mockSave.mockResolvedValue({ ...VENUE, setup_minutes: 30, turnaround_minutes: 45 })
    renderDetail()

    await userEvent.type(await screen.findByLabelText('Setup time (minutes)'), '30')
    await userEvent.type(screen.getByLabelText('Turnaround time (minutes)'), '45')
    await userEvent.click(screen.getByRole('button', { name: 'Save setup and turnaround' }))

    expect(mockSave).toHaveBeenCalledWith(4, { setup_minutes: 30, turnaround_minutes: 45 })
    expect(await screen.findByRole('status')).toHaveTextContent('saved')
    expect(screen.getByText('30 minutes')).toBeInTheDocument()
  })

  it('AC2: empty, negative and non-whole values are blocked before anything is sent', async () => {
    signInAs('venue_staff')
    mockGet.mockResolvedValue(VENUE)
    renderDetail()
    const setup = await screen.findByLabelText('Setup time (minutes)')
    const turnaround = screen.getByLabelText('Turnaround time (minutes)')
    const save = screen.getByRole('button', { name: 'Save setup and turnaround' })

    await userEvent.click(save)
    expect(screen.getAllByRole('alert').map((a) => a.textContent).join(' ')).toMatch(/Setup time is required/)
    expect(setup).toHaveAttribute('aria-invalid', 'true')

    await userEvent.type(setup, '-5')
    await userEvent.type(turnaround, '1.5')
    await userEvent.click(save)
    const alerts = screen.getAllByRole('alert').map((a) => a.textContent)
    expect(alerts[0]).toMatch(/cannot be negative/)
    expect(alerts[1]).toMatch(/whole number/)
    // The problem is tied to its field for assistive technology.
    expect(setup.getAttribute('aria-describedby')).toContain('setup-minutes-error')
    expect(mockSave).not.toHaveBeenCalled()
  })

  it('AC2: a server refusal is shown next to the field it names', async () => {
    signInAs('venue_staff')
    mockGet.mockResolvedValue(VENUE)
    mockSave.mockRejectedValue(
      new ApiError(422, 'setup_minutes: must be 1440 or less', ['setup_minutes'], ['must be 1440 or less']),
    )
    renderDetail()

    await userEvent.type(await screen.findByLabelText('Setup time (minutes)'), '5000')
    await userEvent.type(screen.getByLabelText('Turnaround time (minutes)'), '10')
    await userEvent.click(screen.getByRole('button', { name: 'Save setup and turnaround' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('must be 1440 or less')
    expect(screen.getByLabelText('Setup time (minutes)')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByLabelText('Turnaround time (minutes)')).not.toHaveAttribute('aria-invalid')
  })

  it('AC4: no edit form for anyone but Venue Staff', async () => {
    signInAs('organiser')
    mockGet.mockResolvedValue(VENUE)
    renderDetail()
    await screen.findByRole('heading', { name: 'Setup and turnaround' })
    expect(screen.queryByLabelText('Setup time (minutes)')).not.toBeInTheDocument()
  })
})

describe('SCRUM-41 AC2 - the availability calendar', () => {
  async function checkRange(start: string, end: string) {
    mockGet.mockResolvedValue(VENUE)
    renderDetail()
    await screen.findByRole('heading', { name: 'Availability' })
    if (start) await userEvent.type(screen.getByLabelText('Availability from'), start)
    if (end) await userEvent.type(screen.getByLabelText('Availability until'), end)
    await userEvent.click(screen.getByRole('button', { name: 'Check availability' }))
  }

  it('does not show the venue available during an approved booking\'s occupied period', async () => {
    mockAvail.mockResolvedValue({
      venue_id: 4,
      start: '2026-11-02T00:00:00Z',
      end: '2026-11-03T00:00:00Z',
      items: [],
      busy: [{ kind: 'booking', start: '2026-11-02T01:30:00Z', end: '2026-11-02T04:45:00Z', event_name: 'Alumni Gala' }],
    })
    await checkRange('2026-11-02T00:00', '2026-11-03T00:00')
    const results = await screen.findByRole('region', { name: 'Availability results' })
    expect(results).toHaveTextContent('Booked for Alumni Gala')
    expect(results).not.toHaveTextContent('Available for the whole period')
    expect(mockAvail).toHaveBeenCalledWith(4, expect.any(String), expect.any(String))
  })

  it('lists a closure', async () => {
    mockAvail.mockResolvedValue({
      venue_id: 4,
      start: '2026-11-02T00:00:00Z',
      end: '2026-11-03T00:00:00Z',
      items: [],
      busy: [{ kind: 'closure', start: '2026-11-02T01:00:00Z', end: '2026-11-02T02:00:00Z' }],
    })
    await checkRange('2026-11-02T00:00', '2026-11-03T00:00')
    expect(await screen.findByText(/Unavailable \(closed\)/)).toBeInTheDocument()
  })

  it('says the venue is available when nothing is busy', async () => {
    mockAvail.mockResolvedValue({
      venue_id: 4,
      start: '2026-11-02T00:00:00Z',
      end: '2026-11-03T00:00:00Z',
      items: [],
      busy: [],
    })
    await checkRange('2026-11-02T00:00', '2026-11-03T00:00')
    expect(await screen.findByText('Available for the whole period.')).toBeInTheDocument()
  })

  it('refuses an end that is not after the start, without calling the server', async () => {
    await checkRange('2026-11-03T00:00', '2026-11-02T00:00')
    expect(await screen.findByRole('alert')).toHaveTextContent('The end must be after the start.')
    expect(mockAvail).not.toHaveBeenCalled()
  })

  it('shows the server\'s refusal', async () => {
    mockAvail.mockRejectedValue(new ApiError(403, 'Not allowed.'))
    await checkRange('2026-11-02T00:00', '2026-11-03T00:00')
    expect(await screen.findByRole('alert')).toHaveTextContent('Not allowed.')
  })
})

describe('SCRUM-92 AC1/AC3 - the re-check result after saving', () => {
  async function save(recheck: { flagged: number; cleared: number } | null) {
    signInAs('venue_staff')
    mockGet.mockResolvedValue(VENUE)
    mockSave.mockResolvedValue({ ...VENUE, setup_minutes: 30, turnaround_minutes: 45, recheck })
    renderDetail()
    await userEvent.type(await screen.findByLabelText('Setup time (minutes)'), '30')
    await userEvent.type(screen.getByLabelText('Turnaround time (minutes)'), '45')
    await userEvent.click(screen.getByRole('button', { name: 'Save setup and turnaround' }))
  }

  it('AC1: flagged bookings are reported with a link to the flagged list', async () => {
    await save({ flagged: 2, cleared: 1 })
    expect(await screen.findByText(/2 existing bookings flagged for conflict; 1 flag cleared/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'View flagged bookings' })).toHaveAttribute('href', '/venue-staff/flagged')
  })

  it('AC3: with no conflicts it says so and offers no link', async () => {
    await save({ flagged: 0, cleared: 0 })
    expect(await screen.findByText(/times saved\. No existing bookings conflict\./)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'View flagged bookings' })).not.toBeInTheDocument()
  })

  it('a save without a re-check result shows only the saved notice', async () => {
    await save(null)
    expect(await screen.findByText('Setup and turnaround times saved.')).toBeInTheDocument()
    expect(screen.queryByText(/existing booking/)).not.toBeInTheDocument()
  })
})
