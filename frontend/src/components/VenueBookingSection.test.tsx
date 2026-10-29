/**
 * SCRUM-39 -- Submit Venue Booking Request (Coordinator side), and the
 * Coordinator's side of "Approve or Reject Venue Booking Request": seeing
 * Venue Staff's decision and asking again after a rejection.
 * Whether the API accepts or refuses is backend/tests/test_venue_booking_request.py;
 * these tests cover what the card does with the answer.
 *
 *   SCRUM-39 AC1  no venue selected: the error is shown, nothing is listed
 *   SCRUM-39 AC2  one or more venues: each is sent, with the needs for that venue
 *   SCRUM-39 AC5  every booking is listed with its own status
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../lib/api'
import { formatTimestamp } from '../lib/events'
import { VenueBookingSection } from './VenueBookingSection'

vi.mock('../lib/venueBookings', async () => {
  const actual = await vi.importActual<typeof import('../lib/venueBookings')>('../lib/venueBookings')
  return { ...actual, submitVenueBookings: vi.fn(), listEventVenueBookings: vi.fn() }
})
vi.mock('../lib/venues', () => ({ listVenues: vi.fn() }))

import { listEventVenueBookings, submitVenueBookings } from '../lib/venueBookings'
import { formatBookingPeriods } from '../lib/venueBookings'
import type { VenueBooking } from '../lib/venueBookings'
import { listVenues } from '../lib/venues'

const mockList = vi.mocked(listEventVenueBookings)
const mockSubmit = vi.mocked(submitVenueBookings)
const mockVenues = vi.mocked(listVenues)

const BOOKING: VenueBooking = {
  id: 1,
  status: 'pending',
  created_at: '2026-10-01T02:00:00Z',
  event: { id: 7, name: 'Conference' },
  venue: { id: 3, name: 'Marina Hall', location: '10 Bayfront Ave', capacity: 250 },
  start_time: '2026-11-02T09:00:00Z',
  end_time: '2026-11-02T17:00:00Z',
  setup_minutes: 30,
  turnaround_minutes: 45,
  occupied_start: '2026-11-02T08:30:00Z',
  occupied_end: '2026-11-02T17:45:00Z',
  expires_at: null,
  expected_attendance: 120,
  room_layout_preference: 'Theatre',
  accessibility_needs: 'Step-free access',
  facilities_needs: 'Main hall',
  venue_requirements: 'Main hall',
  requested_by: { name: 'Sam Tan', email: 'sam@connectsphere.test' },
  decision_notes: null,
  suggested_alternative: null,
  reviewed_by: null,
  reviewed_at: null,
}
const BOOKING_B: VenueBooking = {
  ...BOOKING,
  id: 2,
  venue: { id: 5, name: 'Bay Room', location: 'Level 2', capacity: 100 },
}

beforeEach(() => {
  vi.resetAllMocks()
  mockList.mockResolvedValue([])
  mockVenues.mockResolvedValue([
    { id: 3, name: 'Marina Hall', location: '10 Bayfront Ave', capacity: 250, facilities: [], is_active: true },
    { id: 5, name: 'Bay Room', location: 'Level 2', capacity: 100, facilities: [], is_active: true },
    { id: 4, name: 'Old Hall', location: 'Annex', capacity: 300, facilities: [], is_active: false },
  ])
})

const submitButton = () => screen.findByRole('button', { name: 'Submit booking request' })
const tick = async (name: RegExp) => userEvent.click(await screen.findByRole('checkbox', { name }))

describe('SCRUM-39 AC1 - no venue selected', () => {
  it('shows the server error and lists no booking when submitted with no venue', async () => {
    mockSubmit.mockRejectedValue(new ApiError(422, 'Select a venue before submitting the booking request.'))
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    await userEvent.click(await submitButton())
    expect(mockSubmit).toHaveBeenCalledWith(7, [])
    expect(await screen.findByRole('alert')).toHaveTextContent('Select a venue')
    expect(screen.queryByRole('list', { name: /venue bookings/i })).not.toBeInTheDocument()
  })

  it('offers every active venue, flagging one too small rather than hiding it', async () => {
    render(<VenueBookingSection eventId={7} expectedAttendance={300} />)
    expect(await screen.findByRole('checkbox', { name: /Marina Hall.*too small/ })).toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: /Old Hall/ })).not.toBeInTheDocument()
    expect(mockVenues).toHaveBeenCalledWith()
  })

  it('says so when the venues cannot be loaded', async () => {
    mockVenues.mockRejectedValue(new ApiError(500, 'venues down'))
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('venues down')
  })

  it('does not treat a failed booking lookup as an empty booking list and allows retry', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    mockList
      .mockRejectedValueOnce(new ApiError(503, 'Booking records could not be loaded.'))
      .mockResolvedValueOnce([BOOKING])
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Booking records could not be loaded.')
    expect(screen.getByText(/cannot submit another request yet/)).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /Marina Hall/ })).toBeDisabled()

    await userEvent.click(screen.getByRole('button', { name: 'Retry loading bookings' }))
    expect(
      await screen.findByRole('checkbox', { name: /Marina Hall.*already requested/ }),
    ).toBeDisabled()
    expect(mockList).toHaveBeenCalledTimes(2)
    consoleError.mockRestore()
  })
})

describe('SCRUM-39 AC2 - one or more venues are submitted', () => {
  it('sends one chosen venue and lists the new booking as pending', async () => {
    mockSubmit.mockResolvedValue([BOOKING])
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    await tick(/Marina Hall/)
    await userEvent.click(await submitButton())
    expect(mockSubmit).toHaveBeenCalledWith(7, [
      {
        venue_id: 3,
        expected_attendance: 120,
        room_layout_preference: '',
        accessibility_needs: '',
        facilities_needs: '',
      },
    ])
    const list = await screen.findByRole('list', { name: /venue bookings/i })
    expect(list).toHaveTextContent('Marina Hall')
    expect(list).toHaveTextContent('Pending review')
  })

  it('sends every ticked venue together, each with the needs typed for that venue', async () => {
    mockSubmit.mockResolvedValue([BOOKING, BOOKING_B])
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    await tick(/Marina Hall/)
    await tick(/Bay Room/)
    await userEvent.type(screen.getByLabelText('Room layout for Marina Hall'), 'Banquet')
    await userEvent.type(screen.getByLabelText('Facilities for Bay Room'), 'Two microphones')
    await userEvent.click(await submitButton())

    expect(mockSubmit).toHaveBeenCalledWith(7, [
      {
        venue_id: 3,
        expected_attendance: 120,
        room_layout_preference: 'Banquet',
        accessibility_needs: '',
        facilities_needs: '',
      },
      {
        venue_id: 5,
        expected_attendance: 120,
        room_layout_preference: '',
        accessibility_needs: '',
        facilities_needs: 'Two microphones',
      },
    ])
    const list = await screen.findByRole('list', { name: /venue bookings/i })
    expect(within(list).getAllByRole('listitem')).toHaveLength(2)
  })

  it('defaults attendance to the event total but sends a separate override per venue', async () => {
    mockSubmit.mockResolvedValue([BOOKING, BOOKING_B])
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    await tick(/Marina Hall/)
    await tick(/Bay Room/)
    await userEvent.clear(screen.getByLabelText('Expected attendance for Bay Room'))
    await userEvent.type(screen.getByLabelText('Expected attendance for Bay Room'), '35')
    await userEvent.click(await submitButton())

    expect(mockSubmit).toHaveBeenCalledWith(7, [
      expect.objectContaining({ venue_id: 3, expected_attendance: 120 }),
      expect.objectContaining({ venue_id: 5, expected_attendance: 35 }),
    ])
  })

  it('shows needs fields only for a ticked venue, and drops them when it is unticked', async () => {
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    expect(screen.queryByLabelText('Room layout for Marina Hall')).not.toBeInTheDocument()
    await tick(/Marina Hall/)
    expect(screen.getByLabelText('Room layout for Marina Hall')).toBeInTheDocument()
    await tick(/Marina Hall/)
    expect(screen.queryByLabelText('Room layout for Marina Hall')).not.toBeInTheDocument()
  })

  it('clears the selection after a successful submit', async () => {
    mockSubmit.mockResolvedValue([BOOKING])
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    await tick(/Bay Room/)
    await userEvent.click(await submitButton())
    await screen.findByRole('list', { name: /venue bookings/i })
    expect(screen.getByRole('checkbox', { name: /Bay Room/ })).not.toBeChecked()
  })

  it('will not tick a venue that already has a live request', async () => {
    mockList.mockResolvedValue([BOOKING])
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    const marina = await screen.findByRole('checkbox', { name: /Marina Hall.*already requested/ })
    expect(marina).toBeDisabled()
    expect(screen.getByRole('checkbox', { name: /Bay Room/ })).toBeEnabled()
  })

  it('shows the server error when the request is refused, keeping the selection', async () => {
    mockSubmit.mockRejectedValue(new ApiError(409, 'This event already has a venue booking request for Marina Hall.'))
    render(<VenueBookingSection eventId={7} expectedAttendance={null} />)
    await tick(/Marina Hall/)
    await userEvent.click(await submitButton())
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('already has'))
    expect(screen.getByRole('checkbox', { name: /Marina Hall/ })).toBeChecked()
    expect(screen.getByRole('button', { name: 'Submit booking request' })).toBeEnabled()
  })
})

describe('submitting tells the page, so it can show the event moving into planning', () => {
  it('calls onChanged once venues have been requested, and not when the request is refused', async () => {
    const onChanged = vi.fn()
    mockSubmit.mockRejectedValueOnce(new ApiError(422, 'Select a venue before submitting the booking request.'))
    mockSubmit.mockResolvedValueOnce([BOOKING])
    render(<VenueBookingSection eventId={7} expectedAttendance={120} onChanged={onChanged} />)

    await userEvent.click(await submitButton())
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(onChanged).not.toHaveBeenCalled()

    await tick(/Marina Hall/)
    await userEvent.click(await submitButton())
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1))
  })
})

describe('SCRUM-39 AC5 - every booking is listed with its own status', () => {
  it('lists each booking under the event with its own status', async () => {
    mockList.mockResolvedValue([
      { ...BOOKING, status: 'approved', reviewed_at: '2026-10-02T03:00:00Z' },
      { ...BOOKING_B, status: 'pending' },
    ])
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    const items = within(await screen.findByRole('list', { name: /venue bookings/i })).getAllByRole('listitem')
    expect(items[0]).toHaveTextContent('Marina Hall')
    expect(items[0]).toHaveTextContent('Approved')
    expect(items[1]).toHaveTextContent('Bay Room')
    expect(items[1]).toHaveTextContent('Pending review')
  })

  it('lists nothing when the event has no booking yet', async () => {
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    await screen.findByRole('checkbox', { name: /Marina Hall/ })
    expect(screen.queryByRole('list', { name: /venue bookings/i })).not.toBeInTheDocument()
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

describe('the outcome is visible to the Event Coordinator', () => {
  it('shows an approval with who decided', async () => {
    mockList.mockResolvedValue([{ ...BOOKING, ...DECIDED, status: 'approved' }])
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    const item = within(await screen.findByRole('list', { name: /venue bookings/i })).getByRole('listitem')
    expect(item).toHaveTextContent('Marina Hall')
    expect(item).toHaveTextContent('Approved')
    expect(item).toHaveTextContent('Vera Staff')
  })

  it('shows no decision while the request is still pending', async () => {
    mockList.mockResolvedValue([BOOKING])
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    expect(await screen.findByRole('list', { name: /venue bookings/i })).toHaveTextContent('Pending review')
    expect(screen.queryByText('Decided')).not.toBeInTheDocument()
  })

  it('shows a rejection with its reason, its alternative and who decided', async () => {
    mockList.mockResolvedValue([REJECTED])
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    const item = within(await screen.findByRole('list', { name: /venue bookings/i })).getByRole('listitem')
    expect(item).toHaveTextContent('Rejected')
    expect(item).toHaveTextContent('Closed for repairs.')
    expect(item).toHaveTextContent('Try Hall B.')
    expect(item).toHaveTextContent('Vera Staff')
  })

  it('leaves out whichever of reason and alternative was not given', async () => {
    mockList.mockResolvedValue([{ ...REJECTED, decision_notes: null }])
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    const item = within(await screen.findByRole('listitem'))
    expect(item.getByText('Suggested alternative')).toBeInTheDocument()
    expect(item.queryByText('Reason')).not.toBeInTheDocument()
  })

  it('lets a rejected venue be ticked again, however many times it has been rejected', async () => {
    mockList.mockResolvedValue([3, 2, 1].map((id) => ({ ...REJECTED, id, decision_notes: `Rejection ${id}` })))
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    expect(await screen.findByRole('checkbox', { name: /Marina Hall/ })).toBeEnabled()
    expect(screen.getAllByRole('listitem').map((li) => li.textContent)).toEqual([
      expect.stringContaining('Rejection 3'),
      expect.stringContaining('Rejection 2'),
      expect.stringContaining('Rejection 1'),
    ])
  })
})

describe('SCRUM-78 AC6 - bookings show the event time, setup and turnaround', () => {
  it('lists Event, Setup and Turnaround periods on each booking', async () => {
    mockList.mockResolvedValue([BOOKING])
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    const periods = await screen.findByLabelText('Venue time for Marina Hall')
    expect(periods).toHaveTextContent(formatBookingPeriods(BOOKING))
    expect(periods.textContent).toMatch(/^Event .*\d\d:\d\d.* \| Setup .*\d\d:\d\d.* \| Turnaround .*\d\d:\d\d.*$/)
  })
})

describe('SCRUM-92 AC5 - a flagged booking is marked for the Coordinator', () => {
  it('AC5: shows a text marker saying it is not counted as approved until resolved', async () => {
    mockList.mockResolvedValue([{ ...BOOKING, status: 'approved', conflict_flagged: true }])
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    expect(await screen.findByText(/Conflict flagged - not counted as approved until resolved/)).toBeInTheDocument()
  })

  it('AC3: an unflagged approved booking carries no marker', async () => {
    mockList.mockResolvedValue([{ ...BOOKING, status: 'approved', conflict_flagged: false }])
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    await screen.findByLabelText('Venue time for Marina Hall')
    expect(screen.queryByText(/Conflict flagged/)).not.toBeInTheDocument()
  })
})

describe('Tentative hold - the Coordinator sees it on the Event', () => {
  const HELD: VenueBooking = {
    ...BOOKING,
    status: 'tentative_hold',
    expires_at: '2030-01-02T02:00:00Z',
    hold_action: 'Confirm final headcount',
  }

  it('AC4: shows Tentative Hold with its expiry and the required action', async () => {
    mockList.mockResolvedValue([HELD])
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    const [item] = within(await screen.findByRole('list', { name: /venue bookings/i })).getAllByRole('listitem')
    const note = within(item).getByRole('note')
    expect(within(item).getByText('Tentative Hold')).toBeInTheDocument() // the status badge
    expect(note).toHaveTextContent('Held until')
    expect(note).toHaveTextContent(formatTimestamp(HELD.expires_at) as string)
    expect(note).toHaveTextContent('Required action: Confirm final headcount')
  })

  it('a held venue counts as already requested', async () => {
    mockList.mockResolvedValue([HELD])
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    expect(await screen.findByRole('checkbox', { name: /Marina Hall.*already requested/ })).toBeDisabled()
  })

  it('frozen literal: a pending booking carries no hold note', async () => {
    mockList.mockResolvedValue([BOOKING])
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    const [item] = within(await screen.findByRole('list', { name: /venue bookings/i })).getAllByRole('listitem')
    expect(within(item).queryByRole('note')).not.toBeInTheDocument()
  })
})

describe('Auto-release - a released booking stays in the history', () => {
  it('AC3: a booking released with its Event is listed as Released, never Approved', async () => {
    mockList.mockResolvedValue([
      { ...BOOKING, status: 'released', decision_notes: 'Released because the event was cancelled.' },
    ])
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    const [item] = within(await screen.findByRole('list', { name: /venue bookings/i })).getAllByRole('listitem')
    expect(within(item).getByText('Released')).toBeInTheDocument()
    expect(item).not.toHaveTextContent('Approved')
  })
})

describe('Tentative hold expiry - the Event shows it as expired, never as confirmed', () => {
  const EXPIRED: VenueBooking = {
    ...BOOKING,
    status: 'hold_expired',
    expires_at: '2030-01-02T02:00:00Z',
    hold_action: 'Confirm final headcount',
    decision_notes: 'Tentative hold expired.',
    reviewed_by: { name: 'Vera Staff', email: 'vera@connectsphere.test' },
    reviewed_at: '2026-10-02T03:00:00Z',
  }

  it('AC4: shows Hold Expired with when it lapsed, and never Approved', async () => {
    mockList.mockResolvedValue([EXPIRED])
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    const [item] = within(await screen.findByRole('list', { name: /venue bookings/i })).getAllByRole('listitem')
    expect(within(item).getByText('Hold Expired')).toBeInTheDocument()
    expect(item).not.toHaveTextContent('Approved')
    const note = within(item).getByRole('note')
    expect(note).toHaveTextContent(`The hold lapsed on ${formatTimestamp(EXPIRED.expires_at)}`)
    expect(note).toHaveTextContent('Request it again or choose another venue.')
  })

  it('AC4: an expired hold is history: no Change or Cancel, and the venue can be requested again', async () => {
    mockList.mockResolvedValue([EXPIRED])
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    const marina = await screen.findByRole('checkbox', { name: /Marina Hall/ })
    expect(marina).toBeEnabled()
    expect(marina).not.toHaveAccessibleName(/already requested/)
    expect(screen.queryByRole('button', { name: /Change Marina Hall/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Cancel Marina Hall/ })).not.toBeInTheDocument()
  })
})
