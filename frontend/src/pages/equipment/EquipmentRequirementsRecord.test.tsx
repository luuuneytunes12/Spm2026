/**
 * Component tests for Technical Support's event record.
 *
 * Traceability (see docs/test-cases-equipment-requirements.md):
 *   ER AC2  requirements are visible to Technical Support Staff from the
 *           event record
 *
 * Which events can be opened, and what a requirement carries, are the
 * backend's rules (backend/tests/test_equipment_requirements.py). These
 * tests cover what the screen does with the answer, including the refusal.
 */
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../lib/api'
import { EquipmentRequirementsRecord } from './EquipmentRequirementsRecord'

vi.mock('../../lib/equipmentRequirements', async () => {
  const actual = await vi.importActual<typeof import('../../lib/equipmentRequirements')>(
    '../../lib/equipmentRequirements',
  )
  return { ...actual, getSupportEvent: vi.fn(), listSupportEvents: vi.fn() }
})

import { getSupportEvent } from '../../lib/equipmentRequirements'
import type { SupportEventRecord } from '../../lib/equipmentRequirements'

const mockGet = vi.mocked(getSupportEvent)

const RECORD: SupportEventRecord = {
  id: 7,
  name: 'Regional Partner Conference',
  event_type: 'conference',
  proposed_start: '2026-11-02T09:00:00Z',
  proposed_end: '2026-11-02T17:00:00Z',
  expected_attendance: 120,
  venue_requirements: 'Main hall, stage, podium',
  status: 'approved',
  coordinator: { id: 2, name: 'Sam Tan', email: 'sam@connectsphere.test' },
  requirements: [
    {
      id: 1,
      category: 'Audio',
      quantity_needed: 6,
      technical_notes: 'Handheld wireless, for panel Q&A',
      status: 'requested',
    },
    { id: 2, category: 'Projection', quantity_needed: 2, technical_notes: null, status: 'requested' },
  ],
}

function renderPage(id = '7') {
  return render(
    <MemoryRouter initialEntries={[`/equipment-requirements/${id}`]}>
      <Routes>
        <Route path="/equipment-requirements/:eventId" element={<EquipmentRequirementsRecord />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockGet.mockResolvedValue(RECORD)
})

describe('ER AC2 - the event record', () => {
  it('asks for the event named in the address', async () => {
    renderPage('7')

    await screen.findByRole('heading', { name: 'Regional Partner Conference' })
    expect(mockGet).toHaveBeenCalledWith(7)
  })

  it('shows what the event is, so the equipment can be judged against it', async () => {
    renderPage()

    await screen.findByRole('heading', { name: 'Regional Partner Conference' })
    for (const [label, value] of [
      ['Expected attendance', '120'],
      ['Venue requirements', 'Main hall, stage, podium'],
      ['Event type', 'conference'],
    ]) {
      expect(screen.getByText(label).parentElement).toHaveTextContent(value)
    }
    expect(screen.getByText('Approved')).toBeInTheDocument()
  })

  it('names the Coordinator to ask about it', async () => {
    renderPage()

    await screen.findByRole('heading', { name: 'Regional Partner Conference' })
    expect(screen.getByText('Event Coordinator').parentElement).toHaveTextContent('Sam Tan')
    expect(screen.getByText('Event Coordinator').parentElement).toHaveTextContent(
      'sam@connectsphere.test',
    )
  })

  it('says so when no Coordinator is assigned, rather than leaving a blank', async () => {
    mockGet.mockResolvedValue({ ...RECORD, coordinator: null })
    renderPage()

    await screen.findByRole('heading', { name: 'Regional Partner Conference' })
    expect(screen.getByText('Event Coordinator').parentElement).toHaveTextContent('Not assigned')
  })

  it('marks a detail the Organiser never gave rather than rendering a blank row', async () => {
    mockGet.mockResolvedValue({ ...RECORD, venue_requirements: null })
    renderPage()

    await screen.findByRole('heading', { name: 'Regional Partner Conference' })
    expect(screen.getByText('Venue requirements').parentElement).toHaveTextContent('Not provided')
  })

  it('shows each requirement with its type, quantity, notes and status', async () => {
    renderPage()

    const list = await screen.findByRole('list', { name: 'Equipment requirements' })
    const audio = within(list).getByText('Audio').closest('li')!
    expect(within(audio).getByText(/6/)).toBeInTheDocument()
    expect(within(audio).getByText('Handheld wireless, for panel Q&A')).toBeInTheDocument()
    expect(within(audio).getByText('Requested')).toBeInTheDocument()
    expect(within(list).getByText('Projection')).toBeInTheDocument()
  })

  it('says so when nothing has been recorded yet', async () => {
    mockGet.mockResolvedValue({ ...RECORD, requirements: [] })
    renderPage()

    expect(await screen.findByText('No equipment recorded yet.')).toBeInTheDocument()
  })

  it('links back to the list', async () => {
    renderPage()

    const link = await screen.findByRole('link', { name: /equipment requirements/i })
    expect(link).toHaveAttribute('href', '/equipment-requirements')
  })

  it('offers no way to change anything -- reviewing is a later story', async () => {
    renderPage()
    await screen.findByRole('heading', { name: 'Regional Partner Conference' })

    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})

describe('an event that cannot be shown', () => {
  it('says so for an event that does not exist or is not yet approved', async () => {
    mockGet.mockRejectedValue(new ApiError(404, 'Event not found'))
    renderPage('999')

    expect(await screen.findByRole('alert')).toHaveTextContent('Event not found')
    expect(screen.queryByRole('list', { name: 'Equipment requirements' })).not.toBeInTheDocument()
  })

  it('still offers a way back from an event that is not found', async () => {
    mockGet.mockRejectedValue(new ApiError(404, 'Event not found'))
    renderPage('999')

    await screen.findByRole('alert')
    expect(screen.getByRole('link', { name: /equipment requirements/i })).toHaveAttribute(
      'href',
      '/equipment-requirements',
    )
  })

  it('says something useful when the server cannot be reached', async () => {
    mockGet.mockRejectedValue(new Error('network down'))
    renderPage()

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not/i)
  })
})
