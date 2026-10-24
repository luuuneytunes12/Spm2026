/**
 * Component tests for the clarification UI:
 *
 *   SCRUM-27  (Coordinator) Request Event Clarification
 *   SCRUM-103 (Organiser)   Respond to Clarification Request
 *
 * Whether a request or reply is accepted is the backend's job (see
 * backend/tests/test_event_clarification.py). These cover what the screens
 * offer, and what they refuse to send.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../lib/api'
import { EventView } from '../pages/events/EventView'
import { ClarificationReplyPanel } from './ClarificationReplyPanel'
import { ClarificationRequestPanel } from './ClarificationRequestPanel'

vi.mock('../lib/clarifications', () => ({
  listClarifications: vi.fn(),
  requestClarification: vi.fn(),
  replyToClarification: vi.fn(),
}))
vi.mock('../lib/events', async () => {
  const actual = await vi.importActual<typeof import('../lib/events')>('../lib/events')
  return {
    ...actual,
    getEvent: vi.fn(),
    getOwnEventActivity: vi.fn(),
    listOwnChangeRequests: vi.fn(),
  }
})
vi.mock('./AttendeeListSection', () => ({ AttendeeListSection: () => null }))

import { listClarifications, replyToClarification, requestClarification } from '../lib/clarifications'
import type { ClarificationOut } from '../lib/clarifications'
import { getEvent, getOwnEventActivity, listOwnChangeRequests } from '../lib/events'
import type { EventDetail } from '../lib/events'

const mockList = vi.mocked(listClarifications)
const mockRequest = vi.mocked(requestClarification)
const mockReply = vi.mocked(replyToClarification)

const REQUEST: ClarificationOut = {
  id: 1,
  event_id: 7,
  kind: 'request',
  message: 'How many chairs do you need on stage?',
  author_id: 2,
  author_name: 'Sam Tan',
  created_at: '2026-09-11T03:00:00Z',
}

const EVENT: EventDetail = {
  id: 7,
  organiser_id: 1,
  coordinator_id: 2,
  coordinator: { id: 2, name: 'Sam Tan', email: 'sam@connectsphere.test' },
  name: 'Robotics Summit',
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
  equipment_requirements: '2 projectors',
  equipment_items: [],
  special_arrangements: null,
  registration_enabled: false,
  status: 'awaiting_organiser_reply',
  submitted_at: '2026-09-10T02:00:00Z',
  created_at: '2026-09-09T00:00:00Z',
  updated_at: '2026-09-10T02:00:00Z',
} as EventDetail

beforeEach(() => {
  vi.clearAllMocks()
  mockList.mockResolvedValue([])
})

describe('SCRUM-27 - request clarification (Coordinator)', () => {
  it('AC1: an Under Review event offers a clarification form and sends the text message', async () => {
    mockRequest.mockResolvedValue(REQUEST)
    const onChanged = vi.fn()
    render(<ClarificationRequestPanel eventId={7} status="under_review" onChanged={onChanged} />)

    await userEvent.type(screen.getByLabelText('Clarification request'), '  How many chairs?  ')
    await userEvent.click(screen.getByRole('button', { name: 'Send clarification request' }))

    await waitFor(() => expect(mockRequest).toHaveBeenCalledWith(7, 'How many chairs?'))
    expect(await screen.findByText('Clarification request sent to the Event Organiser.')).toBeInTheDocument()
    expect(onChanged).toHaveBeenCalled()
  })

  it('AC2/AC4: the thread shows who asked, when and the message; the event waits for the Organiser', async () => {
    mockList.mockResolvedValue([REQUEST])
    render(<ClarificationRequestPanel eventId={7} status="awaiting_organiser_reply" />)

    expect(await screen.findByText('How many chairs do you need on stage?')).toBeInTheDocument()
    expect(screen.getByText(/Sam Tan/)).toBeInTheDocument()
    expect(screen.getByText('Waiting for the Event Organiser to reply.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Send clarification request' })).not.toBeInTheDocument()
  })

  it('AC5: a blank message is blocked and flagged, and nothing is sent', async () => {
    render(<ClarificationRequestPanel eventId={7} status="under_review" />)

    await userEvent.type(screen.getByLabelText('Clarification request'), '   ')
    await userEvent.click(screen.getByRole('button', { name: 'Send clarification request' }))

    expect(screen.getByLabelText('Clarification request')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByText('Enter a message for the Event Organiser.')).toBeInTheDocument()
    expect(mockRequest).not.toHaveBeenCalled()
  })

  it('AC6: no form is offered when the event is not Under Review', async () => {
    for (const status of ['submitted_awaiting_coordinator', 'event_approved', 'planning_event']) {
      const { unmount } = render(<ClarificationRequestPanel eventId={7} status={status} />)
      await waitFor(() => expect(mockList).toHaveBeenCalled())
      expect(screen.queryByLabelText('Clarification request')).not.toBeInTheDocument()
      unmount()
    }
  })

  it('AC6: a refusal from the server is shown and the message stays for editing', async () => {
    mockRequest.mockRejectedValue(new ApiError(409, 'Only an Under Review event can be queried.', []))
    render(<ClarificationRequestPanel eventId={7} status="under_review" />)

    await userEvent.type(screen.getByLabelText('Clarification request'), 'Hello?')
    await userEvent.click(screen.getByRole('button', { name: 'Send clarification request' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Only an Under Review event can be queried.')
    expect(screen.getByLabelText('Clarification request')).toHaveValue('Hello?')
  })
})

describe('SCRUM-103 - respond to clarification (Organiser)', () => {
  it('AC1: shows the full request and sends the reply', async () => {
    mockList.mockResolvedValue([REQUEST])
    mockReply.mockResolvedValue({ ...REQUEST, id: 2, kind: 'reply', message: 'Six chairs.' })
    const onChanged = vi.fn()
    render(<ClarificationReplyPanel event={EVENT} onChanged={onChanged} />)

    expect(await screen.findByText('How many chairs do you need on stage?')).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Your reply'), 'Six chairs.')
    await userEvent.click(screen.getByRole('button', { name: 'Send reply' }))

    await waitFor(() => expect(mockReply).toHaveBeenCalledWith(7, { message: 'Six chairs.' }))
    expect(await screen.findByText(/Your reply has been sent/)).toBeInTheDocument()
    expect(onChanged).toHaveBeenCalled()
  })

  it('AC5: an empty reply is blocked and flagged, and nothing is sent', async () => {
    render(<ClarificationReplyPanel event={EVENT} />)

    await userEvent.click(screen.getByRole('button', { name: 'Send reply' }))

    expect(screen.getByLabelText('Your reply')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByText('Enter your reply.')).toBeInTheDocument()
    expect(mockReply).not.toHaveBeenCalled()
  })

  it('AC4: no reply form unless the event is Awaiting Organiser Reply', async () => {
    render(<ClarificationReplyPanel event={{ ...EVENT, status: 'under_review' }} />)
    await waitFor(() => expect(mockList).toHaveBeenCalled())
    expect(screen.queryByLabelText('Your reply')).not.toBeInTheDocument()
  })

  it('AC6: amended fields are sent as updates -- only the ones that changed', async () => {
    mockReply.mockResolvedValue({ ...REQUEST, id: 2, kind: 'reply', message: 'Updated.' })
    render(<ClarificationReplyPanel event={EVENT} />)

    await userEvent.type(screen.getByLabelText('Your reply'), 'Updated.')
    await userEvent.click(screen.getByLabelText('Update the request fields'))
    const attendees = screen.getByLabelText('Expected attendees')
    await userEvent.clear(attendees)
    await userEvent.type(attendees, '150')
    await userEvent.click(screen.getByRole('button', { name: 'Send reply' }))

    await waitFor(() =>
      expect(mockReply).toHaveBeenCalledWith(7, {
        message: 'Updated.',
        updates: { expected_attendance: 150 },
      }),
    )
  })

  it('AC6: without ticking "Update the request fields" no updates are sent', async () => {
    mockReply.mockResolvedValue({ ...REQUEST, id: 2, kind: 'reply', message: 'ok' })
    render(<ClarificationReplyPanel event={EVENT} />)

    await userEvent.type(screen.getByLabelText('Your reply'), 'ok')
    await userEvent.click(screen.getByRole('button', { name: 'Send reply' }))

    await waitFor(() => expect(mockReply).toHaveBeenCalledWith(7, { message: 'ok' }))
  })

  it('AC4: a refusal from the server is shown', async () => {
    mockReply.mockRejectedValue(new ApiError(409, 'This event is not awaiting your reply.', []))
    render(<ClarificationReplyPanel event={EVENT} />)

    await userEvent.type(screen.getByLabelText('Your reply'), 'hi')
    await userEvent.click(screen.getByRole('button', { name: 'Send reply' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('This event is not awaiting your reply.')
  })
})

describe('the Organiser event page mounts the reply panel', () => {
  function renderView() {
    return render(
      <MemoryRouter initialEntries={['/organiser/events/7']}>
        <Routes>
          <Route path="/organiser/events/:id" element={<EventView />} />
        </Routes>
      </MemoryRouter>,
    )
  }

  it('SCRUM-103 AC1: offers the reply form on an Awaiting Organiser Reply event', async () => {
    vi.mocked(getEvent).mockResolvedValue(EVENT)
    vi.mocked(getOwnEventActivity).mockResolvedValue([])
    vi.mocked(listOwnChangeRequests).mockResolvedValue([])
    mockList.mockResolvedValue([REQUEST])
    renderView()
    expect(await screen.findByLabelText('Your reply')).toBeInTheDocument()
  })

  it('SCRUM-103 AC4: no reply form once the event is back Under Review', async () => {
    vi.mocked(getEvent).mockResolvedValue({ ...EVENT, status: 'under_review' })
    vi.mocked(getOwnEventActivity).mockResolvedValue([])
    vi.mocked(listOwnChangeRequests).mockResolvedValue([])
    renderView()
    await screen.findByText('Robotics Summit')
    expect(screen.queryByLabelText('Your reply')).not.toBeInTheDocument()
  })
})
