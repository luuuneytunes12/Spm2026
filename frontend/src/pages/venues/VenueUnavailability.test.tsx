/**
 * Component tests for "Mark Venue Temporarily Unavailable" (SCRUM-93) on the
 * venue page. Server-side access control is covered by
 * backend/tests/test_venue_unavailability.py (AC7).
 */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { VenueView } from './VenueView'

vi.mock('../../lib/venues', async () => {
  const actual = await vi.importActual<typeof import('../../lib/venues')>('../../lib/venues')
  return {
    ...actual,
    getVenue: vi.fn(),
    getVenueAvailability: vi.fn(),
    listUnavailability: vi.fn(),
    createUnavailability: vi.fn(),
    updateUnavailability: vi.fn(),
    endUnavailabilityEarly: vi.fn(),
    deleteUnavailability: vi.fn(),
  }
})
vi.mock('../../auth/useAuth', () => ({ useAuth: vi.fn() }))

import { useAuth } from '../../auth/useAuth'
import { ApiError } from '../../lib/api'
import {
  createUnavailability,
  deleteUnavailability,
  endUnavailabilityEarly,
  getVenue,
  listUnavailability,
  updateUnavailability,
} from '../../lib/venues'
import type { Unavailability } from '../../lib/venues'

const mockAuth = vi.mocked(useAuth)
const mockList = vi.mocked(listUnavailability)
const mockCreate = vi.mocked(createUnavailability)
const mockUpdate = vi.mocked(updateUnavailability)
const mockEnd = vi.mocked(endUnavailabilityEarly)
const mockDelete = vi.mocked(deleteUnavailability)

const PERIOD: Unavailability = {
  id: 7,
  venue_id: 4,
  start_time: new Date(Date.now() - 3_600_000).toISOString(),
  end_time: new Date(Date.now() + 86_400_000).toISOString(),
  reason_category: 'Maintenance',
  reason: 'Aircon repair',
  updated_at: null,
  affected_bookings: [
    {
      booking_id: 1,
      event_id: 9,
      event_name: 'Alumni Gala',
      status: 'approved',
      start_time: new Date(Date.now() + 7_200_000).toISOString(),
      end_time: new Date(Date.now() + 10_800_000).toISOString(),
      flagged: true,
    },
  ],
}

function open(role: string) {
  mockAuth.mockReturnValue({ user: { role } } as unknown as ReturnType<typeof useAuth>)
  vi.mocked(getVenue).mockResolvedValue({
    id: 4, name: 'Marina Hall', location: 'Bayfront', capacity: 600, is_active: true,
    supported_layouts: [], facilities: [], accessibility_features: [], operating_hours: null,
    setup_minutes: null, turnaround_minutes: null,
  })
  return render(
    <MemoryRouter initialEntries={['/venues/4']}>
      <Routes>
        <Route path="/venues/:id" element={<VenueView />} />
      </Routes>
    </MemoryRouter>,
  )
}

async function fill(start: string, end: string, reason?: string) {
  const user = userEvent.setup()
  const form = await screen.findByRole('form', { name: 'Mark venue unavailable' })
  await user.type(within(form).getByLabelText('Unavailable from'), start)
  await user.type(within(form).getByLabelText('Unavailable until'), end)
  if (reason) await user.selectOptions(within(form).getByLabelText('Reason'), reason)
  return { user, form }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockList.mockResolvedValue([])
})

