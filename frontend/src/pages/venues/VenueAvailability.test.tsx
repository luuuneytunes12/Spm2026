import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { VenueAvailability } from './VenueAvailability'

vi.mock('../../lib/venues', () => ({
  getVenue: vi.fn(),
  getVenueAvailability: vi.fn(),
}))

import { getVenue, getVenueAvailability } from '../../lib/venues'
import type { VenueAvailability as VenueAvailabilityData, VenueDetail } from '../../lib/venues'

const mockGetVenue = vi.mocked(getVenue)
const mockGetAvailability = vi.mocked(getVenueAvailability)

const VENUE: VenueDetail = {
  id: 7,
  name: 'Harbour Room',
  location: 'Pier 1',
  capacity: 120,
  facilities: ['Projector'],
  is_active: true,
  supported_layouts: ['Theatre'],
  accessibility_features: ['Wheelchair access'],
  operating_hours: null,
}

const CALENDAR: VenueAvailabilityData = {
  venue_id: 7,
  start: '2026-11-02T09:00:00Z',
  end: '2026-11-02T17:00:00Z',
  items: [
    {
      id: 31,
      kind: 'confirmed_booking',
      start_time: '2026-11-02T10:00:00Z',
      end_time: '2026-11-02T11:00:00Z',
      event_name: 'Planning Workshop',
      reason: null,
    },
    {
      id: 12,
      kind: 'unavailability',
      start_time: '2026-11-02T14:00:00Z',
      end_time: '2026-11-02T15:00:00Z',
      event_name: null,
      reason: 'Maintenance',
    },
  ],
}

function renderCalendar() {
  render(
    <MemoryRouter initialEntries={['/venues/7/availability']}>
      <Routes>
        <Route path="/venues/:id/availability" element={<VenueAvailability />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockGetVenue.mockResolvedValue(VENUE)
})

describe('View Venue Availability Calendar', () => {
  it('AC1-AC3: shows confirmed bookings and closures for the selected date/time range', async () => {
    mockGetAvailability.mockResolvedValue(CALENDAR)
    renderCalendar()

    fireEvent.change(await screen.findByLabelText('From'), {
      target: { value: '2026-11-02T09:00' },
    })
    fireEvent.change(screen.getByLabelText('Until'), {
      target: { value: '2026-11-02T17:00' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Check availability' }))

    expect(await screen.findByText('Planning Workshop')).toBeInTheDocument()
    expect(screen.getByText('Confirmed booking')).toBeInTheDocument()
    expect(screen.getAllByText('Unavailable')).toHaveLength(2)
    expect(screen.getByText('Reason: Maintenance')).toBeInTheDocument()
    expect(mockGetAvailability).toHaveBeenCalledWith(
      7,
      new Date('2026-11-02T09:00').toISOString(),
      new Date('2026-11-02T17:00').toISOString(),
    )
  })

  it('keeps the workflow open and offers retry when calendar loading fails', async () => {
    mockGetAvailability
      .mockRejectedValueOnce(new Error('temporary network issue'))
      .mockResolvedValueOnce({ ...CALENDAR, items: [] })
    renderCalendar()

    fireEvent.click(await screen.findByRole('button', { name: 'Check availability' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load venue availability')

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('No confirmed bookings or closures in this period.'))
      .toBeInTheDocument()
    expect(mockGetAvailability).toHaveBeenCalledTimes(2)
  })

  it('reports an invalid date range before sending a request', async () => {
    renderCalendar()
    fireEvent.change(await screen.findByLabelText('From'), {
      target: { value: '2026-11-02T17:00' },
    })
    fireEvent.change(screen.getByLabelText('Until'), {
      target: { value: '2026-11-02T09:00' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Check availability' }))

    expect(screen.getByRole('alert')).toHaveTextContent('The end must be after the start.')
    expect(mockGetAvailability).not.toHaveBeenCalled()
  })
})
