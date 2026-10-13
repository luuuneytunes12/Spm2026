/**
 * SCRUM-50 "View Attendee List for Event".
 *   AC1  registered count and attendees by name are shown
 *   AC2  each attendee's registration status is shown
 * Negatives: registration not enabled -> the section is not rendered by the
 * pages; a server refusal (404 / 409 / 403) is shown, never a list.
 */
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../lib/api'
import { AttendeeListSection } from './AttendeeListSection'

vi.mock('../lib/registrations', async () => {
  const actual = await vi.importActual<typeof import('../lib/registrations')>('../lib/registrations')
  return { ...actual, listEventAttendees: vi.fn() }
})
vi.mock('../lib/events', async () => {
  const actual = await vi.importActual<typeof import('../lib/events')>('../lib/events')
  return {
    ...actual,
    getEvent: vi.fn(),
    getOwnEventActivity: vi.fn().mockResolvedValue([]),
    listOwnChangeRequests: vi.fn().mockResolvedValue([]),
  }
})

import { getEvent } from '../lib/events'
import type { EventDetail } from '../lib/events'
import { listEventAttendees } from '../lib/registrations'
import { EventView } from '../pages/events/EventView'

const mockList = vi.mocked(listEventAttendees)

const entry = (id: number, name: string, status: 'registered' | 'withdrawn') => ({
  registration_id: id,
  attendee_id: id + 10,
  name,
  status,
  registered_at: '2026-10-01T00:00:00Z',
  withdrawn_at: null,
})

beforeEach(() => vi.clearAllMocks())

describe('AttendeeListSection', () => {
  it('AC1: shows the registered count and each attendee by name', async () => {
    mockList.mockResolvedValue({
      event_id: 7,
      registered_count: 2,
      attendees: [entry(1, 'Amir', 'registered'), entry(2, 'Bea', 'registered')],
    })
    render(<AttendeeListSection eventId={7} />)

    expect(await screen.findByTestId('registered-count')).toHaveTextContent('2 registered')
    expect(screen.getByText('Amir')).toBeInTheDocument()
    expect(screen.getByText('Bea')).toBeInTheDocument()
    expect(mockList).toHaveBeenCalledWith(7)
  })

  it('AC2: shows each attendee\'s registration status', async () => {
    mockList.mockResolvedValue({
      event_id: 7,
      registered_count: 1,
      attendees: [entry(1, 'Amir', 'registered'), entry(2, 'Bea', 'withdrawn')],
    })
    render(<AttendeeListSection eventId={7} />)

    expect(await screen.findByText('Registered')).toBeInTheDocument()
    expect(screen.getByText('Withdrawn')).toBeInTheDocument()
    expect(screen.getByTestId('registered-count')).toHaveTextContent('1 registered')
  })

  it('AC1: an enabled event nobody has joined says so', async () => {
    mockList.mockResolvedValue({ event_id: 7, registered_count: 0, attendees: [] })
    render(<AttendeeListSection eventId={7} />)

    expect(await screen.findByText('No one has registered yet.')).toBeInTheDocument()
    expect(screen.getByTestId('registered-count')).toHaveTextContent('0 registered')
  })

  it('negative: a refusal is shown and no names are listed', async () => {
    mockList.mockRejectedValue(new ApiError(409, 'Registration is not enabled for this event.', [], []))
    render(<AttendeeListSection eventId={7} />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Registration is not enabled')
    expect(screen.queryByTestId('registered-count')).not.toBeInTheDocument()
  })
})

describe('Organiser event page wiring', () => {
  const base = {
    id: 7, organiser_id: 1, coordinator_id: null, coordinator: null, name: 'Summit',
    event_type: null, purpose: null, description: null, programme: null,
    proposed_start: null, proposed_end: null, expected_attendance: null,
    venue_requirements: null, room_layout_preference: null, accessibility_needs: null,
    equipment_requirements: null, equipment_items: [], special_arrangements: null,
    status: 'safety_check_passed', submitted_at: null, created_at: '2026-09-09T00:00:00Z',
    updated_at: '2026-09-09T00:00:00Z',
  }

  function renderPage(registration_enabled: boolean) {
    vi.mocked(getEvent).mockResolvedValue({ ...base, registration_enabled } as unknown as EventDetail)
    return render(
      <MemoryRouter initialEntries={['/organiser/events/7']}>
        <Routes>
          <Route path="/organiser/events/:id" element={<EventView />} />
        </Routes>
      </MemoryRouter>,
    )
  }

  it('AC1: shows the attendee list when registration is enabled', async () => {
    mockList.mockResolvedValue({ event_id: 7, registered_count: 1, attendees: [entry(1, 'Amir', 'registered')] })
    renderPage(true)

    const section = await screen.findByRole('region', { name: 'Registered attendees' })
    expect(await within(section).findByText('Amir')).toBeInTheDocument()
  })

  it('negative: registration not enabled -> no attendee list and no request', async () => {
    renderPage(false)

    await screen.findByRole('heading', { name: 'Summit' })
    expect(screen.queryByRole('region', { name: 'Registered attendees' })).not.toBeInTheDocument()
    expect(mockList).not.toHaveBeenCalled()
  })
})
