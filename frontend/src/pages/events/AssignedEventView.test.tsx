/**
 * Component tests for the Coordinator's assigned-event detail screen.
 *
 * Traceability (see docs/test-cases-coordinator-assigned-events.md):
 *   TC-S3-1b -- AC1 every requirement is on screen
 *   TC-S3-2b -- AC2 the Organiser's name and contact details
 *   TC-S3-3b -- AC3 the current status
 *   TC-S3-4b -- AC4 the activity log
 *   TC-S3-5b -- AC5 an event that is not assigned to me is not shown
 *
 * Whether the API *lets* a Coordinator read an event is the backend's job and
 * is covered by backend/tests/test_assigned_events.py. These tests cover what
 * the screen does with the answer, including the refusal.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/api'
import { AssignedEventView } from './AssignedEventView'

vi.mock('../../components/VenueBookingSection', () => ({
  VenueBookingSection: () => <section aria-label="venue booking stub" />,
}))
vi.mock('../../components/EventVenueSuitability', () => ({
  EventVenueSuitability: () => <section aria-label="event venue suitability stub" />,
}))
// The card has its own tests (EquipmentRequirementsSection.test.tsx). Here
// it only needs to show what the page hands it, so the stub echoes its props.
vi.mock('../../components/EquipmentRequirementsSection', () => ({
  EquipmentRequirementsSection: (props: {
    eventId: number
    eventStatus: string
    organiserLines: { equipment_name: string }[]
    organiserNotes: string | null
  }) => (
    <section
      aria-label="equipment requirements stub"
      data-event-id={props.eventId}
      data-event-status={props.eventStatus}
    >
      {props.organiserLines.map((line) => (
        <span key={line.equipment_name}>{line.equipment_name}</span>
      ))}
      {props.organiserNotes && <span>{`stub notes: ${props.organiserNotes}`}</span>}
    </section>
  ),
}))

vi.mock('../../lib/events', async () => {
  const actual = await vi.importActual<typeof import('../../lib/events')>('../../lib/events')
  return {
    ...actual,
    approveEvent: vi.fn(),
    approveEventChangeRequest: vi.fn(),
    cancelEvent: vi.fn(),
    completeEvent: vi.fn(),
    editPlanningEvent: vi.fn(),
    getAssignedEvent: vi.fn(),
    rejectEvent: vi.fn(),
    rejectEventChangeRequest: vi.fn(),
  }
})

import {
  approveEvent,
  approveEventChangeRequest,
  cancelEvent,
  completeEvent,
  editPlanningEvent,
  getAssignedEvent,
  rejectEvent,
  rejectEventChangeRequest,
} from '../../lib/events'
import type { AssignedEventDetail, EventChangeRequest } from '../../lib/events'

const mockGet = vi.mocked(getAssignedEvent)
const mockApprove = vi.mocked(approveEvent)
const mockReject = vi.mocked(rejectEvent)
const mockCancel = vi.mocked(cancelEvent)
const mockComplete = vi.mocked(completeEvent)
const mockEditPlanning = vi.mocked(editPlanningEvent)
const mockApproveChangeRequest = vi.mocked(approveEventChangeRequest)
const mockRejectChangeRequest = vi.mocked(rejectEventChangeRequest)

const EVENT: AssignedEventDetail = {
  id: 7,
  organiser_id: 1,
  coordinator_id: 2,
  coordinator: { id: 2, name: 'Sam Tan', email: 'sam@connectsphere.test' },
  event_contact_name: null,
  event_contact_email: null,
  name: 'Regional Partner Conference',
  event_type: 'conference',
  purpose: 'Annual partner briefing',
  description: 'A full-day briefing for our regional partners.',
  programme: '0900 registration, 0930 keynote',
  proposed_start: '2026-11-02T09:00:00Z',
  proposed_end: '2026-11-02T17:00:00Z',
  expected_attendance: 120,
  venue_requirements: 'Main hall, stage, podium',
  room_layout_preference: 'theatre',
  accessibility_needs: 'Step-free access, hearing loop',
  equipment_requirements: '2 projectors, 4 radio mics',
  equipment_items: [],
  special_arrangements: 'Halal catering',
  registration_enabled: true,
  status: 'submitted_awaiting_coordinator',
  submitted_at: '2026-09-10T02:00:00Z',
  created_at: '2026-09-09T00:00:00Z',
  updated_at: '2026-09-10T02:00:00Z',
  organiser: { id: 1, name: 'Priya Menon', email: 'priya@connectsphere.test' },
  activity: [
    {
      from_status: 'draft',
      to_status: 'submitted_awaiting_coordinator',
      note: 'Submitted by organiser.',
      changed_by_name: 'Priya Menon',
      created_at: '2026-09-10T02:00:00Z',
    },
  ],
  change_requests: [],
}

function renderView(id = '7') {
  return render(
    <MemoryRouter initialEntries={[`/coordinator/events/${id}`]}>
      <Routes>
        <Route path="/coordinator/events/:id" element={<AssignedEventView />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockGet.mockResolvedValue(EVENT)
  mockApproveChangeRequest.mockResolvedValue({
    id: 11,
    event_id: 7,
    requested_by: 1,
    description: 'Increase attendance',
    proposed_changes: { expected_attendance: 150 },
    status: 'approved',
    review_notes: null,
    created_at: '2026-09-10T02:00:00Z',
    reviewed_at: '2026-09-10T03:00:00Z',
    important_change: true,
    safety_check_required: false,
    venue_bookings_to_reconsider: [],
    equipment_reservations_to_reconsider: [],
    equipment_requirements_to_reconsider: [],
  })
  mockRejectChangeRequest.mockResolvedValue({
    id: 11,
    event_id: 7,
    requested_by: 1,
    description: 'Increase attendance',
    proposed_changes: { expected_attendance: 150 },
    status: 'rejected',
    review_notes: 'Capacity is too low.',
    created_at: '2026-09-10T02:00:00Z',
    reviewed_at: '2026-09-10T03:00:00Z',
    important_change: true,
    safety_check_required: false,
    venue_bookings_to_reconsider: [],
    equipment_reservations_to_reconsider: [],
    equipment_requirements_to_reconsider: [],
  })
})

describe('AC1 - the full requirements are visible', () => {
  it('shows the event-wide venue assessment once venue planning is available', async () => {
    mockGet.mockResolvedValue({ ...EVENT, status: 'planning_event' })
    renderView()

    expect(await screen.findByLabelText('event venue suitability stub')).toBeInTheDocument()
  })

  describe('planning event edits', () => {
    it('saves changed details and reports arrangements that need review', async () => {
      const planningEvent = { ...EVENT, status: 'planning_event' as const }
      mockGet.mockResolvedValue(planningEvent)
      mockEditPlanning.mockResolvedValue({
        ...planningEvent,
        name: 'Updated partner conference',
        affected_venue_bookings: ['Main Hall'],
        affected_equipment_requirements: ['Projector'],
      })
      const user = userEvent.setup()
      renderView()

      const name = await screen.findByLabelText('Event name')
      await user.clear(name)
      await user.type(name, 'Updated partner conference')
      await user.click(screen.getByRole('button', { name: 'Save event details' }))

      expect(await screen.findByText('Event details saved.')).toBeInTheDocument()
      expect(mockEditPlanning).toHaveBeenCalledWith(
        7,
        expect.objectContaining({
          name: 'Updated partner conference',
          event_contact_name: null,
          event_contact_email: null,
        }),
      )
      expect(screen.getByText('Venue bookings: Main Hall')).toBeInTheDocument()
      expect(screen.getByText('Equipment requirements: Projector')).toBeInTheDocument()
    })

    it.each(['event_approved', 'planning_event', 'awaiting_safety_check', 'safety_check_passed'] as const)(
      'US2 AC1/AC4: offers the edit form for a %s Event',
      async (status) => {
        mockGet.mockResolvedValue({ ...EVENT, status })
        renderView()

        expect(await screen.findByRole('heading', { name: 'Edit event details' })).toBeInTheDocument()
        expect(screen.getByRole('button', { name: 'Save event details' })).toBeInTheDocument()
      },
    )

    it.each(['under_review', 'event_cancelled', 'event_completed', 'event_rejected'] as const)(
      'US2 AC5: offers no edit form for a %s Event',
      async (status) => {
        mockGet.mockResolvedValue({ ...EVENT, status })
        renderView()
        await screen.findByRole('heading', { name: 'Regional Partner Conference' })

        expect(screen.queryByRole('heading', { name: 'Edit event details' })).toBeNull()
        expect(screen.queryByRole('button', { name: 'Save event details' })).toBeNull()
      },
    )

    it('US2 AC3: shows the server refusal and does not claim the details were saved', async () => {
      mockGet.mockResolvedValue({ ...EVENT, status: 'planning_event' })
      mockEditPlanning.mockRejectedValue(
        new ApiError(422, 'Event name cannot be empty.'),
      )
      const user = userEvent.setup()
      renderView()

      await user.clear(await screen.findByLabelText('Event name'))
      await user.click(screen.getByRole('button', { name: 'Save event details' }))

      expect(await screen.findByText('Event name cannot be empty.')).toHaveAttribute('role', 'alert')
      expect(screen.queryByText('Event details saved.')).toBeNull()
    })

    it('US2: a network failure shows a readable message, not a crash', async () => {
      mockGet.mockResolvedValue({ ...EVENT, status: 'planning_event' })
      mockEditPlanning.mockRejectedValue(new TypeError('Failed to fetch'))
      const user = userEvent.setup()
      renderView()

      await user.click(await screen.findByRole('button', { name: 'Save event details' }))

      expect(await screen.findByText('Could not save event details.')).toHaveAttribute('role', 'alert')
    })
  })

  it('TC-S3-1b: shows every field named in the acceptance criterion', async () => {
    renderView()

    expect(
      await screen.findByRole('heading', { name: 'Regional Partner Conference' }),
    ).toBeInTheDocument()

    // Asserting value-under-label, not just "the text is somewhere on the
    // page": a Coordinator reading "120" needs to know it is the attendance.
    for (const [label, value] of [
      ['Purpose', 'Annual partner briefing'],
      ['Description', 'A full-day briefing for our regional partners.'],
      ['Expected attendance', '120'],
      ['Venue requirements', 'Main hall, stage, podium'],
      ['Accessibility needs', 'Step-free access, hearing loop'],
      ['Other equipment notes', '2 projectors, 4 radio mics'],
      ['Registration needs', 'Attendees must register'],
    ]) {
      expect(screen.getByText(label).parentElement).toHaveTextContent(value)
    }

    // Matched on the year only: the date is formatted in the *viewer's*
    // locale, so asserting "2 Nov 2026" would pass in en-GB and fail in
    // en-US ("Nov 2, 2026") -- a green or red test decided by the runner's
    // locale rather than by the code.
    expect(screen.getByText('Date and time').parentElement).toHaveTextContent(/2026/)
  })

  it('marks a field the Organiser left empty rather than rendering a blank row', async () => {
    mockGet.mockResolvedValue({ ...EVENT, description: null, accessibility_needs: null })
    renderView()

    await screen.findByText('Description')
    expect(screen.getAllByText('Not provided')).toHaveLength(4)
  })

  it('says so plainly when registration is not required', async () => {
    mockGet.mockResolvedValue({ ...EVENT, registration_enabled: false })
    renderView()

    expect(await screen.findByText('Registration not required')).toBeInTheDocument()
  })

  it('renders a note the Organiser wrote one item per line as a bulleted list', async () => {
    mockGet.mockResolvedValue({
      ...EVENT,
      equipment_requirements: 'Two projectors\nFour radio microphones\nA live-stream setup',
    })
    renderView()

    const label = await screen.findByText('Other equipment notes')
    const list = label.parentElement!.querySelector('ul.detail-value-list')
    expect(list).not.toBeNull()
    expect(within(list as HTMLElement).getAllByRole('listitem').map((li) => li.textContent)).toEqual([
      'Two projectors',
      'Four radio microphones',
      'A live-stream setup',
    ])
  })

  it('lists the equipment the Organiser picked, with quantities', async () => {
    mockGet.mockResolvedValue({
      ...EVENT,
      equipment_items: [
        {
          id: 1,
          equipment_id: 11,
          equipment_name: 'Shure BLX24 Handheld Microphone',
          equipment_category: 'Audio',
          quantity_requested: 6,
          technical_requirements: null,
          status: 'requested',
        },
        {
          id: 2,
          equipment_id: 12,
          equipment_name: 'Epson EB-L200SW Projector',
          equipment_category: 'Projection',
          quantity_requested: 2,
          technical_requirements: null,
          status: 'requested',
        },
      ],
    })
    renderView()

    const row = (await screen.findByText('Equipment requirements')).parentElement!
    expect(row).toHaveTextContent('Shure BLX24 Handheld Microphone')
    expect(row).toHaveTextContent('Audio')
    expect(row).toHaveTextContent('6')
    expect(row).toHaveTextContent('Epson EB-L200SW Projector')
  })

  it('says so plainly when no equipment was requested', async () => {
    renderView()

    const row = (await screen.findByText('Equipment requirements')).parentElement!
    expect(row).toHaveTextContent('No equipment requested.')
  })

  it('leaves a single-line field as plain text -- not every field is a list', async () => {
    renderView()

    // The mock's Purpose is one sentence with no newlines: it must stay a
    // sentence, not turn into a one-item bullet.
    const label = await screen.findByText('Purpose')
    expect(label.parentElement!.querySelector('ul.detail-value-list')).toBeNull()
    expect(label.parentElement).toHaveTextContent('Annual partner briefing')
  })

  it('drops blank lines rather than rendering empty bullets', async () => {
    mockGet.mockResolvedValue({
      ...EVENT,
      special_arrangements: 'Halal catering\n\nInterpreter booth\n',
    })
    renderView()

    const label = await screen.findByText('Special arrangements')
    const items = within(label.parentElement!.querySelector('ul') as HTMLElement).getAllByRole(
      'listitem',
    )
    expect(items.map((li) => li.textContent)).toEqual(['Halal catering', 'Interpreter booth'])
  })
})

describe('change requests - coordinator review and planning impact', () => {
  it('shows an important proposal and existing commitments, then offers a decision', async () => {
    mockGet.mockResolvedValue({
      ...EVENT,
      status: 'under_review',
      change_requests: [
        {
          id: 11,
          event_id: 7,
          requested_by: 1,
          description: 'Increase expected attendance',
          proposed_changes: { expected_attendance: 180 },
          status: 'pending',
          review_notes: null,
          created_at: '2026-09-10T02:00:00Z',
          reviewed_at: null,
          important_change: true,
          safety_check_required: true,
          venue_bookings_to_reconsider: [
            {
              id: 1,
              venue_name: 'Main Hall',
              start_time: '2026-11-02T09:00:00Z',
              end_time: '2026-11-02T17:00:00Z',
              status: 'approved',
              suitable: false,
              unmet_requirements: ['Insufficient capacity.'],
              conflicts: ['Conflicts with another booking.'],
            },
          ],
          equipment_reservations_to_reconsider: [
            { id: 2, equipment_name: 'Projector', quantity_requested: 2, status: 'reserved' },
          ],
          equipment_requirements_to_reconsider: [
            {
              id: 3,
              category: 'Projection',
              status: 'reserved',
              quantity_needed: 2,
              reserved_items: ['Projector × 2'],
            },
          ],
        },
      ],
    })
    renderView()

    expect(await screen.findByText('Important change')).toBeInTheDocument()
    expect(screen.getByText(/returns this Event to Planning Event/)).toBeInTheDocument()
    expect(screen.getByText(/Main Hall/)).toBeInTheDocument()
    expect(screen.getByText(/Not Suitable/)).toBeInTheDocument()
    expect(screen.getByText('Insufficient capacity.')).toBeInTheDocument()
    expect(screen.getByText('Conflicts with another booking.')).toBeInTheDocument()
    expect(screen.getByText(/Requirement #3: Projection/)).toBeInTheDocument()
    expect(screen.getAllByText(/Projector/).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: 'Approve changes' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Approve request' })).toBeDisabled()
  })

  it('lists proposed equipment by name and quantity instead of raw JSON', async () => {
    mockGet.mockResolvedValue({
      ...EVENT,
      change_requests: [
        {
          id: 12,
          event_id: 7,
          requested_by: 1,
          description: 'Add a projector',
          proposed_changes: {
            equipment_items: [
              {
                equipment_id: 11,
                equipment_name: 'Epson Projector',
                quantity_requested: 2,
                technical_requirements: null,
              },
            ],
          },
          status: 'pending',
          review_notes: null,
          created_at: '2026-09-10T02:00:00Z',
          reviewed_at: null,
          important_change: true,
          safety_check_required: false,
          venue_bookings_to_reconsider: [],
          equipment_reservations_to_reconsider: [],
          equipment_requirements_to_reconsider: [],
        },
      ],
    })
    renderView()

    expect(await screen.findByText('Epson Projector × 2')).toBeInTheDocument()
    expect(screen.queryByText(/\{"equipment_id"/)).not.toBeInTheDocument()
    expect(screen.getByText('Add a projector')).toBeInTheDocument()
  })
})

describe("AC2 - the Event Organiser's name and contact details", () => {
  it('TC-S3-2b: names the Organiser and links their email', async () => {
    renderView()

    expect(await screen.findByRole('heading', { name: 'Event Organiser' })).toBeInTheDocument()
    expect(screen.getByText('Priya Menon')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'priya@connectsphere.test' })).toHaveAttribute(
      'href',
      'mailto:priya@connectsphere.test',
    )
  })
})

describe('AC3 - the current status', () => {
  it('TC-S3-3b: shows the status under a readable label, not the stored slug', async () => {
    mockGet.mockResolvedValue({ ...EVENT, status: 'under_review' })
    renderView()

    // Appears twice once loaded -- the header badge and the timeline's
    // current step both show it -- so any match at all proves the label
    // rendered; the second assertion is what proves the raw slug did not.
    await waitFor(() => expect(screen.getAllByText('Under Review').length).toBeGreaterThan(0))
    expect(screen.queryByText('under_review')).toBeNull()
  })

  it('TC-S3-3c: explains what the current status means, not just names it', async () => {
    renderView()

    // "Submitted" alone does not say what happens next -- the description
    // does, and it is this specific one for exactly this status.
    expect(
      await screen.findByText(
        'Submitted by the Organiser and waiting for a Coordinator to begin reviewing it.',
      ),
    ).toBeInTheDocument()
  })

  it('TC-S3-3d: shows the full lifecycle with the current stage marked', async () => {
    renderView()

    // Scoped to the timeline's own label class: "Submitted" also appears in
    // the header badge, so an unscoped match would be ambiguous.
    const steps = [
      'Submitted – Awaiting Coordinator',
      'Under Review',
      'Event Approved',
      'Planning Event',
      'Awaiting Safety Check',
      'Safety Check Passed (Event Confirmed)',
      'Event Completed',
    ]
    for (const label of steps) {
      expect(await screen.findByText(label, { selector: '.status-step-label' })).toBeInTheDocument()
    }
    // Exactly one stage is "current" -- the event's actual status.
    const current = screen
      .getByText('Submitted – Awaiting Coordinator', { selector: '.status-step-label' })
      .closest('[aria-current="step"]')
    expect(current).not.toBeNull()
    expect(
      screen.getAllByRole('listitem').filter((li) => li.getAttribute('aria-current') === 'step'),
    ).toHaveLength(1)
  })

  it("does not show Draft on the timeline -- a Coordinator's process only begins at Submitted", async () => {
    renderView()

    await screen.findByText('Submitted – Awaiting Coordinator', { selector: '.status-step-label' })
    expect(screen.queryByText('Draft', { selector: '.status-step-label' })).toBeNull()
  })

  it('handles a still-Draft assigned event without marking any stage reached', async () => {
    // Not a state the real flow produces yet (there is no "assign a
    // Coordinator" endpoint), but the API shape allows it, and a Draft
    // genuinely has not entered the Coordinator's pipeline -- nothing
    // should read as done or current.
    mockGet.mockResolvedValue({ ...EVENT, status: 'draft', submitted_at: null, activity: [] })
    renderView()

    await screen.findByText(
      'The Organiser is still filling this request in. It has not been submitted yet.',
    )
    expect(
      screen.queryAllByRole('listitem').some((li) => li.getAttribute('aria-current') === 'step'),
    ).toBe(false)
  })

  it('TC-S3-3e: a branch status (changes requested) is drawn off the stage it departed from, not as its own fixed step', async () => {
    mockGet.mockResolvedValue({
      ...EVENT,
      status: 'awaiting_organiser_reply',
      activity: [
        {
          from_status: 'under_review',
          to_status: 'awaiting_organiser_reply',
          note: 'Please confirm the accessibility plan.',
          changed_by_name: 'Sam Tan',
          created_at: '2026-09-12T09:00:00Z',
        },
        ...EVENT.activity,
      ],
    })
    renderView()

    // "Under review" and "Changes requested" each appear twice on this page
    // -- once as a timeline node, once in the activity log's own wording --
    // so the timeline's copy is picked out by its label class.
    await screen.findByText('Awaiting Organiser Reply', { selector: '.status-step-label' })
    const reviewStep = screen
      .getByText('Under Review', { selector: '.status-step-label' })
      .closest('.status-step')
    expect(reviewStep).toHaveClass('status-step-done')
    const approvedStep = screen.getByText('Event Approved').closest('.status-step')
    expect(approvedStep).toHaveClass('status-step-upcoming')
    const branchStep = screen
      .getByText('Awaiting Organiser Reply', { selector: '.status-step-label' })
      .closest('.status-step')
    expect(branchStep).toHaveClass('status-step-branch', 'status-step-branch-warning')
  })

  it('TC-S3-3f: a rejection is shown in a danger tone', async () => {
    mockGet.mockResolvedValue({
      ...EVENT,
      status: 'event_rejected',
      activity: [
        {
          from_status: 'under_review',
          to_status: 'event_rejected',
          note: null,
          changed_by_name: 'Sam Tan',
          created_at: '2026-09-12T09:00:00Z',
        },
      ],
    })
    renderView()

    const branchStep = await screen.findByText('Event Rejected', { selector: '.status-step-label' })
    expect(branchStep.closest('.status-step')).toHaveClass('status-step-branch-danger')
  })
})

describe('AC4 - the activity log', () => {
  it('TC-S3-4b: shows each change, who made it, and any note', async () => {
    renderView()

    const log = await screen.findByRole('list', { name: 'Activity log' })
    const [entry] = within(log).getAllByRole('listitem')
    // "Draft -> Submitted", rendered as labels rather than stored slugs.
    expect(entry).toHaveTextContent('Draft')
    expect(entry).toHaveTextContent('Submitted')
    expect(entry).not.toHaveTextContent('draft')
    expect(entry).toHaveTextContent('Priya Menon')
    expect(entry).toHaveTextContent('Submitted by organiser.')
  })

  it('lists the most recent change first', async () => {
    mockGet.mockResolvedValue({
      ...EVENT,
      status: 'under_review',
      activity: [
        {
          from_status: 'submitted_awaiting_coordinator',
          to_status: 'under_review',
          note: 'Picked up for review.',
          changed_by_name: 'Sam Tan',
          created_at: '2026-09-11T09:00:00Z',
        },
        ...EVENT.activity,
      ],
    })
    renderView()

    const log = await screen.findByRole('list', { name: 'Activity log' })
    const entries = within(log).getAllByRole('listitem')
    expect(entries[0]).toHaveTextContent('Picked up for review.')
    expect(entries[1]).toHaveTextContent('Submitted by organiser.')
  })

  it('shows an empty state rather than an empty box for an untouched event', async () => {
    mockGet.mockResolvedValue({ ...EVENT, status: 'draft', submitted_at: null, activity: [] })
    renderView()

    expect(await screen.findByText('No activity recorded yet.')).toBeInTheDocument()
  })

  it('renders a log entry whose actor can no longer be named', async () => {
    mockGet.mockResolvedValue({
      ...EVENT,
      activity: [{ ...EVENT.activity[0], changed_by_name: null }],
    })
    renderView()

    expect(await screen.findByText(/Unknown user ·/)).toBeInTheDocument()
  })

  it('renders an assignment as "Assignment", not a status change into itself', async () => {
    mockGet.mockResolvedValue({
      ...EVENT,
      status: 'under_review',
      activity: [
        {
          from_status: 'under_review',
          to_status: 'under_review',
          note: 'Reassigned from Alex Chen to Sam Tan.',
          changed_by_name: 'Lena Lead',
          created_at: '2026-09-10T02:05:00Z',
        },
        ...EVENT.activity,
      ],
    })
    renderView()

    const log = await screen.findByRole('list', { name: 'Activity log' })
    const [entry] = within(log).getAllByRole('listitem')
    expect(entry).toHaveTextContent('Assignment')
    expect(entry).toHaveTextContent('Reassigned from Alex Chen to Sam Tan.')
    // Not rendered as "Under Review -> Under Review".
    expect(within(entry).queryByText('→')).toBeNull()
  })

  it('renders an organiser correction as a request update, not an assignment', async () => {
    mockGet.mockResolvedValue({
      ...EVENT,
      status: 'under_review',
      activity: [
        {
          from_status: 'under_review',
          to_status: 'under_review',
          note: 'Updated by the Organiser before review was decided.',
          changed_by_name: 'Priya Menon',
          created_at: '2026-09-11T09:00:00Z',
        },
        ...EVENT.activity,
      ],
    })
    renderView()

    const log = await screen.findByRole('list', { name: 'Activity log' })
    const [entry] = within(log).getAllByRole('listitem')
    expect(entry).toHaveTextContent('Request update')
    expect(entry).not.toHaveTextContent('Assignment')
    expect(within(entry).queryByText('→')).toBeNull()
  })
})

describe('AC5 - events that are not assigned to me', () => {
  it('shows the server\'s reassignment message when the Lead moved the event away', async () => {
    const msg =
      "'Robotics Summit' that was initially assigned to you by the Event Coordinator Lead has been reassigned to Priya Nair."
    mockGet.mockRejectedValue(new ApiError(409, msg))
    renderView('99')

    expect(await screen.findByRole('alert')).toHaveTextContent(msg)
    expect(screen.getByRole('link', { name: /back to my assigned events/i })).toBeInTheDocument()
  })

  it('TC-S3-5b: a 404 becomes a refusal, and none of the event is rendered', async () => {
    mockGet.mockRejectedValue(new ApiError(404, 'Event not found'))
    renderView('99')

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'That event is not assigned to you.',
    )
    expect(screen.queryByText('Regional Partner Conference')).toBeNull()
    expect(screen.queryByText('Priya Menon')).toBeNull()
    expect(screen.getByRole('link', { name: /back to my assigned events/i })).toBeInTheDocument()
  })

  it('distinguishes a server problem from a refusal', async () => {
    mockGet.mockRejectedValue(new Error('network down'))
    renderView()

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load this event.')
  })
})

describe('what this screen deliberately does not offer', () => {
  it('has no way to edit the event\'s fields -- releasing it is not editing it', async () => {
    renderView()
    await screen.findByRole('heading', { name: 'Regional Partner Conference' })

    await waitFor(() => expect(mockGet).toHaveBeenCalledWith(7))
    expect(screen.queryByRole('link', { name: /edit/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /save|update/i })).toBeNull()
  })
})

describe('US3 AC2 - arrangements the change does not touch', () => {
  const pendingRequest: EventChangeRequest = {
    id: 21,
    event_id: 7,
    requested_by: 1,
    description: 'More attendees',
    proposed_changes: { expected_attendance: 180 },
    status: 'pending',
    review_notes: null,
    created_at: '2026-09-10T02:00:00Z',
    reviewed_at: null,
    important_change: true,
    safety_check_required: true,
    venue_bookings_to_reconsider: [],
    equipment_reservations_to_reconsider: [],
    equipment_requirements_to_reconsider: [],
    other_venue_bookings: [
      {
        id: 5,
        venue_name: 'Annex',
        start_time: '2026-11-02T09:00:00Z',
        end_time: '2026-11-02T17:00:00Z',
        status: 'approved',
      },
    ],
    other_equipment_reservations: [
      { id: 6, equipment_name: 'Projector', quantity_requested: 2, status: 'reserved' },
    ],
  }

  it('lists them as unticked choices, so by default they stay unchanged', async () => {
    mockGet.mockResolvedValue({ ...EVENT, status: 'planning_event', change_requests: [pendingRequest] })
    const user = userEvent.setup()
    renderView()

    const annex = await screen.findByRole('checkbox', { name: /Venue Booking #5 — Annex/ })
    const projector = screen.getByRole('checkbox', { name: /Equipment reservation #6 — Projector × 2/ })
    expect(annex).not.toBeChecked()
    expect(projector).not.toBeChecked()

    await user.click(screen.getByRole('button', { name: 'Approve changes' }))

    await waitFor(() => expect(mockApproveChangeRequest).toHaveBeenCalledWith(21, undefined))
  })

  it('sends only the ones the Coordinator ticks', async () => {
    mockGet.mockResolvedValue({ ...EVENT, status: 'planning_event', change_requests: [pendingRequest] })
    const user = userEvent.setup()
    renderView()

    await user.click(await screen.findByRole('checkbox', { name: /Venue Booking #5/ }))
    await user.click(screen.getByRole('checkbox', { name: /Equipment reservation #6/ }))
    await user.click(screen.getByRole('checkbox', { name: /Equipment reservation #6/ }))
    await user.click(screen.getByRole('button', { name: 'Approve changes' }))

    await waitFor(() =>
      expect(mockApproveChangeRequest).toHaveBeenCalledWith(21, undefined, {
        venueBookingIds: [5],
        equipmentReservationIds: [],
      }),
    )
  })

  it('does not offer the choice once the request has been decided', async () => {
    mockGet.mockResolvedValue({
      ...EVENT,
      status: 'planning_event',
      change_requests: [{ ...pendingRequest, status: 'approved' }],
    })
    renderView()
    await screen.findByText('More attendees')

    expect(screen.queryByRole('checkbox', { name: /Venue Booking #5/ })).toBeNull()
  })

  it('shows a readable refusal from the server', async () => {
    mockGet.mockResolvedValue({ ...EVENT, status: 'planning_event', change_requests: [pendingRequest] })
    mockApproveChangeRequest.mockRejectedValueOnce(
      new ApiError(
        422,
        'reopen_venue_booking_ids: Venue Booking #5 is not an active booking on this Event, so it cannot be reopened for review.',
      ),
    )
    const user = userEvent.setup()
    renderView()

    await user.click(await screen.findByRole('checkbox', { name: /Venue Booking #5/ }))
    await user.click(screen.getByRole('button', { name: 'Approve changes' }))

    expect(
      await screen.findByText(/Venue Booking #5 is not an active booking on this Event/),
    ).toHaveAttribute('role', 'alert')
  })
})

describe('Coordinator decisions', () => {
  it('approves the assigned request and refreshes its activity', async () => {
    mockGet.mockResolvedValue({ ...EVENT, status: 'under_review' })
    const approved = { ...EVENT, status: 'event_approved' as const }
    mockApprove.mockResolvedValue(approved)
    mockGet.mockResolvedValueOnce({ ...EVENT, status: 'under_review' }).mockResolvedValueOnce({
      ...approved,
      activity: [
        {
          from_status: 'under_review',
          to_status: 'event_approved',
          note: 'Approved by the Event Coordinator.',
          changed_by_name: 'Sam Tan',
          created_at: '2026-09-12T09:00:00Z',
        },
        ...EVENT.activity,
      ],
    })
    renderView()

    await userEvent.click(await screen.findByRole('button', { name: 'Approve request' }))

    await waitFor(() => expect(mockApprove).toHaveBeenCalledWith(7))
    expect(await screen.findByText('Event Approved', { selector: '.badge' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Approve request' })).not.toBeInTheDocument()
    expect(screen.getByText('Approved by the Event Coordinator.')).toBeInTheDocument()
  })

  it('requires a reason before rejecting and submits the recorded reason', async () => {
    mockGet.mockResolvedValue({ ...EVENT, status: 'under_review' })
    mockReject.mockResolvedValue({ ...EVENT, status: 'event_rejected' })
    renderView()

    const reject = await screen.findByRole('button', { name: 'Reject request' })
    expect(reject).toBeDisabled()
    await userEvent.type(screen.getByRole('textbox', { name: 'Rejection reason' }), 'Venue unavailable')
    expect(reject).toBeEnabled()
    await userEvent.click(reject)

    await waitFor(() => expect(mockReject).toHaveBeenCalledWith(7, 'Venue unavailable'))
  })

  it('does not offer decision controls once the request has been decided', async () => {
    mockGet.mockResolvedValue({ ...EVENT, status: 'event_approved' })
    renderView()

    await screen.findByRole('heading', { name: 'Regional Partner Conference' })
    expect(screen.queryByRole('button', { name: 'Approve request' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reject request' })).not.toBeInTheDocument()
  })

  it('does not offer approval or rejection while the event awaits coordinator assignment', async () => {
    mockGet.mockResolvedValue({ ...EVENT, status: 'submitted_awaiting_coordinator' })
    renderView()

    await screen.findByRole('heading', { name: 'Regional Partner Conference' })
    expect(screen.queryByRole('button', { name: 'Approve request' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reject request' })).not.toBeInTheDocument()
  })
})

describe('Cancel Event', () => {
  it('requires a reason and refreshes the event activity after cancelling', async () => {
    const user = userEvent.setup()
    mockGet
      .mockResolvedValueOnce({ ...EVENT, status: 'planning_event' })
      .mockResolvedValueOnce({
        ...EVENT,
        status: 'event_cancelled',
        activity: [
          {
            from_status: 'planning_event',
            to_status: 'event_cancelled',
            note: 'Venue unavailable.',
            changed_by_name: 'Sam Tan',
            created_at: '2026-09-10T03:00:00Z',
          },
          ...EVENT.activity,
        ],
      })
    mockCancel.mockResolvedValue({ ...EVENT, status: 'event_cancelled' })
    renderView()

    const reason = await screen.findByLabelText('Cancellation reason')
    const button = screen.getByRole('button', { name: 'Cancel event' })
    expect(button).toBeDisabled()

    await user.type(reason, 'Venue unavailable.')
    await user.click(button)

    expect(mockCancel).toHaveBeenCalledWith(7, 'Venue unavailable.')
    expect(await screen.findByText('Event Cancelled', { selector: '.badge' })).toBeInTheDocument()
    expect(screen.getByText(/Sam Tan/)).toBeInTheDocument()
    expect(screen.getByText('Venue unavailable.')).toBeInTheDocument()
    expect(screen.queryByLabelText('Cancellation reason')).toBeNull()
  })

  it('shows a useful error when the cancellation is refused', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ ...EVENT, status: 'under_review' })
    mockCancel.mockRejectedValue(new ApiError(409, 'This event can no longer be cancelled.'))
    renderView()

    await user.type(await screen.findByLabelText('Cancellation reason'), 'No longer proceeding.')
    await user.click(screen.getByRole('button', { name: 'Cancel event' }))

    expect(await screen.findByText('This event can no longer be cancelled.')).toBeInTheDocument()
  })

  it.each(['event_completed', 'event_rejected', 'event_cancelled'] as const)(
    'does not offer cancellation for %s',
    async (status) => {
      mockGet.mockResolvedValue({ ...EVENT, status })
      renderView()

      await screen.findByRole('heading', { name: 'Regional Partner Conference' })
      expect(screen.queryByLabelText('Cancellation reason')).toBeNull()
      expect(screen.queryByRole('button', { name: 'Cancel event' })).toBeNull()
    },
  )
})

describe('Mark Event as Completed', () => {
  it('marks an ended confirmed Event complete and reloads its Activity Log', async () => {
    const completedEvent = {
      ...EVENT,
      status: 'event_completed' as const,
      activity: [
        {
          from_status: 'safety_check_passed',
          to_status: 'event_completed',
          note: 'Event marked completed by the assigned Event Coordinator.',
          changed_by_name: 'Sam Tan',
          created_at: '2026-09-10T03:00:00Z',
        },
        ...EVENT.activity,
      ],
    }
    mockGet
      .mockResolvedValueOnce({
        ...EVENT,
        status: 'safety_check_passed',
        proposed_end: '2020-01-01T12:00:00Z',
      })
      .mockResolvedValueOnce(completedEvent)
    mockComplete.mockResolvedValue(completedEvent)
    renderView()

    await userEvent.click(await screen.findByRole('button', { name: 'Mark Event Completed' }))

    expect(mockComplete).toHaveBeenCalledWith(7)
    expect(await screen.findByText('Event Completed', { selector: '.badge' })).toBeInTheDocument()
    expect(screen.getByText(/Sam Tan/)).toBeInTheDocument()
    expect(
      screen.getByText('Event marked completed by the assigned Event Coordinator.'),
    ).toBeInTheDocument()
  })

  it('shows the scheduled end and displays the server refusal before that time', async () => {
    mockGet.mockResolvedValue({
      ...EVENT,
      status: 'safety_check_passed',
      proposed_end: '2099-01-01T12:00:00Z',
    })
    mockComplete.mockRejectedValue(
      new ApiError(409, 'An event cannot be marked completed before its scheduled end time has passed.'),
    )
    renderView()

    expect(await screen.findByText(/Scheduled end:/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Mark Event Completed' }))
    expect(mockComplete).toHaveBeenCalledWith(7)
    expect(
      await screen.findByText(
        'An event cannot be marked completed before its scheduled end time has passed.',
      ),
    ).toBeInTheDocument()
  })

  it('shows a useful error when completion is refused', async () => {
    mockGet.mockResolvedValue({
      ...EVENT,
      status: 'safety_check_passed',
      proposed_end: '2020-01-01T12:00:00Z',
    })
    mockComplete.mockRejectedValue(
      new ApiError(409, 'An event cannot be marked completed before its scheduled end time has passed.'),
    )
    renderView()

    await userEvent.click(await screen.findByRole('button', { name: 'Mark Event Completed' }))

    expect(
      await screen.findByText(
        'An event cannot be marked completed before its scheduled end time has passed.',
      ),
    ).toBeInTheDocument()
  })

  it.each([
    'planning_event',
    'awaiting_safety_check',
    'event_completed',
    'event_cancelled',
  ] as const)(
    'does not offer completion for %s',
    async (status) => {
      mockGet.mockResolvedValue({ ...EVENT, status })
      renderView()

      await screen.findByRole('heading', { name: 'Regional Partner Conference' })
      expect(screen.queryByRole('button', { name: 'Mark Event Completed' })).not.toBeInTheDocument()
    },
  )
})

describe('SCRUM-39 - the venue booking card follows the event status', () => {
  it('is offered once the event is approved', async () => {
    mockGet.mockResolvedValue({ ...EVENT, status: 'event_approved' })
    renderView()
    expect(await screen.findByLabelText('venue booking stub')).toBeInTheDocument()
  })

  it('is not offered while the request is still awaiting review', async () => {
    renderView()
    await screen.findByRole('heading', { name: 'Regional Partner Conference' })
    expect(screen.queryByLabelText('venue booking stub')).not.toBeInTheDocument()
  })

  it('is not offered for a rejected event', async () => {
    mockGet.mockResolvedValue({ ...EVENT, status: 'event_rejected' })
    renderView()
    await screen.findByRole('heading', { name: 'Regional Partner Conference' })
    expect(screen.queryByLabelText('venue booking stub')).not.toBeInTheDocument()
  })
})

describe('ER AC1 - the equipment requirements card', () => {
  it('is on the Coordinator’s event page, for that event', async () => {
    mockGet.mockResolvedValue({ ...EVENT, status: 'event_approved' })
    renderView()

    const card = await screen.findByLabelText('equipment requirements stub')
    expect(card).toHaveAttribute('data-event-id', '7')
    expect(card).toHaveAttribute('data-event-status', 'event_approved')
  })

  it('is given the Organiser’s picks, so a requirement can be based on one', async () => {
    mockGet.mockResolvedValue({
      ...EVENT,
      status: 'event_approved',
      equipment_items: [
        {
          id: 31,
          equipment_id: 11,
          equipment_name: 'Shure BLX24 Handheld Microphone',
          equipment_category: 'Audio',
          quantity_requested: 4,
          technical_requirements: null,
          status: 'requested',
        },
      ],
    })
    renderView()

    const card = await screen.findByLabelText('equipment requirements stub')
    expect(within(card).getByText('Shure BLX24 Handheld Microphone')).toBeInTheDocument()
  })

  it('is given the Organiser’s other equipment notes as context', async () => {
    mockGet.mockResolvedValue({
      ...EVENT,
      status: 'event_approved',
      equipment_requirements: 'Stage left, near the fire exit',
    })
    renderView()

    const card = await screen.findByLabelText('equipment requirements stub')
    expect(within(card).getByText('stub notes: Stage left, near the fire exit')).toBeInTheDocument()
  })

  it('is present while the event is under review too, where it explains the wait', async () => {
    mockGet.mockResolvedValue({ ...EVENT, status: 'under_review' })
    renderView()

    const card = await screen.findByLabelText('equipment requirements stub')
    expect(card).toHaveAttribute('data-event-status', 'under_review')
  })

  it('does not replace the Organiser’s own equipment under Event Details', async () => {
    mockGet.mockResolvedValue({ ...EVENT, status: 'event_approved' })
    renderView()
    await screen.findByLabelText('equipment requirements stub')

    // What the Organiser asked for is still part of their request. Scoped to
    // the Event Details list: an approved Event also has the edit form, whose
    // field has the same label.
    expect(screen.getByText('Equipment requirements', { selector: 'dt' })).toBeInTheDocument()
  })
})
