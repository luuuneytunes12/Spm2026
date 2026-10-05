/**
 * Component tests for the Coordinator's Registration card (SCRUM-66).
 *
 * Each test is named for the acceptance criterion it covers. Whether the API
 * accepts the dates and who may enable registration is the backend's job
 * (backend/tests/test_open_registration.py); these cover what the screen
 * offers, sends, and flags.
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
  return { ...actual, getAssignedEvent: vi.fn(), setEventRegistration: vi.fn() }
})

import { getAssignedEvent, setEventRegistration } from '../../lib/events'
import type { AssignedEventDetail } from '../../lib/events'

const mockGet = vi.mocked(getAssignedEvent)
const mockSet = vi.mocked(setEventRegistration)

const CONFIRMED: AssignedEventDetail = {
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
  status: 'confirmed',
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

async function fillDates(opens: string, closes: string) {
  const opensInput = await screen.findByLabelText('Registration opens')
  const closesInput = screen.getByLabelText('Registration closes')
  await userEvent.clear(opensInput)
  await userEvent.type(opensInput, opens)
  await userEvent.clear(closesInput)
  await userEvent.type(closesInput, closes)
}

beforeEach(() => {
  vi.clearAllMocks()
  mockGet.mockResolvedValue(CONFIRMED)
})

describe('Registration card', () => {
  it('AC1: enabling with an open and a close date sends them, then shows them on the event', async () => {
    mockSet.mockResolvedValue(CONFIRMED)
    renderView()

    await userEvent.click(await screen.findByLabelText('Enable registration'))
    await fillDates('2026-10-10T09:00', '2026-10-30T17:00')
    mockGet.mockResolvedValue({
      ...CONFIRMED,
      registration_enabled: true,
      registration_opens_at: '2026-10-10T01:00:00Z',
      registration_closes_at: '2026-10-30T09:00:00Z',
    })
    await userEvent.click(screen.getByRole('button', { name: 'Save registration settings' }))

    await waitFor(() => expect(mockSet).toHaveBeenCalledTimes(1))
    const [id, sent] = mockSet.mock.calls[0]
    expect(id).toBe(7)
    expect(sent.registration_enabled).toBe(true)
    expect(sent.registration_opens_at).toMatch(/^2026-10-10T/)
    expect(sent.registration_closes_at).toMatch(/^2026-10-30T/)

    expect(await screen.findByText('Registration settings saved.')).toBeInTheDocument()
    // Shown on the event record: a "Registration window" row in the details.
    expect(await screen.findByText('Registration window')).toBeInTheDocument()
  })

  it('AC2: when the server blocks close-before-open, both date fields are flagged and nothing is saved', async () => {
    mockSet.mockRejectedValue(
      new ApiError(
        422,
        'registration_opens_at: Registration cannot close before it opens.; registration_closes_at: Ensure the registration close date is later than the open date.',
        ['registration_opens_at', 'registration_closes_at'],
        [
          'Registration cannot close before it opens.',
          'Ensure the registration close date is later than the open date.',
        ],
      ),
    )
    renderView()

    await userEvent.click(await screen.findByLabelText('Enable registration'))
    await fillDates('2026-10-30T09:00', '2026-10-10T09:00')
    await userEvent.click(screen.getByRole('button', { name: 'Save registration settings' }))

    // Exactly the two sentences -- no column names like "registration_opens_at:".
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(
      'Registration cannot close before it opens. Ensure the registration close date is later than the open date.',
    )
    expect(alert).not.toHaveTextContent('registration_opens_at')
    expect(alert).not.toHaveTextContent('registration_closes_at')
    expect(screen.getByLabelText('Registration opens')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByLabelText('Registration closes')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.queryByText('Registration settings saved.')).not.toBeInTheDocument()
  })

  it('AC2: a missing date is flagged on that field only', async () => {
    mockSet.mockRejectedValue(
      new ApiError(422, 'Registration close date is required.', ['registration_closes_at']),
    )
    renderView()

    await userEvent.click(await screen.findByLabelText('Enable registration'))
    await userEvent.type(screen.getByLabelText('Registration opens'), '2026-10-10T09:00')
    await userEvent.click(screen.getByRole('button', { name: 'Save registration settings' }))

    await screen.findByRole('alert')
    expect(screen.getByLabelText('Registration closes')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByLabelText('Registration opens')).not.toHaveAttribute('aria-invalid')
  })

  it('AC3: an event that is not confirmed offers no way to enable registration', async () => {
    for (const status of ['submitted', 'under_review', 'approved', 'rejected'] as const) {
      mockGet.mockResolvedValue({ ...CONFIRMED, status })
      const view = renderView()

      await screen.findByText('Event Details')
      expect(screen.queryByLabelText('Enable registration')).not.toBeInTheDocument()
      expect(
        screen.queryByRole('button', { name: 'Save registration settings' }),
      ).not.toBeInTheDocument()
      view.unmount()
    }
  })

  it('AC3: if the server still refuses an unconfirmed event, the reason is shown', async () => {
    mockSet.mockRejectedValue(
      new ApiError(409, 'Registration can only be opened for a confirmed event.'),
    )
    renderView()

    await userEvent.click(await screen.findByLabelText('Enable registration'))
    await fillDates('2026-10-10T09:00', '2026-10-30T09:00')
    await userEvent.click(screen.getByRole('button', { name: 'Save registration settings' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('only be opened for a confirmed event')
  })

  it('reopens with the saved settings filled in', async () => {
    mockGet.mockResolvedValue({
      ...CONFIRMED,
      registration_enabled: true,
      registration_opens_at: '2026-10-10T01:00:00Z',
      registration_closes_at: '2026-10-30T09:00:00Z',
    })
    renderView()

    expect(await screen.findByLabelText('Enable registration')).toBeChecked()
    expect(screen.getByLabelText('Registration opens')).not.toHaveValue('')
    expect(screen.getByLabelText('Registration closes')).not.toHaveValue('')
  })
})
