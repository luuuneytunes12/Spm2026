/**
 * SCRUM-39 -- Submit Venue Booking Request (Coordinator side), and the
 * Coordinator's side of "Approve or Reject Venue Booking Request": seeing
 * Venue Staff's decision and resubmitting after a rejection.
 * Whether the API accepts or refuses is backend/tests/test_venue_booking_request.py;
 * these tests cover what the card does with the answer.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
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
  decision_notes: null,
  suggested_alternative: null,
  reviewed_by: null,
  reviewed_at: null,
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

const DECIDED = { reviewed_by: { name: 'Vera Staff', email: 'vera@connectsphere.test' }, reviewed_at: '2026-10-02T03:00:00Z' }
const REJECTED: VenueBooking = {
  ...BOOKING,
  ...DECIDED,
  status: 'rejected',
  decision_notes: 'Closed for repairs.',
  suggested_alternative: 'Try Hall B.',
}

describe('AC4 - the outcome is visible to the Event Coordinator', () => {
  it('shows an approval with who decided, and no form', async () => {
    mockList.mockResolvedValue([{ ...BOOKING, ...DECIDED, status: 'approved' }])
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    const outcome = await screen.findByRole('status')
    expect(outcome).toHaveTextContent('Marina Hall')
    expect(outcome).toHaveTextContent('Approved')
    expect(outcome).toHaveTextContent('Vera Staff')
    expect(screen.queryByRole('button', { name: 'Submit booking request' })).not.toBeInTheDocument()
  })

  it('shows no decision while the request is still pending', async () => {
    mockList.mockResolvedValue([BOOKING])
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    expect(await screen.findByRole('status')).toHaveTextContent('Pending review')
    expect(screen.queryByText('Decided')).not.toBeInTheDocument()
  })
})

describe('AC3 - the reason and alternative are visible to the Event Coordinator', () => {
  it('shows a rejection with its reason, its alternative and who decided', async () => {
    mockList.mockResolvedValue([REJECTED])
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    const outcome = await screen.findByRole('status')
    expect(outcome).toHaveTextContent('Rejected')
    expect(outcome).toHaveTextContent('Closed for repairs.')
    expect(outcome).toHaveTextContent('Try Hall B.')
    expect(outcome).toHaveTextContent('Vera Staff')
  })

  it('leaves out whichever of the two was not given', async () => {
    mockList.mockResolvedValue([{ ...REJECTED, decision_notes: null }])
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    const outcome = within(await screen.findByRole('status'))
    expect(outcome.getByText('Suggested alternative')).toBeInTheDocument()
    expect(outcome.queryByText('Reason')).not.toBeInTheDocument()
  })
})

describe('AC5 - a rejected request can be resubmitted', () => {
  it('offers the form again after a rejection and submits a new request', async () => {
    mockList.mockResolvedValue([REJECTED])
    mockSubmit.mockResolvedValue({ ...BOOKING, id: 2 })
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    await userEvent.selectOptions(await screen.findByLabelText('Venue'), '3')
    await userEvent.click(screen.getByRole('button', { name: 'Submit booking request' }))

    expect(mockSubmit).toHaveBeenCalledWith(7, 3)
    expect(await screen.findByText(/Pending review/)).toBeInTheDocument()
    // The rejection it replaces is kept, with its reason, under Earlier requests.
    const earlier = screen.getByRole('list')
    expect(earlier).toHaveTextContent('Rejected')
    expect(earlier).toHaveTextContent('Closed for repairs.')
  })

  it('offers the form again however many times the request has been rejected', async () => {
    mockList.mockResolvedValue([3, 2, 1].map((id) => ({ ...REJECTED, id, decision_notes: `Rejection ${id}` })))
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    expect(await screen.findByRole('button', { name: 'Submit booking request' })).toBeEnabled()
    expect(screen.getByRole('status')).toHaveTextContent('Rejection 3') // the latest answer
    expect(screen.getAllByRole('listitem').map((li) => li.textContent)).toEqual([
      expect.stringContaining('Rejection 2'),
      expect.stringContaining('Rejection 1'),
    ])
  })
})
