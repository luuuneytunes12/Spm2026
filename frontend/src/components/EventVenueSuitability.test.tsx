import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { EventVenueSuitability } from './EventVenueSuitability'
import { ApiError } from '../lib/api'

vi.mock('../lib/venues', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/venues')>()),
  checkEventVenueSuitability: vi.fn(),
  checkVenueBookingSuitability: vi.fn(),
}))

import { checkEventVenueSuitability, checkVenueBookingSuitability } from '../lib/venues'
import type { EventVenueSuitability as EventVenueSuitabilityResult } from '../lib/venues'

const mockCheck = vi.mocked(checkEventVenueSuitability)
const mockCheckBooking = vi.mocked(checkVenueBookingSuitability)

const RESULT: EventVenueSuitabilityResult = {
  event_id: 7,
  event_name: 'Regional Partner Conference',
  suitable: false,
  venues: [
    {
      booking_id: 14,
      venue_id: 3,
      venue_name: 'Main Hall',
      expected_attendance: 120,
      suitable: true,
      checks: [{
        category: 'capacity',
        requirement: '120 people',
        available: '250 people',
        met: true,
        message: 'Capacity is sufficient.',
      }],
    },
    {
      booking_id: 15,
      venue_id: 4,
      venue_name: 'Garden Room',
      expected_attendance: 80,
      suitable: false,
      checks: [{
        category: 'layout',
        requirement: 'Theatre',
        available: 'Boardroom',
        met: false,
        message: "Unsupported layout: 'Theatre' is not offered by this venue.",
      }],
    },
  ],
  combined_capacity: {
    required_capacity: 300,
    available_capacity: 360,
    met: true,
    message: 'Combined capacity is 360; it must exceed 300 attendees.',
  },
}

describe('event-wide venue suitability', () => {
  beforeEach(() => vi.clearAllMocks())

  it('AC3: marks only the venue booking outside its operating hours as Not suitable', async () => {
    mockCheck.mockResolvedValue({
      ...RESULT,
      venues: [
        RESULT.venues[0],
        {
          ...RESULT.venues[1],
          checks: [{
            category: 'operating_hours',
            requirement: 'Mon 02 Nov 2026 18:00 to Mon 02 Nov 2026 20:00',
            available: 'Mon-Fri 09:00-17:00',
            met: false,
            message: 'Outside operating hours',
          }],
        },
      ],
    })
    render(<EventVenueSuitability eventId={7} />)

    expect(await screen.findByText('Garden Room: Not suitable')).toBeInTheDocument()
    expect(screen.getByText('Main Hall: Suitable')).toBeInTheDocument()
    expect(screen.getByText('operating hours:')).toBeInTheDocument()
    expect(screen.getByText(/Outside operating hours/)).toBeInTheDocument()
  })

  it('shows each venue result and the separate combined-capacity result', async () => {
    mockCheck.mockResolvedValue(RESULT)
    render(<EventVenueSuitability eventId={7} />)

    expect(await screen.findByText('Main Hall: Suitable')).toBeInTheDocument()
    expect(screen.getByText('Garden Room: Not suitable')).toBeInTheDocument()
    expect(screen.getByText('Main Hall: Suitable')).toBeInTheDocument()
    expect(screen.getByText(/Unsupported layout/)).toBeInTheDocument()
    expect(screen.getByText(/Combined capacity: 360 \/ 300 required/)).toBeInTheDocument()
    expect(screen.getByText('Overall result: Not suitable.')).toBeInTheDocument()
    expect(mockCheck).toHaveBeenCalledWith(7)
  })

  it('shows an explicit message when no active venue bookings exist', async () => {
    mockCheck.mockResolvedValue({
      ...RESULT,
      venues: [],
      suitable: false,
      combined_capacity: {
        required_capacity: 120,
        available_capacity: 0,
        met: false,
        message: 'Combined capacity is 0; it must exceed 120 attendees.',
      },
    })
    render(<EventVenueSuitability eventId={7} />)

    expect(await screen.findByText('No active venue bookings are attached to this event yet.'))
      .toBeInTheDocument()
    expect(screen.getByText(/Combined capacity: 0 \/ 120 required/)).toBeInTheDocument()
  })

  it('rechecks only the selected booking and leaves the other result unchanged', async () => {
    mockCheck.mockResolvedValue(RESULT)
    mockCheckBooking.mockResolvedValue({
      ...RESULT.venues[0],
      expected_attendance: 300,
      suitable: false,
      checks: [{
        category: 'capacity',
        requirement: '300 people',
        available: '250 people',
        met: false,
        message: 'Insufficient capacity: Capacity 250 < attendance 300.',
      }],
    })
    render(<EventVenueSuitability eventId={7} />)

    await userEvent.click(await screen.findByRole('button', { name: 'Recheck Main Hall' }))

    expect(await screen.findByText('Main Hall: Not suitable')).toBeInTheDocument()
    expect(screen.getByText('Garden Room: Not suitable')).toBeInTheDocument()
    expect(screen.getByText('Attendance checked: 300')).toBeInTheDocument()
    expect(screen.getByText(/Combined capacity: 360 \/ 300 required/)).toBeInTheDocument()
    expect(screen.getByText('Overall result: Not suitable.')).toBeInTheDocument()
    await waitFor(() => expect(mockCheckBooking).toHaveBeenCalledWith(14))
  })

  it('shows the server explanation and permits a retry after failure', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    mockCheck
      .mockRejectedValueOnce(new ApiError(503, 'Venue suitability could not be calculated.'))
      .mockResolvedValueOnce(RESULT)
    render(<EventVenueSuitability eventId={7} />)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Venue suitability could not be calculated.',
    )
    await screen.findByRole('button', { name: 'Retry check' }).then((button) => button.click())
    expect(await screen.findByText('Main Hall: Suitable')).toBeInTheDocument()
    expect(mockCheck).toHaveBeenCalledTimes(2)
    expect(consoleError).toHaveBeenCalledWith(
      'Failed to check event venue suitability.',
      expect.objectContaining({ eventId: 7 }),
    )
    consoleError.mockRestore()
  })
})
