/**
 * SCRUM-96 -- Change or Cancel One Venue Booking (Coordinator side).
 *
 *   AC1  cancelling one booking cancels only that booking
 *   AC2  changing the venue (or what is needed of it) sends only that
 *        booking back to Pending for Venue Staff
 *   AC3  cancelling all lists the bookings first and asks again
 *   AC4  Venue Staff are told and the Activity Log records it -- both done by
 *        the server, in backend/tests/test_venue_booking_change_cancel.py;
 *        here the card only has to refresh the page that shows the log
 *
 * Whether the server accepts or refuses is the backend's. These cover what the
 * card offers, what it sends, and what it shows of the answer. The libs are
 * mocked.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../lib/api'
import { VenueBookingSection } from './VenueBookingSection'

vi.mock('../lib/venueBookings', async () => {
  const actual = await vi.importActual<typeof import('../lib/venueBookings')>('../lib/venueBookings')
  return {
    ...actual,
    submitVenueBookings: vi.fn(),
    listEventVenueBookings: vi.fn(),
    changeVenueBooking: vi.fn(),
    cancelVenueBooking: vi.fn(),
    listCancellableVenueBookings: vi.fn(),
    cancelAllVenueBookings: vi.fn(),
  }
})
vi.mock('../lib/venues', () => ({ listVenues: vi.fn() }))

import {
  cancelAllVenueBookings,
  cancelVenueBooking,
  changeVenueBooking,
  listCancellableVenueBookings,
  listEventVenueBookings,
} from '../lib/venueBookings'
import type { VenueBooking } from '../lib/venueBookings'
import { listVenues } from '../lib/venues'

const mockList = vi.mocked(listEventVenueBookings)
const mockChange = vi.mocked(changeVenueBooking)
const mockCancel = vi.mocked(cancelVenueBooking)
const mockPreview = vi.mocked(listCancellableVenueBookings)
const mockCancelAll = vi.mocked(cancelAllVenueBookings)
const mockVenues = vi.mocked(listVenues)

const BOOKING: VenueBooking = {
  id: 1,
  status: 'approved',
  created_at: '2026-10-01T02:00:00Z',
  event: { id: 7, name: 'Conference' },
  venue: { id: 3, name: 'Marina Hall', location: '10 Bayfront Ave', capacity: 250 },
  start_time: '2026-11-02T09:00:00Z',
  end_time: '2026-11-02T17:00:00Z',
  setup_minutes: 0,
  turnaround_minutes: 0,
  occupied_start: '2026-11-02T09:00:00Z',
  occupied_end: '2026-11-02T17:00:00Z',
  expires_at: null,
  expected_attendance: 120,
  room_layout_preference: 'Theatre',
  accessibility_needs: null,
  facilities_needs: 'Projector',
  venue_requirements: 'Main hall',
  requested_by: { name: 'Sam Tan', email: 'sam@connectsphere.test' },
  decision_notes: null,
  suggested_alternative: null,
  reviewed_by: { name: 'Vera Staff', email: 'vera@connectsphere.test' },
  reviewed_at: '2026-10-02T02:00:00Z',
}
const GARDEN: VenueBooking = {
  ...BOOKING,
  id: 2,
  status: 'pending',
  venue: { id: 5, name: 'Garden Hall', location: 'Level 2', capacity: 100 },
  reviewed_by: null,
  reviewed_at: null,
}
const SKY: VenueBooking = {
  ...BOOKING,
  id: 3,
  status: 'tentative_hold',
  venue: { id: 6, name: 'Sky Room', location: 'Roof', capacity: 80 },
  expires_at: '2026-10-20T00:00:00Z',
}
const REJECTED: VenueBooking = {
  ...BOOKING,
  id: 4,
  status: 'rejected',
  venue: { id: 8, name: 'Closed Hall', location: 'Annex', capacity: 50 },
  decision_notes: 'Closed.',
}
const CANCELLED: VenueBooking = {
  ...BOOKING,
  id: 5,
  status: 'cancelled',
  venue: { id: 9, name: 'Old Hall', location: 'Annex', capacity: 60 },
}

const VENUES = [
  { id: 3, name: 'Marina Hall', location: '10 Bayfront Ave', capacity: 250, facilities: [], is_active: true },
  { id: 5, name: 'Garden Hall', location: 'Level 2', capacity: 100, facilities: [], is_active: true },
  { id: 6, name: 'Sky Room', location: 'Roof', capacity: 80, facilities: [], is_active: true },
  { id: 7, name: 'Spare Hall', location: 'Wing C', capacity: 300, facilities: [], is_active: true },
  { id: 8, name: 'Closed Hall', location: 'Annex', capacity: 50, facilities: [], is_active: true },
  { id: 4, name: 'Retired Hall', location: 'Annex', capacity: 300, facilities: [], is_active: false },
]

function renderSection(onChanged = vi.fn()) {
  render(<VenueBookingSection eventId={7} expectedAttendance={120} onChanged={onChanged} />)
  return onChanged
}

/** One booking's row in the list. */
const row = (venue: string) =>
  screen.getByText(venue, { selector: 'strong' }).closest('li') as HTMLElement

