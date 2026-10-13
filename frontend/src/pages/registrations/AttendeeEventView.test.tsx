/**
 * Component tests for the Attendee's event details page. What is returned
 * (and refused) is the backend's job: backend/tests/test_attendee_event_view.py.
 */
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/api'
import App from '../../App'
import { AttendeeEventView } from './AttendeeEventView'

vi.mock('../../lib/registrations', () => ({ getAttendeeEvent: vi.fn() }))
vi.mock('../../components/AppLayout', async () => {
  const { Outlet } = await vi.importActual<typeof import('react-router')>('react-router')
  return { AppLayout: () => <Outlet /> }
})
vi.mock('../../auth/useAuth', () => ({
  useAuth: () => ({ user: { role: 'attendee' }, loading: false }),
}))

import { getAttendeeEvent } from '../../lib/registrations'
import type { AttendeeEventDetail } from '../../lib/registrations'

const mockGet = vi.mocked(getAttendeeEvent)

const EVENT: AttendeeEventDetail = {
  id: 3,
  name: 'Partner Summit',
  description: 'A day of partner briefings.',
  event_type: 'conference',
  proposed_start: '2026-11-02T09:00:00Z',
  proposed_end: '2026-11-02T17:00:00Z',
  venues: [{ name: 'Garden Pavilion', location: '10 Bayfront Ave' }],
  accessibility_needs: 'Step-free access',
  programme: '09:00 Welcome\n10:00 Keynote',
  registration_open: true,
  registration_opens_at: '2026-10-01T00:00:00Z',
  registration_closes_at: '2026-10-30T00:00:00Z',
  my_status: null,
}

function renderView() {
  return render(
    <MemoryRouter initialEntries={['/attendee/events/3']}>
      <Routes>
        <Route path="/attendee/events/:id" element={<AttendeeEventView />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('Attendee event details', () => {
  it('AC1: shows name, description, category, date, venues, accessibility, programme and registration dates', async () => {
    mockGet.mockResolvedValue(EVENT)
    renderView()

    expect(await screen.findByRole('heading', { name: 'Partner Summit' })).toBeInTheDocument()
    expect(mockGet).toHaveBeenCalledWith(3)
    for (const label of ['Description', 'Category', 'Date and time', 'Venues', 'Accessibility', 'Programme', 'Registration opens', 'Registration closes']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
    expect(screen.getByText('A day of partner briefings.')).toBeInTheDocument()
    expect(screen.getByText('conference')).toBeInTheDocument()
    expect(screen.getByText('Garden Pavilion, 10 Bayfront Ave')).toBeInTheDocument()
    expect(screen.getByText('Step-free access')).toBeInTheDocument()
    expect(screen.getByText(/09:00 Welcome/)).toBeInTheDocument()
  })

  it('AC2: shows no internal planning sections', async () => {
    mockGet.mockResolvedValue(EVENT)
    renderView()
    await screen.findByRole('heading', { name: 'Partner Summit' })

    const text = document.body.textContent ?? ''
    for (const internal of ['Activity', 'Equipment', 'Safety', 'Coordinator', 'Booking', 'Hold', 'Notes']) {
      expect(text).not.toContain(internal)
    }
  })

  it('AC3: an event the server refuses shows its message and no details', async () => {
    mockGet.mockRejectedValue(new ApiError(404, 'Event not found'))
    renderView()

    expect(await screen.findByRole('alert')).toHaveTextContent('Event not found')
    expect(screen.queryByText('Description')).not.toBeInTheDocument()
  })

  it.each(['/coordinator/events/3', '/safety-checks/3', '/organiser/events/3', '/equipment-requirements/3'])(
    'AC3: opening internal planning page %s directly shows access denied',
    async (path) => {
      render(
        <MemoryRouter initialEntries={[path]}>
          <App />
        </MemoryRouter>,
      )
      expect(await screen.findByRole('heading', { name: 'No Access' })).toBeInTheDocument()
    },
  )

  it('AC4: shows the current venue the server returns', async () => {
    mockGet.mockResolvedValue({ ...EVENT, venues: [{ name: 'Replacement Hall', location: '1 New Rd' }] })
    renderView()

    expect(await screen.findByText('Replacement Hall, 1 New Rd')).toBeInTheDocument()
    expect(screen.queryByText(/Garden Pavilion/)).not.toBeInTheDocument()
  })
})
