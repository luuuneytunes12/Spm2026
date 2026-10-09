import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { VenueAvailability } from './VenueAvailability'

vi.mock('../../lib/venues', () => ({
  getVenue: vi.fn(),
  getVenueAvailability: vi.fn(),
}))
vi.mock('../../auth/useAuth', () => ({
  useAuth: () => ({ user: null }),
}))

import { ApiError } from '../../lib/api'
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
      event_id: 18,
      reason: null,
      expires_at: null,
      conflicts_with_unavailability: false,
    },
    {
      id: 12,
      kind: 'unavailability',
      start_time: '2026-11-02T14:00:00Z',
      end_time: '2026-11-02T15:00:00Z',
      event_name: null,
      event_id: null,
      reason: 'Maintenance',
      expires_at: null,
      conflicts_with_unavailability: false,
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
  vi.resetAllMocks()
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

    expect(await screen.findByText(/Planning Workshop/)).toBeInTheDocument()
    expect(screen.getByRole('grid', { name: 'November 2026' })).toBeInTheDocument()
    const selectedDate = screen.getByRole('region', { name: /Availability on 2026-11-02/ })
    expect(selectedDate).toHaveTextContent('Confirmed booking')
    expect(selectedDate).toHaveTextContent('Unavailable')
    expect(screen.queryByText('Reason: Maintenance')).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Planning Workshop' })).not.toBeInTheDocument()
    expect(mockGetAvailability).toHaveBeenCalledWith(
      7,
      new Date('2026-11-02T09:00').toISOString(),
      new Date('2026-11-02T17:00').toISOString(),
    )
  })

  it('marks dates and shows only event names, times, and availability when a date is selected', async () => {
    mockGetAvailability.mockResolvedValue(CALENDAR)
    renderCalendar()

    fireEvent.click(await screen.findByRole('button', { name: 'Check availability' }))
    fireEvent.click(await screen.findByRole('button', { name: /Monday, November 2, 2026/ }))

    const selectedDate = screen.getByRole('region', { name: /Availability on 2026-11-02/ })
    expect(selectedDate).toHaveTextContent('Planning Workshop')
    expect(selectedDate).toHaveTextContent('Unavailable')
    expect(selectedDate).toHaveTextContent('Confirmed booking')
    const start = new Date(CALENDAR.items[0].start_time).toLocaleTimeString(undefined, {
      hour: '2-digit',
      minute: '2-digit',
    })
    const end = new Date(CALENDAR.items[0].end_time).toLocaleTimeString(undefined, {
      hour: '2-digit',
      minute: '2-digit',
    })
    expect(selectedDate).toHaveTextContent(`${start} – ${end}`)
    expect(selectedDate).not.toHaveTextContent('Maintenance')
    expect(selectedDate.querySelector('a')).toBeNull()
  })

  it('loads another year and month from the month picker', async () => {
    mockGetAvailability
      .mockResolvedValueOnce(CALENDAR)
      .mockResolvedValueOnce({
        ...CALENDAR,
        start: new Date(2027, 1, 1).toISOString(),
        end: new Date(2027, 1, 28, 23, 59).toISOString(),
        items: [],
      })
    renderCalendar()

    fireEvent.click(await screen.findByRole('button', { name: 'Check availability' }))
    fireEvent.change(await screen.findByLabelText('View month'), {
      target: { value: '2027-02' },
    })

    expect(await screen.findByRole('grid', { name: 'February 2027' })).toBeInTheDocument()
    expect(mockGetAvailability).toHaveBeenLastCalledWith(
      7,
      new Date(2027, 1, 1).toISOString(),
      new Date(2027, 1, 28, 23, 59).toISOString(),
    )
  })

  it('marks every date covered by a multi-day booking', async () => {
    mockGetAvailability.mockResolvedValue({
      ...CALENDAR,
      start: '2026-11-02T00:00:00Z',
      end: '2026-11-03T23:59:00Z',
      items: [
        {
          ...CALENDAR.items[0],
          start_time: '2026-11-02T22:00:00Z',
          end_time: '2026-11-03T02:00:00Z',
          event_name: 'Overnight Conference',
        },
      ],
    })
    renderCalendar()
    fireEvent.change(await screen.findByLabelText('From'), {
      target: { value: '2026-11-02T00:00' },
    })
    fireEvent.change(screen.getByLabelText('Until'), {
      target: { value: '2026-11-03T23:59' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Check availability' }))

    fireEvent.click(
      await screen.findByRole('button', { name: /Tuesday, November 3, 2026, 1 availability entry/ }),
    )
    expect(screen.getByRole('region', { name: /Availability on 2026-11-03/ }))
      .toHaveTextContent('Overnight Conference')
  })

  it('keeps the workflow open and offers retry when calendar loading fails', async () => {
    mockGetAvailability
      .mockRejectedValueOnce(new TypeError('temporary network issue'))
      .mockResolvedValueOnce({ ...CALENDAR, items: [] })
    renderCalendar()

    fireEvent.click(await screen.findByRole('button', { name: 'Check availability' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not reach the backend')

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('No confirmed bookings, active holds, or closures on this date.'))
      .toBeInTheDocument()
    expect(mockGetAvailability).toHaveBeenCalledTimes(2)
  })

  it('explains a missing database migration and logs diagnostic context', async () => {
    const databaseError = new ApiError(
      503,
      'The database is missing venue_bookings.expires_at. Apply backend/sql/019_multi_venue_tentative_holds.sql to the configured database, then retry.',
    )
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    mockGetAvailability.mockRejectedValue(databaseError)
    renderCalendar()

    fireEvent.click(await screen.findByRole('button', { name: 'Check availability' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('The database is missing venue_bookings.expires_at')
    expect(screen.getByRole('alert')).toHaveTextContent(
      'backend/sql/019_multi_venue_tentative_holds.sql',
    )
    expect(consoleError).toHaveBeenCalledWith(
      'Failed to retrieve venue availability.',
      expect.objectContaining({ venueId: 7, error: databaseError }),
    )
    consoleError.mockRestore()
  })

  it('identifies a backend connection failure for the user', async () => {
    mockGetAvailability.mockRejectedValue(new TypeError('Failed to fetch'))
    renderCalendar()
    fireEvent.click(await screen.findByRole('button', { name: 'Check availability' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Could not reach the backend to retrieve availability',
    )
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
