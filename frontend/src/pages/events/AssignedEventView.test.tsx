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
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/api'
import { AssignedEventView } from './AssignedEventView'

vi.mock('../../lib/events', async () => {
  const actual = await vi.importActual<typeof import('../../lib/events')>('../../lib/events')
  return { ...actual, getAssignedEvent: vi.fn() }
})

import { getAssignedEvent } from '../../lib/events'
import type { AssignedEventDetail } from '../../lib/events'

const mockGet = vi.mocked(getAssignedEvent)

const EVENT: AssignedEventDetail = {
  id: 7,
  organiser_id: 1,
  coordinator_id: 2,
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
  special_arrangements: 'Halal catering',
  registration_enabled: true,
  status: 'submitted',
  submitted_at: '2026-09-10T02:00:00Z',
  created_at: '2026-09-09T00:00:00Z',
  updated_at: '2026-09-10T02:00:00Z',
  organiser: { id: 1, name: 'Priya Menon', email: 'priya@connectsphere.test' },
  activity: [
    {
      from_status: 'draft',
      to_status: 'submitted',
      note: 'Submitted by organiser.',
      changed_by_name: 'Priya Menon',
      created_at: '2026-09-10T02:00:00Z',
    },
  ],
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
})

describe('AC1 - the full requirements are visible', () => {
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
      ['Equipment requirements', '2 projectors, 4 radio mics'],
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
    expect(screen.getAllByText('Not provided')).toHaveLength(2)
  })

  it('says so plainly when registration is not required', async () => {
    mockGet.mockResolvedValue({ ...EVENT, registration_enabled: false })
    renderView()

    expect(await screen.findByText('Registration not required')).toBeInTheDocument()
  })

  it('renders a field the Organiser wrote one item per line as a bulleted list', async () => {
    mockGet.mockResolvedValue({
      ...EVENT,
      equipment_requirements: 'Two projectors\nFour radio microphones\nA live-stream setup',
    })
    renderView()

    const label = await screen.findByText('Equipment requirements')
    const list = label.parentElement!.querySelector('ul.detail-value-list')
    expect(list).not.toBeNull()
    expect(within(list as HTMLElement).getAllByRole('listitem').map((li) => li.textContent)).toEqual([
      'Two projectors',
      'Four radio microphones',
      'A live-stream setup',
    ])
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
    await waitFor(() => expect(screen.getAllByText('Under review').length).toBeGreaterThan(0))
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
    const steps = ['Submitted', 'Under review', 'Approved', 'Planning', 'Confirmed', 'Completed']
    for (const label of steps) {
      expect(await screen.findByText(label, { selector: '.status-step-label' })).toBeInTheDocument()
    }
    // Exactly one stage is "current" -- the event's actual status.
    const current = screen
      .getByText('Submitted', { selector: '.status-step-label' })
      .closest('[aria-current="step"]')
    expect(current).not.toBeNull()
    expect(
      screen.getAllByRole('listitem').filter((li) => li.getAttribute('aria-current') === 'step'),
    ).toHaveLength(1)
  })

  it("does not show Draft on the timeline -- a Coordinator's process only begins at Submitted", async () => {
    renderView()

    await screen.findByText('Submitted', { selector: '.status-step-label' })
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
      status: 'changes_requested',
      activity: [
        {
          from_status: 'under_review',
          to_status: 'changes_requested',
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
    await screen.findByText('Changes requested', { selector: '.status-step-label' })
    const reviewStep = screen
      .getByText('Under review', { selector: '.status-step-label' })
      .closest('.status-step')
    expect(reviewStep).toHaveClass('status-step-done')
    const approvedStep = screen.getByText('Approved').closest('.status-step')
    expect(approvedStep).toHaveClass('status-step-upcoming')
    const branchStep = screen
      .getByText('Changes requested', { selector: '.status-step-label' })
      .closest('.status-step')
    expect(branchStep).toHaveClass('status-step-branch', 'status-step-branch-warning')
  })

  it('TC-S3-3f: a rejection is shown in a danger tone', async () => {
    mockGet.mockResolvedValue({
      ...EVENT,
      status: 'rejected',
      activity: [
        {
          from_status: 'under_review',
          to_status: 'rejected',
          note: null,
          changed_by_name: 'Sam Tan',
          created_at: '2026-09-12T09:00:00Z',
        },
      ],
    })
    renderView()

    const branchStep = await screen.findByText('Rejected', { selector: '.status-step-label' })
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
          from_status: 'submitted',
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
})

describe('AC5 - events that are not assigned to me', () => {
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
  it('has no way to edit the event -- viewing is the whole story', async () => {
    renderView()
    await screen.findByRole('heading', { name: 'Regional Partner Conference' })

    await waitFor(() => expect(mockGet).toHaveBeenCalledWith(7))
    expect(screen.queryByRole('button')).toBeNull()
    expect(screen.queryByRole('link', { name: /edit/i })).toBeNull()
  })
})
