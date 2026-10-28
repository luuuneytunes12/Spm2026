/**
 * Component tests for adding and editing Venues (SCRUM-108), named after the
 * AC they prove. Who may save is enforced server-side (backend/tests/test_venue_catalogue.py).
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/api'
import { parseList, venueFormErrors } from '../../lib/venueCatalogue'
import { VenueManage } from './VenueManage'

vi.mock('../../lib/venueCatalogue', async () => {
  const actual = await vi.importActual<typeof import('../../lib/venueCatalogue')>('../../lib/venueCatalogue')
  return { ...actual, addVenue: vi.fn(), editVenue: vi.fn(), listVenueActivity: vi.fn() }
})
vi.mock('../../lib/venues', async () => {
  const actual = await vi.importActual<typeof import('../../lib/venues')>('../../lib/venues')
  return { ...actual, getVenue: vi.fn() }
})

import { addVenue, editVenue, listVenueActivity } from '../../lib/venueCatalogue'
import { getVenue } from '../../lib/venues'

const mockAdd = vi.mocked(addVenue)
const mockEdit = vi.mocked(editVenue)
const mockActivity = vi.mocked(listVenueActivity)
const mockGet = vi.mocked(getVenue)

const VENUE = {
  id: 4,
  name: 'Harbour Hall',
  location: '5 Quay Road',
  capacity: 200,
  is_active: true,
  supported_layouts: ['Theatre', 'Classroom'],
  facilities: ['Projector'],
  accessibility_features: [],
  operating_hours: 'Mon-Fri 08:00-22:00',
  setup_minutes: null,
  turnaround_minutes: null,
}

function renderAt(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/venue-staff/venues/new" element={<VenueManage />} />
        <Route path="/venue-staff/venues/:id/edit" element={<VenueManage />} />
        <Route path="/venues/:id" element={<p>Venue page</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

async function fillNew(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText('Name'), 'Harbour Hall')
  await user.type(screen.getByLabelText('Location'), '5 Quay Road')
  await user.type(screen.getByLabelText(/Capacity/), '200')
  await user.type(screen.getByLabelText('Supported room layouts'), 'Theatre, Classroom')
  await user.type(screen.getByLabelText('Operating hours'), 'Mon-Fri 08:00-22:00')
}

beforeEach(() => {
  vi.clearAllMocks()
  mockActivity.mockResolvedValue([])
})

describe('lib helpers', () => {
  it('parses a comma list without blanks or repeats', () => {
    expect(parseList(' Theatre, theatre,, U-shape ')).toEqual(['Theatre', 'U-shape'])
  })
  it('ac3 flags missing details and a non-positive capacity', () => {
    const errors = venueFormErrors({
      name: '', location: '', capacity: '0', facilities: '', accessibility_features: '',
      supported_layouts: '', operating_hours: '',
    })
    expect(Object.keys(errors).sort()).toEqual(['capacity', 'location', 'name', 'operating_hours', 'supported_layouts'])
  })
})

describe('Add a venue', () => {
  it('ac1 sends all the details and opens the new venue', async () => {
    mockAdd.mockResolvedValue({ ...VENUE, flagged_bookings: [] })
    const user = userEvent.setup()
    renderAt('/venue-staff/venues/new')
    await fillNew(user)
    await user.click(screen.getByRole('button', { name: 'Add venue' }))
    expect(mockAdd).toHaveBeenCalledWith({
      name: 'Harbour Hall',
      location: '5 Quay Road',
      capacity: 200,
      facilities: [],
      accessibility_features: [],
      supported_layouts: ['Theatre', 'Classroom'],
      operating_hours: 'Mon-Fri 08:00-22:00',
    })
    expect(await screen.findByText('Venue page')).toBeInTheDocument()
  })

  it('ac3 blocks a save with a missing detail or bad capacity, sending nothing', async () => {
    const user = userEvent.setup()
    renderAt('/venue-staff/venues/new')
    await user.type(screen.getByLabelText(/Capacity/), '-3')
    await user.click(screen.getByRole('button', { name: 'Add venue' }))
    expect(await screen.findByText('Name is required.')).toBeInTheDocument()
    expect(screen.getByText('Capacity must be a whole number above zero.')).toBeInTheDocument()
    expect(mockAdd).not.toHaveBeenCalled()
  })

  it('ac3 shows the server reason when the name matches another venue', async () => {
    mockAdd.mockRejectedValue(new ApiError(409, "A venue named 'Harbour Hall' already exists. Venue names must be unique."))
    const user = userEvent.setup()
    renderAt('/venue-staff/venues/new')
    await fillNew(user)
    await user.click(screen.getByRole('button', { name: 'Add venue' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('already exists')
    expect(screen.getByLabelText('Name')).toHaveValue('Harbour Hall')
  })
})

describe('Edit a venue', () => {
  it('ac2 loads the details and saves the change', async () => {
    mockGet.mockResolvedValue(VENUE)
    mockEdit.mockResolvedValue({ ...VENUE, capacity: 300, flagged_bookings: [] })
    const user = userEvent.setup()
    renderAt('/venue-staff/venues/4/edit')
    const capacity = await screen.findByLabelText(/Capacity/)
    expect(capacity).toHaveValue('200')
    await user.clear(capacity)
    await user.type(capacity, '300')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(mockEdit).toHaveBeenCalledWith(4, expect.objectContaining({ capacity: 300 }))
    expect(await screen.findByRole('status')).toHaveTextContent('Harbour Hall saved.')
  })

  it('ac4 lists the bookings kept and flagged for review', async () => {
    mockGet.mockResolvedValue(VENUE)
    mockEdit.mockResolvedValue({
      ...VENUE,
      capacity: 50,
      flagged_bookings: [{ booking_id: 1, event_id: 2, event_name: 'Gala', reason: 'capacity reduced from 200 to 50' }],
    })
    const user = userEvent.setup()
    renderAt('/venue-staff/venues/4/edit')
    await user.click(await screen.findByRole('button', { name: 'Save changes' }))
    expect(await screen.findByText(/kept and flagged for review/)).toBeInTheDocument()
    expect(screen.getByText(/Gala: capacity reduced from 200 to 50/)).toBeInTheDocument()
  })

  it('ac5 shows the activity log with the change, who and when', async () => {
    mockGet.mockResolvedValue(VENUE)
    mockActivity.mockResolvedValue([
      { id: 1, venue_id: 4, venue_name: 'Harbour Hall', note: "Venue 'Harbour Hall' added.", changed_by: 'Vera', created_at: '2026-10-19T10:00:00Z' },
    ])
    renderAt('/venue-staff/venues/4/edit')
    expect(await screen.findByText(/Venue 'Harbour Hall' added\. By Vera on/)).toBeInTheDocument()
  })
})