describe('SCRUM-93 unavailable periods', () => {
  it('ac1 saves a period with start, end and reason', async () => {
    open('venue_staff')
    mockCreate.mockResolvedValue({ ...PERIOD, affected_bookings: [] })
    const { user, form } = await fill('2030-11-02T08:00', '2030-11-02T18:00', 'Renovation')
    await user.click(within(form).getByRole('button', { name: 'Save unavailable period' }))
    expect(mockCreate).toHaveBeenCalledWith(
      4,
      expect.objectContaining({ reason_category: 'Renovation', reason: null }),
    )
    expect(await screen.findByRole('status')).toHaveTextContent('Unavailable period saved.')
  })

  it('ac1 offers the five reasons', async () => {
    open('venue_staff')
    const form = await screen.findByRole('form', { name: 'Mark venue unavailable' })
    const options = within(within(form).getByLabelText('Reason')).getAllByRole('option').map((o) => o.textContent)
    expect(options).toEqual(['Choose a reason', 'Maintenance', 'Equipment failure', 'Renovation', 'Safety concern', 'Other'])
  })

  it('ac1 asks for a reason before saving', async () => {
    open('venue_staff')
    const { user, form } = await fill('2030-11-02T08:00', '2030-11-02T18:00')
    await user.click(within(form).getByRole('button', { name: 'Save unavailable period' }))
    expect(await within(form).findByText('Choose a reason.')).toBeInTheDocument()
    expect(mockCreate).not.toHaveBeenCalled()
  })

  it('ac2 blocks the save and flags both date fields when the end is before the start', async () => {
    open('venue_staff')
    const { user, form } = await fill('2030-11-02T18:00', '2030-11-02T08:00', 'Other')
    await user.click(within(form).getByRole('button', { name: 'Save unavailable period' }))
    expect(await within(form).findByRole('alert')).toHaveTextContent('The end must be after the start.')
    expect(within(form).getByLabelText('Unavailable from')).toHaveAttribute('aria-invalid', 'true')
    expect(within(form).getByLabelText('Unavailable until')).toHaveAttribute('aria-invalid', 'true')
    expect(mockCreate).not.toHaveBeenCalled()
  })

  it('ac2 shows the server refusal against the date fields', async () => {
    open('venue_staff')
    mockCreate.mockRejectedValue(new ApiError(422, 'x', ['end_time'], ['The end must be after the start.']))
    const { user, form } = await fill('2030-11-02T08:00', '2030-11-02T18:00', 'Other')
    await user.click(within(form).getByRole('button', { name: 'Save unavailable period' }))
    expect(await within(form).findByRole('alert')).toHaveTextContent('The end must be after the start.')
  })

  it('ac3 lists periods with their reason', async () => {
    open('coordinator')
    mockList.mockResolvedValue([PERIOD])
    const list = await screen.findByRole('list', { name: 'Unavailable periods' })
    expect(list).toHaveTextContent('Maintenance')
    expect(list).toHaveTextContent('Aircon repair')
  })

  it('ac5 shows the affected bookings after saving, and says none were cancelled', async () => {
    open('venue_staff')
    mockCreate.mockResolvedValue({ ...PERIOD, recheck: { flagged: 1, cleared: 0 } })
    const { user, form } = await fill('2030-11-02T08:00', '2030-11-02T18:00', 'Maintenance')
    await user.click(within(form).getByRole('button', { name: 'Save unavailable period' }))
    expect(await screen.findByRole('status')).toHaveTextContent(/1 future booking is inside.*not been cancelled/)
    expect(screen.getByText(/Alumni Gala \(approved\)/)).toHaveTextContent('flagged for review')
  })

  it('ac6 edits a period', async () => {
    open('venue_staff')
    mockList.mockResolvedValue([PERIOD])
    mockUpdate.mockResolvedValue({ ...PERIOD, reason_category: 'Other', affected_bookings: [] })
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Edit' }))
    await user.selectOptions(screen.getByLabelText('Reason'), 'Other')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(mockUpdate).toHaveBeenCalledWith(4, 7, expect.objectContaining({ reason_category: 'Other' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Unavailable period updated.')
  })

  it('ac6 ends a period early and removes one', async () => {
    open('venue_staff')
    mockList.mockResolvedValue([PERIOD])
    mockEnd.mockResolvedValue({ ...PERIOD, end_time: new Date().toISOString(), affected_bookings: [] })
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'End early' }))
    expect(mockEnd).toHaveBeenCalledWith(4, 7)
    expect(await screen.findByRole('status')).toHaveTextContent('ended early')
    mockDelete.mockResolvedValue(undefined)
    await user.click(screen.getByRole('button', { name: 'Remove' }))
    expect(mockDelete).toHaveBeenCalledWith(4, 7)
    expect(await screen.findByText('No unavailable periods are recorded.')).toBeInTheDocument()
  })

  it('ac7 gives a Coordinator no form and no edit buttons', async () => {
    open('coordinator')
    mockList.mockResolvedValue([PERIOD])
    await screen.findByRole('list', { name: 'Unavailable periods' })
    expect(screen.queryByRole('form', { name: 'Mark venue unavailable' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Remove' })).not.toBeInTheDocument()
  })
})
