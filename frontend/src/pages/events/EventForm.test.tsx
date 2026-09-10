/**
 * Component tests for the event request form.
 *
 * Traceability (see docs/test-cases-organiser-event-requests.md):
 *   TC-S1-1a, TC-S1-1b, TC-S1-2e, TC-S1-2f  -- Story 1 "Draft an Event Request"
 *   TC-S2-1c, TC-S2-1d                      -- Story 2 "Submit an Event Request"
 *
 * These assert what a user experiences (labels, aria-invalid, visible error
 * text), never CSS class names -- so restyling cannot turn them red.
 *
 * `lib/events` is mocked: this layer is about rendering and wiring. The real
 * request/response behaviour is covered by backend/tests/test_events.py.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/api'
import { EventForm } from './EventForm'

const navigate = vi.fn()
vi.mock('react-router', async () => {
  const actual = await vi.importActual<typeof import('react-router')>('react-router')
  return { ...actual, useNavigate: () => navigate }
})

vi.mock('../../lib/events', async () => {
  const actual = await vi.importActual<typeof import('../../lib/events')>('../../lib/events')
  return {
    ...actual, // keep the real date helpers
    createEvent: vi.fn(),
    updateEvent: vi.fn(),
    submitEvent: vi.fn(),
    getEvent: vi.fn(),
  }
})

import { createEvent, getEvent, submitEvent, updateEvent } from '../../lib/events'
import type { EventDetail } from '../../lib/events'

const mockCreate = vi.mocked(createEvent)
const mockUpdate = vi.mocked(updateEvent)
const mockSubmit = vi.mocked(submitEvent)
const mockGet = vi.mocked(getEvent)

/** Every field Story 1 AC1 says the form must capture. */
const AC1_LABELS = [
  'Event name',
  'Event type',
  'Purpose',
  'Description',
  'Preferred start',
  'Preferred end',
  'Expected attendees',
  'General programme',
  'Venue requirements',
  'Room layout preference',
  'Accessibility requirements',
  'Equipment requirements',
  'Other special arrangements',
]

function renderNew() {
  return render(
    <MemoryRouter initialEntries={['/organiser/events/new']}>
      <Routes>
        <Route path="/organiser/events/new" element={<EventForm />} />
      </Routes>
    </MemoryRouter>,
  )
}

function renderEdit(id = '7') {
  return render(
    <MemoryRouter initialEntries={[`/organiser/events/${id}/edit`]}>
      <Routes>
        <Route path="/organiser/events/:id/edit" element={<EventForm />} />
      </Routes>
    </MemoryRouter>,
  )
}

const SAVED: EventDetail = {
  id: 7,
  organiser_id: 5,
  coordinator_id: null,
  name: 'Regional Partner Conference',
  purpose: 'Annual partner briefing',
  event_type: 'conference',
  description: null,
  programme: '0900 keynote',
  proposed_start: null,
  proposed_end: null,
  expected_attendance: 120,
  venue_requirements: 'Main hall',
  room_layout_preference: 'theatre',
  accessibility_needs: null,
  equipment_requirements: null,
  special_arrangements: 'Halal catering',
  registration_enabled: true,
  status: 'draft',
  submitted_at: null,
  created_at: '2026-09-10T00:00:00Z',
  updated_at: '2026-09-10T00:00:00Z',
}

beforeEach(() => {
  vi.clearAllMocks()
  mockCreate.mockResolvedValue({ ...SAVED })
  mockUpdate.mockResolvedValue({ ...SAVED })
  mockSubmit.mockResolvedValue({ ...SAVED, status: 'submitted' })
  mockGet.mockResolvedValue({ ...SAVED })
})

describe('Story 1 AC1 - the form captures every required piece of information', () => {
  it('TC-S1-1a: renders an input for every field named in the acceptance criterion', () => {
    renderNew()
    for (const label of AC1_LABELS) {
      expect(screen.getByLabelText(label)).toBeInTheDocument()
    }
    // Registration is a checkbox rather than a text field.
    expect(
      screen.getByRole('checkbox', { name: /attendees must register/i }),
    ).toBeInTheDocument()
  })

  it('TC-S1-1b: sends what the organiser typed to the API', async () => {
    const user = userEvent.setup()
    renderNew()

    await user.type(screen.getByLabelText('Event name'), 'Robotics Summit')
    await user.type(screen.getByLabelText('Purpose'), 'Industry showcase')
    await user.type(screen.getByLabelText('Expected attendees'), '80')
    await user.click(screen.getByRole('checkbox', { name: /attendees must register/i }))
    await user.click(screen.getByRole('button', { name: 'Save as draft' }))

    await waitFor(() => expect(mockCreate).toHaveBeenCalledTimes(1))
    expect(mockCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'Robotics Summit',
        purpose: 'Industry showcase',
        expected_attendance: 80,
        registration_enabled: true,
      }),
    )
  })
})

