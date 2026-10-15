/**
 * Unit tests for the equipment requirement client's shared definitions.
 *
 * The status window is the one thing the frontend and backend must agree
 * on: it decides when the Coordinator's card is editable and when Technical
 * Support's list offers an event. These pin it, so a change on one side
 * that is not made on the other fails here instead of showing up as a
 * button that the server then refuses.
 *
 * The statuses are the Definition of Done's (11b): Requested, Reserved,
 * Unavailable and Available, and no others.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { EventStatus } from './events'
import {
  EQUIPMENT_ACTIVE_STATUSES,
  TECH_SUPPORT_STATUS_OPTIONS,
  canRecordEquipment,
  requirementStatusLabel,
  requirementStatusText,
  reserveForRequirement,
  updateSupportRequirement,
} from './equipmentRequirements'

vi.mock('./api', async () => {
  const actual = await vi.importActual<typeof import('./api')>('./api')
  return { ...actual, apiFetch: vi.fn() }
})

import { apiFetch } from './api'

const mockFetch = vi.mocked(apiFetch)

describe('the status window', () => {
  it('is exactly approved, planning and confirmed', () => {
    // Mirrors EQUIPMENT_ACTIVE_STATUSES in backend/app/domain/equipment_requirements.py.
    expect([...EQUIPMENT_ACTIVE_STATUSES].sort()).toEqual(['event_approved', 'planning_event', 'safety_check_passed'])
  })

  it.each([EventStatus.EVENT_APPROVED, EventStatus.PLANNING_EVENT, EventStatus.SAFETY_CHECK_PASSED])(
    'lets equipment be recorded while the event is %s',
    (status) => {
      expect(canRecordEquipment(status)).toBe(true)
    },
  )

  it.each([
    EventStatus.DRAFT,
    EventStatus.SUBMITTED_AWAITING_COORDINATOR,
    EventStatus.UNDER_REVIEW,
    EventStatus.AWAITING_ORGANISER_REPLY,
    EventStatus.EVENT_REJECTED,
    EventStatus.EVENT_COMPLETED,
    EventStatus.EVENT_CANCELLED,
  ])('does not while the event is %s', (status) => {
    expect(canRecordEquipment(status)).toBe(false)
  })
})

describe('requirementStatusLabel', () => {
  it('reads each of the Definition of Done statuses the way a person would say it', () => {
    expect(requirementStatusLabel('requested')).toBe('Requested')
    expect(requirementStatusLabel('reserved')).toBe('Reserved')
    expect(requirementStatusLabel('unavailable')).toBe('Unavailable')
    expect(requirementStatusLabel('available')).toBe('Available')
  })

  it('shows a status it has never heard of as it arrives, rather than hiding the row', () => {
    expect(requirementStatusLabel('on_the_truck')).toBe('on_the_truck')
  })
})

describe('requirementStatusText', () => {
  // One wording, used by every row on both sides, so a Coordinator and
  // Technical Support never read the same requirement two ways.
  it('is the status alone while nothing is reserved', () => {
    expect(requirementStatusText('requested', 0, 5)).toBe('Requested')
    expect(requirementStatusText('unavailable', 0, 5)).toBe('Unavailable')
  })

  it('is still Requested, with how much is reserved so far, while only part of it is', () => {
    // The Definition of Done has no "in progress": part reserved is Requested,
    // and the figure beside it says how far.
    expect(requirementStatusText('requested', 3, 5)).toBe('Requested — 3 of 5 reserved')
  })

  it('is Reserved once all of it is', () => {
    expect(requirementStatusText('reserved', 5, 5)).toBe('Reserved — 5 of 5')
  })

  it('still reads honestly if more is reserved than is needed', () => {
    expect(requirementStatusText('reserved', 4, 2)).toBe('Reserved — 4 of 2')
  })

  it('is Available, with how much was freed, once the reservation is freed', () => {
    expect(requirementStatusText('available', 0, 5, 3)).toBe('Available — 3 freed')
  })

  it('takes the status the server worked out, not one worked out again from the figures', () => {
    // A stale "reserved" with nothing behind it is not turned into something
    // else here: the server decides, the wording follows.
    expect(requirementStatusText('requested', 5, 5)).toBe('Requested — 5 of 5 reserved')
  })
})

describe('TECH_SUPPORT_STATUS_OPTIONS', () => {
  it('offers Requested and Unavailable, in the words used on screen', () => {
    expect(TECH_SUPPORT_STATUS_OPTIONS).toEqual([
      { value: 'requested', label: 'Requested' },
      { value: 'unavailable', label: 'Unavailable' },
    ])
  })

  it('never offers reserved or available: one needs a real reservation, the other is the event ending', () => {
    const values = TECH_SUPPORT_STATUS_OPTIONS.map((o) => o.value)

    expect(values).not.toContain('reserved')
    expect(values).not.toContain('available')
  })
})

describe('the Technical Support client calls', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockFetch.mockResolvedValue({})
  })

  it('updates a requirement with a PATCH of only what changed', async () => {
    await updateSupportRequirement(4, { quantity_needed: 8 })

    expect(mockFetch).toHaveBeenCalledWith('/equipment-requirements/support/requirements/4', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ quantity_needed: 8 }),
    })
  })

  it('sends the reason with Unavailable', async () => {
    await updateSupportRequirement(4, { status: 'unavailable', reason: 'Under maintenance' })

    const body = JSON.parse((mockFetch.mock.calls[0][1] as { body: string }).body)
    expect(body).toEqual({ status: 'unavailable', reason: 'Under maintenance' })
  })

  it('reserves an item for a requirement', async () => {
    await reserveForRequirement(4, 11, 3)

    expect(mockFetch).toHaveBeenCalledWith('/equipment-requirements/4/reservations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ equipment_id: 11, quantity: 3 }),
    })
  })

  it('leaves the quantity out when none is given, so the server picks it', async () => {
    await reserveForRequirement(4, 11)

    const body = JSON.parse((mockFetch.mock.calls[0][1] as { body: string }).body)
    expect(body).toEqual({ equipment_id: 11 })
  })

  it('sends where the item will be placed, when that is given', async () => {
    await reserveForRequirement(4, 11, 3, 'Stage left')

    const body = JSON.parse((mockFetch.mock.calls[0][1] as { body: string }).body)
    expect(body).toEqual({ equipment_id: 11, quantity: 3, placement_notes: 'Stage left' })
  })

  it('leaves the placement out when there is none', async () => {
    await reserveForRequirement(4, 11, 3, undefined)

    const body = JSON.parse((mockFetch.mock.calls[0][1] as { body: string }).body)
    expect(body).not.toHaveProperty('placement_notes')
  })
})
