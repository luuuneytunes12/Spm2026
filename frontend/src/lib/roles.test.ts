/**
 * Event Coordinator Lead role -- frontend mirror of backend/app/core/roles.py.
 *   AC1  Lead role carries assignment powers on top of a Coordinator's
 *   AC2  Lead lands on its own home page and is labelled
 *   AC3  existing roles' permissions and home pages are unchanged
 */
import { describe, expect, it } from 'vitest'
import { Permission, ROLE_HOME_PATH, ROLE_LABELS, ROLE_PERMISSIONS, Role, roleHas } from './roles'

describe('Event Coordinator Lead role', () => {
  it('AC1: uses the database enum label and can assign and view all assignments', () => {
    expect(Role.COORDINATOR_LEAD).toBe('event_coordinator_lead')
    expect(roleHas(Role.COORDINATOR_LEAD, Permission.ASSIGNMENT_MANAGE)).toBe(true)
    expect(roleHas(Role.COORDINATOR_LEAD, Permission.ASSIGNMENT_VIEW_ALL)).toBe(true)
  })

  it('AC1: a plain Coordinator cannot assign or view all assignments', () => {
    expect(roleHas(Role.COORDINATOR, Permission.ASSIGNMENT_MANAGE)).toBe(false)
    expect(roleHas(Role.COORDINATOR, Permission.ASSIGNMENT_VIEW_ALL)).toBe(false)
  })

  it('AC2: holds every permission a Coordinator holds', () => {
    for (const p of ROLE_PERMISSIONS[Role.COORDINATOR]) {
      expect(roleHas(Role.COORDINATOR_LEAD, p)).toBe(true)
    }
  })

  it('AC2: has a label and its own home page', () => {
    expect(ROLE_LABELS[Role.COORDINATOR_LEAD]).toBe('Event Coordinator Lead')
    expect(ROLE_HOME_PATH[Role.COORDINATOR_LEAD]).toBe('/coordinator-lead')
  })

  it('AC3: existing roles keep their home pages', () => {
    expect(ROLE_HOME_PATH[Role.ORGANISER]).toBe('/organiser')
    expect(ROLE_HOME_PATH[Role.COORDINATOR]).toBe('/coordinator')
    expect(ROLE_HOME_PATH[Role.VENUE_STAFF]).toBe('/venue-staff')
    expect(ROLE_HOME_PATH[Role.TECH_SUPPORT]).toBe('/tech-support')
    expect(ROLE_HOME_PATH[Role.ATTENDEE]).toBe('/attendee')
  })

  it('AC3: existing non-admin roles gain no assignment permissions', () => {
    for (const r of [Role.COORDINATOR, Role.VENUE_STAFF, Role.TECH_SUPPORT, Role.ATTENDEE]) {
      expect(roleHas(r, Permission.ASSIGNMENT_MANAGE)).toBe(false)
      expect(roleHas(r, Permission.ASSIGNMENT_VIEW_ALL)).toBe(false)
    }
  })
})
