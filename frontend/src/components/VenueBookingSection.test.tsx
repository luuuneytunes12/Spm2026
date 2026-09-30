/**
 * SCRUM-39 -- Submit Venue Booking Request (Coordinator side).
 * Whether the API accepts or refuses is backend/tests/test_venue_booking_request.py;
 * these tests cover what the card does with the answer.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../lib/api'
import { VenueBookingSection } from './VenueBookingSection'

vi.mock('../lib/venueBookings', async () => {
  const actual = await vi.importActual<typeof import('../lib/venueBookings')>('../lib/venueBookings')
  return { ...actual, submitVenueBooking: vi.fn(), listEventVenueBookings: vi.fn() }
})
vi.mock('../lib/venues', () => ({ listVenues: vi.fn() }))

import { listEventVenueBookings, submitVenueBooking } from '../lib/venueBookings'
import type { VenueBooking } from '../lib/venueBookings'
import { listVenues } from '../lib/venues'

const mockList = vi.mocked(listEventVenueBookings)
const mockSubmit = vi.mocked(submitVenueBooking)
const mockVenues = vi.mocked(listVenues)

const BOOKING: VenueBooking = {
  id: 1,
  status: 'pending',
  created_at: '2026-10-01T02:00:00Z',
  event: { id: 7, name: 'Conference' },
  venue: { id: 3, name: 'Marina Hall', location: '10 Bayfront Ave', capacity: 250 },
  start_time: '2026-11-02T09:00:00Z',
  end_time: '2026-11-02T17:00:00Z',
  expected_attendance: 120,
  room_layout_preference: 'Theatre',
  accessibility_needs: 'Step-free access',
  venue_requirements: 'Main hall',
  requested_by: { name: 'Sam Tan', email: 'sam@connectsphere.test' },
}

beforeEach(() => {
  vi.resetAllMocks()
  mockList.mockResolvedValue([])
  mockVenues.mockResolvedValue([
    { id: 3, name: 'Marina Hall', location: '10 Bayfront Ave', capacity: 250, facilities: [], is_active: true },
    { id: 4, name: 'Old Hall', location: 'Annex', capacity: 300, facilities: [], is_active: false },
  ])
})

describe('SCRUM-39 AC1 - no venue selected', () => {
  it('shows the server error and shows no request when submitted with no venue', async () => {
    mockSubmit.mockRejectedValue(new ApiError(422, 'Select a venue before submitting the booking request.'))
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Submit booking request' }))
    expect(mockSubmit).toHaveBeenCalledWith(7, null)
    expect(await screen.findByRole('alert')).toHaveTextContent('Select a venue')
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('offers every active venue, flagging one too small rather than hiding it', async () => {
    render(<VenueBookingSection eventId={7} expectedAttendance={300} />)
    expect(await screen.findByRole('option', { name: /Marina Hall.*too small/ })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /Old Hall/ })).not.toBeInTheDocument()
    expect(mockVenues).toHaveBeenCalledWith()
  })

  it('says so when the venues cannot be loaded', async () => {
    mockVenues.mockRejectedValue(new ApiError(500, 'venues down'))
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('venues down')
  })
})

describe('SCRUM-39 AC2 - a chosen venue is submitted', () => {
  it('sends the chosen venue and replaces the form with the pending request', async () => {
    mockSubmit.mockResolvedValue(BOOKING)
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    await userEvent.selectOptions(await screen.findByLabelText('Venue'), '3')
    await userEvent.click(screen.getByRole('button', { name: 'Submit booking request' }))
    expect(mockSubmit).toHaveBeenCalledWith(7, 3)
    expect(await screen.findByRole('status')).toHaveTextContent('Marina Hall')
    expect(screen.getByRole('status')).toHaveTextContent('Pending review')
    expect(screen.queryByRole('button', { name: 'Submit booking request' })).not.toBeInTheDocument()
  })

  it('shows an existing live request instead of the form (no duplicate)', async () => {
    mockList.mockResolvedValue([BOOKING])
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    expect(await screen.findByRole('status')).toHaveTextContent('Marina Hall')
    expect(screen.queryByRole('button', { name: 'Submit booking request' })).not.toBeInTheDocument()
  })

  it('shows the server error when the request is refused, keeping the form', async () => {
    mockSubmit.mockRejectedValue(new ApiError(409, 'This event already has a venue booking request.'))
    render(<VenueBookingSection eventId={7} expectedAttendance={null} />)
    await userEvent.selectOptions(await screen.findByLabelText('Venue'), '3')
    await userEvent.click(screen.getByRole('button', { name: 'Submit booking request' }))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('already has'))
    expect(screen.getByRole('button', { name: 'Submit booking request' })).toBeEnabled()
  })
})
