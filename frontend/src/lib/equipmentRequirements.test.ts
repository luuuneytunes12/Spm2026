/**
 * Unit tests for the equipment requirement client's shared definitions.
 *
 * The status window is the one thing the frontend and backend must agree
 * on: it decides when the Coordinator's card is editable and when Technical
 * Support's list offers an event. These pin it, so a change on one side
 * that is not made on the other fails here instead of showing up as a
 * button that the server then refuses.
 */
import { describe, expect, it } from 'vitest'
import { EventStatus } from './events'
import {
  EQUIPMENT_ACTIVE_STATUSES,
  canRecordEquipment,
  requirementStatusLabel,
} from './equipmentRequirements'

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
    expect(requirementStatusLabel('reviewing')).toBe('In review')
    expect(requirementStatusLabel('reserved')).toBe('Reserved')
  })

  it('shows a status it has never heard of as it arrives, rather than hiding the row', () => {
    expect(requirementStatusLabel('on_the_truck')).toBe('on_the_truck')
  })
})