describe('Story 1 AC2 - an incomplete request can be saved and resumed', () => {
  it('TC-S1-2f: no field is marked required, so an empty form can still be saved', async () => {
    const user = userEvent.setup()
    const { container } = renderNew()

    // The guard that keeps drafts possible. A `required` attribute added
    // here would silently break the whole draft story, because the browser
    // would block submission before any handler ran.
    expect(container.querySelectorAll('[required]')).toHaveLength(0)

    await user.click(screen.getByRole('button', { name: 'Save as draft' }))

    await waitFor(() => expect(mockCreate).toHaveBeenCalledTimes(1))
    // Untouched fields are sent as null, not empty strings.
    expect(mockCreate).toHaveBeenCalledWith(
      expect.objectContaining({ name: null, purpose: null, expected_attendance: null }),
    )
  })

  it('TC-S1-2e: reopening a draft repopulates every value previously entered', async () => {
    renderEdit()

    await waitFor(() => expect(mockGet).toHaveBeenCalledWith(7))
    expect(screen.getByLabelText('Event name')).toHaveValue('Regional Partner Conference')
    expect(screen.getByLabelText('Purpose')).toHaveValue('Annual partner briefing')
    expect(screen.getByLabelText('Event type')).toHaveValue('conference')
    expect(screen.getByLabelText('Expected attendees')).toHaveValue(120)
    expect(screen.getByLabelText('General programme')).toHaveValue('0900 keynote')
    expect(screen.getByLabelText('Room layout preference')).toHaveValue('theatre')
    expect(screen.getByLabelText('Other special arrangements')).toHaveValue('Halal catering')
    expect(screen.getByRole('checkbox', { name: /attendees must register/i })).toBeChecked()
  })

  it('edits an existing draft rather than creating a second one', async () => {
    const user = userEvent.setup()
    renderEdit()
    await waitFor(() => expect(mockGet).toHaveBeenCalled())

    await user.click(screen.getByRole('button', { name: 'Save as draft' }))

    await waitFor(() => expect(mockUpdate).toHaveBeenCalledTimes(1))
    expect(mockUpdate).toHaveBeenCalledWith(7, expect.any(Object))
    expect(mockCreate).not.toHaveBeenCalled()
  })
})

describe('Story 2 AC1 - submitting an incomplete request is blocked and the gaps are flagged', () => {
  it('TC-S2-1c: marks exactly the fields the server rejected', async () => {
    const user = userEvent.setup()
    mockSubmit.mockRejectedValueOnce(
      new ApiError(422, 'name: required; venue_requirements: required', [
        'name',
        'venue_requirements',
      ]),
    )
    renderNew()

    await user.click(screen.getByRole('button', { name: 'Submit request' }))

    await waitFor(() =>
      expect(screen.getByLabelText('Event name')).toHaveAttribute('aria-invalid', 'true'),
    )
    expect(screen.getByLabelText('Venue requirements')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getAllByText('Required before submitting.')).toHaveLength(2)

    // Fields the server did NOT complain about are left alone.
    expect(screen.getByLabelText('Purpose')).not.toHaveAttribute('aria-invalid', 'true')
    // Blocked means blocked -- no navigation away from the form.
    expect(navigate).not.toHaveBeenCalled()
  })

  it('TC-S2-1d: summarises how many fields are still incomplete', async () => {
    const user = userEvent.setup()
    mockSubmit.mockRejectedValueOnce(
      new ApiError(422, 'three problems', ['name', 'purpose', 'event_type']),
    )
    renderNew()

    await user.click(screen.getByRole('button', { name: 'Submit request' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('3 required fields are incomplete')
  })

  it('saves the current form before submitting, so validation sees what is on screen', async () => {
    const user = userEvent.setup()
    const order: string[] = []
    mockCreate.mockImplementation(async () => {
      order.push('save')
      return { ...SAVED }
    })
    mockSubmit.mockImplementation(async () => {
      order.push('submit')
      return { ...SAVED, status: 'submitted' as const }
    })
    renderNew()

    await user.type(screen.getByLabelText('Event name'), 'Late edit')
    await user.click(screen.getByRole('button', { name: 'Submit request' }))

    await waitFor(() => expect(order).toEqual(['save', 'submit']))
    // Submitted against the id returned by the save, not a stale one.
    expect(mockSubmit).toHaveBeenCalledWith(SAVED.id)
  })
})

describe('Story 2 AC2/AC3 - a completed request is submitted', () => {
  it('lands on the Submitted Requests tab once accepted', async () => {
    const user = userEvent.setup()
    renderNew()

    await user.click(screen.getByRole('button', { name: 'Submit request' }))

    await waitFor(() => expect(mockSubmit).toHaveBeenCalledTimes(1))
    expect(navigate).toHaveBeenCalledWith('/organiser/events?tab=submitted', { replace: true })
  })
})
