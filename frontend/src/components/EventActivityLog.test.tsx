import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { EventActivityLog } from './EventActivityLog'

describe('EventActivityLog', () => {
  it('shows current status and the action, author, timestamp, and note', () => {
    render(
      <EventActivityLog
        status="under_review"
        activity={[
          {
            from_status: 'submitted_awaiting_coordinator',
            to_status: 'under_review',
            changed_by_name: 'Lena Lead',
            created_at: '2026-10-01T09:30:00Z',
            note: 'Assigned to Sam Tan; review started.',
          },
        ]}
      />,
    )

    expect(screen.getByText('Current status: Under Review')).toBeInTheDocument()
    expect(screen.getByText('Submitted – Awaiting Coordinator')).toBeInTheDocument()
    expect(screen.getByText('Under Review', { selector: 'strong' })).toBeInTheDocument()
    expect(screen.getByText(/Lena Lead/)).toBeInTheDocument()
    expect(screen.getByText(/2026/)).toBeInTheDocument()
    expect(screen.getByText('Assigned to Sam Tan; review started.')).toBeInTheDocument()
  })

  it('states when no activity has been recorded yet', () => {
    render(<EventActivityLog status="draft" activity={[]} />)

    expect(screen.getByText('Current status: Draft')).toBeInTheDocument()
    expect(screen.getByText('No activity recorded yet.')).toBeInTheDocument()
  })
})
