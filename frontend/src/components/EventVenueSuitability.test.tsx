import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { EventVenueSuitability } from './EventVenueSuitability'

vi.mock('../lib/venues', () => ({
  checkEventVenueSuitability: vi.fn(),
}))

import { checkEventVenueSuitability } from '../lib/venues'
import type { EventVenueSuitability as EventVenueSuitabilityResult } from '../lib/venues'

const mockCheck = vi.mocked(checkEventVenueSuitability)

const RESULT: EventVenueSuitabilityResult = {
  event_id: 7,
  event_name: 'Regional Partner Conference',
  suitable: false,
  venues: [
    {
      booking_id: 14,
      venue_id: 3,
      venue_name: 'Main Hall',
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

  it('shows each venue result and the separate combined-capacity result', async () => {
    mockCheck.mockResolvedValue(RESULT)
    render(<EventVenueSuitability eventId={7} />)

    expect(await screen.findByText('Main Hall: Suitable')).toBeInTheDocument()
    expect(screen.getByText('Garden Room: Needs attention')).toBeInTheDocument()
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
})
