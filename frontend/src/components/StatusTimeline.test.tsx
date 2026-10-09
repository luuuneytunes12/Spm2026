/**
 * The status timeline shared by the Coordinator's, the Organiser's and the
 * Safety Officer's event pages: every role reads the same stages, with the
 * event's actual progress marked on them.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { StatusTimeline } from './StatusTimeline'

const stages = () => screen.getAllByRole('listitem').map((li) => li.textContent)

describe('StatusTimeline', () => {
  it('shows the whole lifecycle and marks the current stage', () => {
    render(<StatusTimeline status="planning_event" activity={[]} />)

    expect(stages()).toEqual([
      'Submitted – Awaiting Coordinator',
      'Under Review',
      'Event Approved',
      'Planning Event',
      'Awaiting Safety Check',
      'Safety Check Passed (Event Confirmed)',
      'Event Completed',
    ])
    expect(screen.getByRole('listitem', { current: 'step' })).toHaveTextContent('Planning Event')
  })

  it('describes what the current status means', () => {
    render(<StatusTimeline status="awaiting_safety_check" activity={[]} />)
    expect(screen.getByText(/Submitted to the Safety Officer/)).toBeInTheDocument()
  })

  it('shows an exit from the path as its own stage, after where the event left it', () => {
    render(
      <StatusTimeline
        status="event_rejected"
        activity={[{ from_status: 'under_review' }]}
      />,
    )
    expect(stages().at(-1)).toBe('Event Rejected')
    expect(screen.getByRole('listitem', { current: 'step' })).toHaveTextContent('Event Rejected')
  })
})
