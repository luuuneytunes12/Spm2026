/**
 * Unit tests for the equipment requirement client's shared definitions.
 *
 * The status window is the one thing the frontend and backend must agree
 * on: it decides when the Coordinator's card is editable and when Technical
 * Support's list offers an event. These pin it, so a change on one side
 * that is not made on the other fails here instead of showing up as a
 * button that the server then refuses.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { EventStatus } from './events'
import {
  EQUIPMENT_ACTIVE_STATUSES,
  TECH_SUPPORT_STATUS_OPTIONS,
  canRecordEquipment,
  progressText,
  requirementStatusLabel,
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
    expect([...EQUIPMENT_ACTIVE_STATUSES].sort()).toEqual(['approved', 'confirmed', 'planning'])
  })

  it.each([EventStatus.APPROVED, EventStatus.PLANNING, EventStatus.CONFIRMED])(
    'lets equipment be recorded while the event is %s',
    (status) => {
      expect(canRecordEquipment(status)).toBe(true)
    },
  )

  it.each([
    EventStatus.DRAFT,
    EventStatus.SUBMITTED,
    EventStatus.UNDER_REVIEW,
    EventStatus.CHANGES_REQUESTED,
    EventStatus.REJECTED,
    EventStatus.COMPLETED,
    EventStatus.CANCELLED,
  ])('does not while the event is %s', (status) => {
    expect(canRecordEquipment(status)).toBe(false)
  })
})

describe('requirementStatusLabel', () => {
  it('reads a status the way a person would say it', () => {
    expect(requirementStatusLabel('requested')).toBe('Requested')
    expect(requirementStatusLabel('reviewing')).toBe('Reviewing')
    expect(requirementStatusLabel('reserved')).toBe('Reserved')
  })

  it('shows the stored rejected value as Unavailable', () => {
    // No new value in the shared enum: this feature just calls it what the
    // customer calls it (W1: "found to be unavailable").
    expect(requirementStatusLabel('rejected')).toBe('Unavailable')
  })

  it('shows a status it has never heard of as it arrives, rather than hiding the row', () => {
    expect(requirementStatusLabel('on_the_truck')).toBe('on_the_truck')
  })
})

describe('progressText', () => {
  it('says how much of what is needed has been reserved', () => {
    expect(progressText(3, 5)).toBe('3 of 5 reserved')
    expect(progressText(5, 5)).toBe('5 of 5 reserved')
  })

  it('says nothing while nothing is reserved, rather than "0 of 5 reserved"', () => {
    expect(progressText(0, 5)).toBeNull()
  })

  it('still reads honestly if more is reserved than is needed', () => {
    expect(progressText(4, 2)).toBe('4 of 2 reserved')
  })
})

describe('TECH_SUPPORT_STATUS_OPTIONS', () => {
  it('offers requested, reviewing and unavailable, in the words used on screen', () => {
    expect(TECH_SUPPORT_STATUS_OPTIONS).toEqual([
      { value: 'requested', label: 'Requested' },
      { value: 'reviewing', label: 'Reviewing' },
      { value: 'rejected', label: 'Unavailable' },
    ])
  })

  it('never offers reserved: that has to be backed by a real reservation', () => {
    expect(TECH_SUPPORT_STATUS_OPTIONS.map((o) => o.value)).not.toContain('reserved')
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
})