async function loaded(...venues: string[]) {
  for (const v of venues) await screen.findByText(v, { selector: 'strong' })
}

beforeEach(() => {
  vi.resetAllMocks()
  mockList.mockResolvedValue([BOOKING, GARDEN, SKY])
  mockVenues.mockResolvedValue(VENUES)
})

// ---------------------------------------------------------------------------
// What is offered, and when
// ---------------------------------------------------------------------------

describe('which bookings can be changed or cancelled', () => {
  it.each([
    ['approved', 'Marina Hall'],
    ['pending', 'Garden Hall'],
    ['held', 'Sky Room'],
  ])('offers Change and Cancel on a %s booking', async (_name, venue) => {
    renderSection()
    await loaded(venue)

    expect(within(row(venue)).getByRole('button', { name: `Change ${venue} booking` })).toBeInTheDocument()
    expect(within(row(venue)).getByRole('button', { name: `Cancel ${venue} booking` })).toBeInTheDocument()
  })

  it('offers neither on a rejected or a cancelled booking: they are history', async () => {
    mockList.mockResolvedValue([REJECTED, CANCELLED])
    renderSection()
    await loaded('Closed Hall', 'Old Hall')

    expect(screen.queryByRole('button', { name: /^Change .* booking$/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Cancel .* booking$/ })).not.toBeInTheDocument()
  })

  it('offers Cancel all only while at least one booking is live', async () => {
    mockList.mockResolvedValue([REJECTED, CANCELLED])
    const { unmount } = render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    await loaded('Closed Hall')
    expect(screen.queryByRole('button', { name: 'Cancel all venue bookings' })).not.toBeInTheDocument()
    unmount()

    mockList.mockResolvedValue([BOOKING])
    render(<VenueBookingSection eventId={7} expectedAttendance={120} />)
    expect(await screen.findByRole('button', { name: 'Cancel all venue bookings' })).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// AC2 -- change one booking
// ---------------------------------------------------------------------------

async function openChange(venue: string) {
  const user = userEvent.setup()
  await loaded(venue)
  await user.click(within(row(venue)).getByRole('button', { name: `Change ${venue} booking` }))
  return { user, panel: within(await screen.findByRole('region', { name: `Change ${venue} booking` })) }
}

describe('SCRUM-96 AC2 - the change form', () => {
  it('opens on the booking, with its venue and what is needed already filled in', async () => {
    renderSection()
    const { panel } = await openChange('Marina Hall')

    expect(panel.getByLabelText('Venue')).toHaveValue('3')
    expect(panel.getByLabelText('Room layout')).toHaveValue('Theatre')
    expect(panel.getByLabelText('Accessibility needs')).toHaveValue('')
    expect(panel.getByLabelText('Facilities')).toHaveValue('Projector')
  })

  it('offers every active venue, but not one the event already has another booking at', async () => {
    renderSection()
    const { panel } = await openChange('Marina Hall')

    const options = Array.from(panel.getByLabelText('Venue').querySelectorAll('option')).map(
      (o) => o.textContent,
    )
    expect(options.some((o) => o?.includes('Marina Hall'))).toBe(true) // where it is now
    expect(options.some((o) => o?.includes('Spare Hall'))).toBe(true)
    expect(options.some((o) => o?.includes('Garden Hall'))).toBe(false) // another live booking
    expect(options.some((o) => o?.includes('Sky Room'))).toBe(false) // another live booking
    expect(options.some((o) => o?.includes('Retired Hall'))).toBe(false) // inactive
  })

  it('offers a venue whose booking for this event was rejected or cancelled', async () => {
    mockList.mockResolvedValue([BOOKING, REJECTED])
    renderSection()
    const { panel } = await openChange('Marina Hall')

    const options = Array.from(panel.getByLabelText('Venue').querySelectorAll('option')).map((o) => o.textContent)
    expect(options.some((o) => o?.includes('Closed Hall'))).toBe(true)
  })

  it('does not ask for a time: the booking’s time is the event’s', async () => {
    renderSection()
    const { panel } = await openChange('Marina Hall')

    expect(panel.queryByLabelText(/start|end|time/i)).not.toBeInTheDocument()
  })

  it('warns that an approved booking goes back to Pending, and stops counting as approved', async () => {
    renderSection()
    const { panel } = await openChange('Marina Hall')

    expect(panel.getByText(/go back to pending/i)).toBeInTheDocument()
    expect(panel.getByText(/not count as approved until venue staff approve it again/i)).toBeInTheDocument()
  })

  it('says a pending booking’s change will be seen by Venue Staff', async () => {
    renderSection()
    const { panel } = await openChange('Garden Hall')

    expect(panel.getByText(/venue staff will see the change/i)).toBeInTheDocument()
    expect(panel.queryByText(/go back to pending/i)).not.toBeInTheDocument()
  })

  it('says a held booking’s hold is released', async () => {
    renderSection()
    const { panel } = await openChange('Sky Room')

    expect(panel.getByText(/hold will be released/i)).toBeInTheDocument()
  })

  it('has nothing to save until something is changed', async () => {
    renderSection()
    const { panel } = await openChange('Marina Hall')

    expect(panel.getByRole('button', { name: 'Save change' })).toBeDisabled()
  })

  it('discards the change without sending anything', async () => {
    renderSection()
    const { user, panel } = await openChange('Marina Hall')
    await user.selectOptions(panel.getByLabelText('Venue'), 'Spare Hall — Wing C (capacity 300)')

    await user.click(panel.getByRole('button', { name: 'Discard changes' }))

    expect(mockChange).not.toHaveBeenCalled()
    expect(screen.queryByRole('region', { name: 'Change Marina Hall booking' })).not.toBeInTheDocument()
  })
})

describe('SCRUM-96 AC2 - saving a change', () => {
  it('sends only the new venue when only that changed', async () => {
    mockChange.mockResolvedValue({
      ...BOOKING,
      status: 'pending',
      venue: { id: 7, name: 'Spare Hall', location: 'Wing C', capacity: 300 },
      reviewed_by: null,
      reviewed_at: null,
    })
    renderSection()
    const { user, panel } = await openChange('Marina Hall')

    await user.selectOptions(panel.getByLabelText('Venue'), 'Spare Hall — Wing C (capacity 300)')
    await user.click(panel.getByRole('button', { name: 'Save change' }))

    await waitFor(() => expect(mockChange).toHaveBeenCalledWith(1, { venue_id: 7 }))
  })

  it('sends only the need that changed', async () => {
    mockChange.mockResolvedValue({ ...BOOKING, status: 'pending', room_layout_preference: 'Classroom' })
    renderSection()
    const { user, panel } = await openChange('Marina Hall')

    const layout = panel.getByLabelText('Room layout')
    await user.clear(layout)
    await user.type(layout, 'Classroom')
    await user.click(panel.getByRole('button', { name: 'Save change' }))

    await waitFor(() => expect(mockChange).toHaveBeenCalledWith(1, { room_layout_preference: 'Classroom' }))
  })

  it('sends a need that was emptied as null: it goes back to what the event says', async () => {
    mockChange.mockResolvedValue({ ...BOOKING, status: 'pending', facilities_needs: null })
    renderSection()
    const { user, panel } = await openChange('Marina Hall')

    await user.clear(panel.getByLabelText('Facilities'))
    await user.click(panel.getByRole('button', { name: 'Save change' }))

    await waitFor(() => expect(mockChange).toHaveBeenCalledWith(1, { facilities_needs: null }))
  })

  it('shows that booking as pending, and leaves the other bookings as they were', async () => {
    mockChange.mockResolvedValue({
      ...BOOKING,
      status: 'pending',
      room_layout_preference: 'Classroom',
      reviewed_by: null,
      reviewed_at: null,
    })
    renderSection()
    const { user, panel } = await openChange('Marina Hall')
    const layout = panel.getByLabelText('Room layout')
    await user.clear(layout)
    await user.type(layout, 'Classroom')

    await user.click(panel.getByRole('button', { name: 'Save change' }))

    await waitFor(() => expect(within(row('Marina Hall')).getByText('Pending review')).toBeInTheDocument())
    expect(within(row('Garden Hall')).getByText('Pending review')).toBeInTheDocument()
    expect(within(row('Sky Room')).getByText('Tentative hold')).toBeInTheDocument()
    expect(within(row('Marina Hall')).queryByText('Approved')).not.toBeInTheDocument()
  })

  it('closes the form, says it went back to Venue Staff, and refreshes the page', async () => {
    mockChange.mockResolvedValue({ ...BOOKING, status: 'pending', room_layout_preference: 'Classroom' })
    const onChanged = renderSection()
    const { user, panel } = await openChange('Marina Hall')
    const layout = panel.getByLabelText('Room layout')
    await user.clear(layout)
    await user.type(layout, 'Classroom')

    await user.click(panel.getByRole('button', { name: 'Save change' }))

    expect(await screen.findByRole('status')).toHaveTextContent(/sent back to venue staff for review/i)
    expect(screen.queryByRole('region', { name: 'Change Marina Hall booking' })).not.toBeInTheDocument()
    expect(onChanged).toHaveBeenCalled()
  })

  it('shows the server’s reason and keeps the form open when it refuses', async () => {
    mockChange.mockRejectedValue(new ApiError(409, 'This event already has a live booking request for Spare Hall.'))
    const onChanged = renderSection()
    const { user, panel } = await openChange('Marina Hall')
    await user.selectOptions(panel.getByLabelText('Venue'), 'Spare Hall — Wing C (capacity 300)')

    await user.click(panel.getByRole('button', { name: 'Save change' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('already has a live booking request')
    expect(screen.getByRole('region', { name: 'Change Marina Hall booking' })).toBeInTheDocument()
    expect(within(row('Marina Hall')).getByText('Approved')).toBeInTheDocument()
    expect(onChanged).not.toHaveBeenCalled()
  })

  it('says something useful when the server cannot be reached', async () => {
    mockChange.mockRejectedValue(new Error('network down'))
    renderSection()
    const { user, panel } = await openChange('Marina Hall')
    await user.selectOptions(panel.getByLabelText('Venue'), 'Spare Hall — Wing C (capacity 300)')

    await user.click(panel.getByRole('button', { name: 'Save change' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not change/i)
  })
})

// ---------------------------------------------------------------------------
// AC1 -- cancel one booking
// ---------------------------------------------------------------------------

async function openCancel(venue: string) {
  const user = userEvent.setup()
  await loaded(venue)
  await user.click(within(row(venue)).getByRole('button', { name: `Cancel ${venue} booking` }))
  return { user, dialog: within(await screen.findByRole('dialog', { name: `Cancel ${venue} booking?` })) }
}

describe('SCRUM-96 AC1 - cancelling one booking', () => {
  it('asks first, naming the venue, and sends nothing yet', async () => {
    renderSection()
    const { dialog } = await openCancel('Garden Hall')

    expect(dialog.getByText(/the other bookings are not affected/i)).toBeInTheDocument()
    expect(mockCancel).not.toHaveBeenCalled()
  })

  it('keeps the booking when the Coordinator changes their mind', async () => {
    renderSection()
    const { user, dialog } = await openCancel('Garden Hall')

    await user.click(dialog.getByRole('button', { name: 'Keep booking' }))

    expect(mockCancel).not.toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(within(row('Garden Hall')).getByText('Pending review')).toBeInTheDocument()
  })

  it('cancels only that booking, with no reason when none is given', async () => {
    mockCancel.mockResolvedValue({ ...GARDEN, status: 'cancelled' })
    const onChanged = renderSection()
    const { user, dialog } = await openCancel('Garden Hall')

    await user.click(dialog.getByRole('button', { name: 'Yes, cancel booking' }))

    await waitFor(() => expect(mockCancel).toHaveBeenCalledWith(2, undefined))
    await waitFor(() => expect(within(row('Garden Hall')).getByText('Cancelled')).toBeInTheDocument())
    expect(within(row('Marina Hall')).getByText('Approved')).toBeInTheDocument()
    expect(within(row('Sky Room')).getByText('Tentative hold')).toBeInTheDocument()
    expect(onChanged).toHaveBeenCalled()
  })

  it('sends the reason when one is given', async () => {
    mockCancel.mockResolvedValue({ ...GARDEN, status: 'cancelled' })
    renderSection()
    const { user, dialog } = await openCancel('Garden Hall')

    await user.type(dialog.getByLabelText('Reason (optional)'), 'Moving to the main hall')
    await user.click(dialog.getByRole('button', { name: 'Yes, cancel booking' }))

    await waitFor(() => expect(mockCancel).toHaveBeenCalledWith(2, 'Moving to the main hall'))
  })

  it('takes the actions off a booking once it is cancelled', async () => {
    mockCancel.mockResolvedValue({ ...GARDEN, status: 'cancelled' })
    renderSection()
    const { user, dialog } = await openCancel('Garden Hall')

    await user.click(dialog.getByRole('button', { name: 'Yes, cancel booking' }))

    await waitFor(() => expect(within(row('Garden Hall')).getByText('Cancelled')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: 'Change Garden Hall booking' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cancel Garden Hall booking' })).not.toBeInTheDocument()
  })

  it('shows the server’s reason when it refuses, and the booking stays', async () => {
    mockCancel.mockRejectedValue(new ApiError(409, 'This booking is already cancelled.'))
    const onChanged = renderSection()
    const { user, dialog } = await openCancel('Garden Hall')

    await user.click(dialog.getByRole('button', { name: 'Yes, cancel booking' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('already cancelled')
    expect(within(row('Garden Hall')).getByText('Pending review')).toBeInTheDocument()
    expect(onChanged).not.toHaveBeenCalled()
  })

  it('says something useful when the server cannot be reached', async () => {
    mockCancel.mockRejectedValue(new Error('network down'))
    renderSection()
    const { user, dialog } = await openCancel('Garden Hall')

    await user.click(dialog.getByRole('button', { name: 'Yes, cancel booking' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not cancel/i)
  })
})

// ---------------------------------------------------------------------------
// AC3 -- cancel all: listed first, confirmed again
// ---------------------------------------------------------------------------

async function startCancelAll() {
  const user = userEvent.setup()
  await loaded('Marina Hall')
  await user.click(screen.getByRole('button', { name: 'Cancel all venue bookings' }))
  return user
}

describe('SCRUM-96 AC3 - cancelling all of an event’s bookings', () => {
  beforeEach(() => {
    mockPreview.mockResolvedValue([BOOKING, GARDEN, SKY])
  })

  it('first asks whether to, saying the event itself is not cancelled; nothing is listed or sent yet', async () => {
    renderSection()
    await startCancelAll()

    const first = await screen.findByRole('dialog', { name: 'Cancel all venue bookings?' })
    expect(within(first).getByText(/the event itself is not cancelled/i)).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Bookings to be cancelled' })).not.toBeInTheDocument()
    expect(mockPreview).not.toHaveBeenCalled()
    expect(mockCancelAll).not.toHaveBeenCalled()
  })

  it('then lists the bookings to be cancelled, and asks again', async () => {
    renderSection()
    const user = await startCancelAll()

    await user.click(within(await screen.findByRole('dialog', { name: 'Cancel all venue bookings?' })).getByRole('button', { name: 'Continue' }))

    const second = await screen.findByRole('dialog', { name: 'Confirm cancelling these bookings' })
    const items = within(within(second).getByRole('list', { name: 'Bookings to be cancelled' })).getAllByRole('listitem')
    expect(items.map((i) => i.textContent)).toEqual([
      expect.stringContaining('Marina Hall'),
      expect.stringContaining('Garden Hall'),
      expect.stringContaining('Sky Room'),
    ])
    expect(mockCancelAll).not.toHaveBeenCalled()
  })

  it('lists what the server says is live, not what the page remembers', async () => {
    mockPreview.mockResolvedValue([BOOKING, GARDEN, SKY, { ...BOOKING, id: 9, venue: { id: 7, name: 'Spare Hall', location: 'Wing C', capacity: 300 } }])
    renderSection()
    const user = await startCancelAll()

    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Continue' }))

    const list = await screen.findByRole('list', { name: 'Bookings to be cancelled' })
    expect(within(list).getByText(/Spare Hall/)).toBeInTheDocument()
  })

  it('cancels exactly the listed bookings once confirmed the second time', async () => {
    mockCancelAll.mockResolvedValue([BOOKING, GARDEN, SKY].map((b) => ({ ...b, status: 'cancelled' as const })))
    const onChanged = renderSection()
    const user = await startCancelAll()
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Continue' }))

    await user.click(
      within(await screen.findByRole('dialog', { name: 'Confirm cancelling these bookings' })).getByRole('button', { name: 'Cancel all these bookings' }),
    )

    await waitFor(() => expect(mockCancelAll).toHaveBeenCalledWith(7, [1, 2, 3], undefined))
    await waitFor(() => expect(screen.getAllByText('Cancelled')).toHaveLength(3))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(onChanged).toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: 'Cancel all venue bookings' })).not.toBeInTheDocument()
  })

  it('sends the reason when one is given', async () => {
    mockCancelAll.mockResolvedValue([])
    renderSection()
    const user = await startCancelAll()
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Continue' }))
    const second = within(await screen.findByRole('dialog', { name: 'Confirm cancelling these bookings' }))

    await user.type(second.getByLabelText('Reason (optional)'), 'Moving venue entirely')
    await user.click(second.getByRole('button', { name: 'Cancel all these bookings' }))

    await waitFor(() => expect(mockCancelAll).toHaveBeenCalledWith(7, [1, 2, 3], 'Moving venue entirely'))
  })

  it('cancels nothing if the Coordinator keeps the bookings at the first question', async () => {
    renderSection()
    const user = await startCancelAll()

    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Keep bookings' }))

    expect(mockPreview).not.toHaveBeenCalled()
    expect(mockCancelAll).not.toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('cancels nothing if the Coordinator goes back from the list', async () => {
    renderSection()
    const user = await startCancelAll()
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Continue' }))

    await user.click(within(await screen.findByRole('dialog', { name: 'Confirm cancelling these bookings' })).getByRole('button', { name: 'Go back' }))

    expect(mockCancelAll).not.toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('does not offer to confirm when the list is empty', async () => {
    mockPreview.mockResolvedValue([])
    renderSection()
    const user = await startCancelAll()

    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Continue' }))

    expect(await screen.findByText(/no live bookings to cancel/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cancel all these bookings' })).not.toBeInTheDocument()
  })

  it('when the list had gone stale, says so, shows the fresh list, and asks again rather than retrying', async () => {
    mockPreview
      .mockResolvedValueOnce([BOOKING, GARDEN, SKY])
      .mockResolvedValueOnce([BOOKING, GARDEN, SKY, { ...BOOKING, id: 9, venue: { id: 7, name: 'Spare Hall', location: 'Wing C', capacity: 300 } }])
    mockCancelAll.mockRejectedValue(new ApiError(409, 'The bookings changed since the list was shown.'))
    renderSection()
    const user = await startCancelAll()
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Continue' }))
    await user.click(
      within(await screen.findByRole('dialog', { name: 'Confirm cancelling these bookings' })).getByRole('button', { name: 'Cancel all these bookings' }),
    )

    expect(await screen.findByRole('alert')).toHaveTextContent('changed since the list was shown')
    await waitFor(() => expect(within(screen.getByRole('list', { name: 'Bookings to be cancelled' })).getByText(/Spare Hall/)).toBeInTheDocument())
    expect(mockCancelAll).toHaveBeenCalledTimes(1) // not retried behind the Coordinator's back
    expect(screen.getByRole('button', { name: 'Cancel all these bookings' })).toBeInTheDocument()
  })

  it('says something useful when the server cannot be reached', async () => {
    mockCancelAll.mockRejectedValue(new Error('network down'))
    renderSection()
    const user = await startCancelAll()
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Continue' }))
    await user.click(
      within(await screen.findByRole('dialog', { name: 'Confirm cancelling these bookings' })).getByRole('button', { name: 'Cancel all these bookings' }),
    )

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not cancel/i)
  })
})
