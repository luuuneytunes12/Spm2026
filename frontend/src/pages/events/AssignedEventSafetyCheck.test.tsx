/**
 * Component tests for the Coordinator's "Submit for Safety Check" card (SCRUM-65).
 *
 * Each test is named for the acceptance criterion it covers. Whether the API
 * submits or refuses is the backend's job (backend/tests/test_submit_for_safety_check.py);
 * these cover what the screen offers, sends, lists and says.
 *
 *   AC1  an approved / planning event can be submitted, and moves on
 *   AC2  an event with no venue is told so
 *   AC3  a blocked submit lists every outstanding item with its status
 *   AC4  the card is only offered while the event is 'Event Approved' or 'Planning Event'
 *   AC6  the new status appears in the Activity Log with the Coordinator's name
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/api'
import { AssignedEventView } from './AssignedEventView'

vi.mock('../../components/VenueBookingSection', () => ({
  VenueBookingSection: () => <section aria-label="venue booking stub" />,
}))
vi.mock('../../components/EquipmentRequirementsSection', () => ({
  EquipmentRequirementsSection: () => <section aria-label="equipment requirements stub" />,
}))
vi.mock('../../lib/events', async () => {
  const actual = await vi.importActual<typeof import('../../lib/events')>('../../lib/events')
  return { ...actual, getAssignedEvent: vi.fn(), submitForSafetyCheck: vi.fn() }
})

import { getAssignedEvent, submitForSafetyCheck } from '../../lib/events'
import type { AssignedEventDetail } from '../../lib/events'

const mockGet = vi.mocked(getAssignedEvent)
const mockSubmit = vi.mocked(submitForSafetyCheck)

const APPROVED: AssignedEventDetail = {
  id: 7,
  organiser_id: 1,
  coordinator_id: 2,
  coordinator: { id: 2, name: 'Sam Tan', email: 'sam@connectsphere.test' },
  name: 'Regional Partner Conference',
  event_type: 'conference',
  purpose: 'Annual partner briefing',
  description: null,
  programme: null,
  proposed_start: '2026-11-02T09:00:00Z',
  proposed_end: '2026-11-02T17:00:00Z',
  expected_attendance: 120,
  venue_requirements: 'Main hall',
  room_layout_preference: null,
  accessibility_needs: 'Step-free access',
  equipment_requirements: null,
  equipment_items: [],
  special_arrangements: null,
  registration_enabled: false,
  registration_opens_at: null,
  registration_closes_at: null,
  status: 'event_approved',
  submitted_at: '2026-09-10T02:00:00Z',
  created_at: '2026-09-09T00:00:00Z',
  updated_at: '2026-09-10T02:00:00Z',
  organiser: { id: 1, name: 'Priya Menon', email: 'priya@connectsphere.test' },
  activity: [],
  change_requests: [],
  confirmation_outstanding: [],
}

function renderView() {
  return render(
    <MemoryRouter initialEntries={['/coordinator/events/7']}>
      <Routes>
        <Route path="/coordinator/events/:id" element={<AssignedEventView />} />
      </Routes>
    </MemoryRouter>,
  )
}

const submitButton = () => screen.findByRole('button', { name: 'Submit for Safety Check' })

beforeEach(() => {
  vi.clearAllMocks()
  mockGet.mockResolvedValue(APPROVED)
})

describe('Submit for Safety Check card', () => {
  it.each(['event_approved', 'planning_event'])('AC1: is offered while the event is %s', async (status) => {
    mockGet.mockResolvedValue({ ...APPROVED, status: status as AssignedEventDetail['status'] })
    renderView()
    expect(await submitButton()).toBeEnabled()
  })

  it('AC1: submitting asks the server, then shows the event as Awaiting Safety Check', async () => {
    mockSubmit.mockResolvedValue(APPROVED)
    renderView()
    const button = await submitButton()
    mockGet.mockResolvedValue({ ...APPROVED, status: 'awaiting_safety_check' }) // what the page reloads after submitting
    await userEvent.click(button)

    await waitFor(() => expect(mockSubmit).toHaveBeenCalledWith(7))
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Submit for Safety Check' })).not.toBeInTheDocument())
    expect(screen.getAllByText('Awaiting Safety Check').length).toBeGreaterThan(0)
  })

  it('AC2: an event with no venue is told so before anything is submitted', async () => {
    mockGet.mockResolvedValue({
      ...APPROVED,
      confirmation_outstanding: ['The event has no venue: no venue booking has been requested, or all were cancelled'],
    })
    renderView()
    expect(await screen.findByRole('status')).toHaveTextContent('The event has no venue')
  })

  it('AC3: lists every outstanding item, with its status, before anything is submitted', async () => {
    mockGet.mockResolvedValue({
      ...APPROVED,
      confirmation_outstanding: [
        "Venue booking 'Hall B' is not approved (status: pending)",
        "Equipment 'Projector' is not reserved (status: requested)",
      ],
    })
    renderView()
    const list = await screen.findByRole('status')
    expect(list).toHaveTextContent("Venue booking 'Hall B' is not approved (status: pending)")
    expect(list).toHaveTextContent("Equipment 'Projector' is not reserved (status: requested)")
  })

  it('AC3: a blocked submit shows the server\'s list and the event stays as it was', async () => {
    mockSubmit.mockRejectedValue(
      new ApiError(409, "Cannot submit yet. Outstanding: Venue booking 'Hall B' is not approved (status: pending)."),
    )
    renderView()
    await userEvent.click(await submitButton())

    expect(await screen.findByRole('alert')).toHaveTextContent("Hall B' is not approved (status: pending)")
    expect(screen.getByRole('button', { name: 'Submit for Safety Check' })).toBeEnabled()
  })

  it('AC3: nothing is listed as outstanding when the event is ready', async () => {
    renderView()
    await submitButton()
    expect(screen.queryByText('Still outstanding:')).not.toBeInTheDocument()
  })

  it.each(['under_review', 'awaiting_safety_check', 'safety_check_passed'])('AC4: is not offered while the event is %s', async (status) => {
    mockGet.mockResolvedValue({ ...APPROVED, status: status as AssignedEventDetail['status'] })
    renderView()
    await screen.findByRole('heading', { name: 'Event Details' })
    expect(screen.queryByRole('button', { name: 'Submit for Safety Check' })).not.toBeInTheDocument()
  })

  it('AC6: the Activity Log shows the change with the Coordinator\'s name and time', async () => {
    mockGet.mockResolvedValue({
      ...APPROVED,
      status: 'awaiting_safety_check',
      activity: [
        {
          from_status: 'event_approved',
          to_status: 'awaiting_safety_check',
          note: 'Submitted for safety check by the Event Coordinator.',
          changed_by_name: 'Sam Tan',
          created_at: '2026-10-03T04:00:00Z',
        },
      ],
    })
    renderView()
    expect(await screen.findByText(/Submitted for safety check by the Event Coordinator/)).toBeInTheDocument()
    expect(screen.getByText(/Sam Tan/)).toBeInTheDocument()
  })
})
