import { expect, test } from '@playwright/test'
import { call } from './support/api'
import { approvedEvent, arrange, as, expectNoSeriousViolations, notice, signedIn, tabToAndFollow } from './support/arranged'
import { openAs } from './support/coordinator-users'
import type { SeedUser } from './support/db'
import { removeEquipment, removeUsers, removeVenue, resetUsers, seedEquipment, seedUsers, seedVenue } from './support/db'

/**
 * End-to-end coverage of the Safety Officer's notifications about their
 * queue, plus its DoD accessibility checks.
 *
 *   TC-SN-1e -- AC1, an Event submitted for its Safety Check names the Event, date and Coordinator; it opens the check
 *   TC-SN-2e -- AC2, an approved change sends it back to planning: it has left the queue, with why; it opens the queue
 *   TC-SN-3e -- every Safety Officer is told; nobody else
 *   TC-SN-A1 -- DoD 8, axe on the Safety Officer's Notifications page (light, dark)
 *   TC-SN-A2 -- DoD 8, keyboard: the notice's "View event" link is reachable, visible focus
 */
const PASSWORD = 'e2e-safety-notice-123'
const user = (key: string, name: string, role: SeedUser['role']): SeedUser => ({
  email: `e2e_sn_${key}@cs.local`, name, role, password: PASSWORD,
})
const ORG = user('org', 'Olivia Organiser', 'organiser')
const COORD = user('coord', 'Sam Tan', 'coordinator')
const STAFF = user('staff', 'Vera Venue', 'venue_staff')
const TECH = user('tech', 'Tess Tech', 'tech_support')
const SOFIA = user('sofia', 'Sofia Safety', 'safety_officer')
const SID = user('sid', 'Sid Safety', 'safety_officer')
const USERS = [ORG, COORD, STAFF, TECH, SOFIA, SID]
const EMAILS = USERS.map((u) => u.email)
const VENUE = { name: 'SN Auditorium', location: 'Block S', capacity: 400 }
const ITEM = { name: 'SN Projector', category: 'SN Projection', total_quantity: 10 }

let equipmentId = 0

test.beforeAll(() => {
  seedUsers(USERS)
  seedVenue(VENUE)
  equipmentId = seedEquipment(ITEM)
})
test.beforeEach(() => resetUsers(EMAILS))
test.afterAll(() => {
  removeUsers(EMAILS)
  removeVenue(VENUE.name)
  removeEquipment(ITEM.name)
})

/** An arranged Event of Sam's, submitted for its Safety Check. */
async function awaitingCheck(request: Parameters<typeof as>[0], name: string) {
  const eventId = await approvedEvent(request, ORG, COORD, name, equipmentId)
  await arrange(request, eventId, { coord: COORD, staff: STAFF, tech: TECH }, VENUE.name, equipmentId)
  await call(request, 'post', `/events/${eventId}/confirm`, await as(request, COORD))
  return eventId
}

test('TC-SN-1e: an Event submitted for its Safety Check names the Event, date and Coordinator, and opens the check', async ({ browser, request }) => {
  const eventId = await awaitingCheck(request, 'Checked Summit')
  const sofia = await signedIn(browser, SOFIA)
  await sofia.goto('/notifications')
  const row = notice(sofia, "'Checked Summit' on")
  await expect(row).toContainText('(Event Coordinator: Sam Tan) was submitted for a Safety Check.')
  await row.getByRole('link', { name: 'View event' }).click()
  await expect(sofia).toHaveURL(new RegExp(`/safety-checks/${eventId}$`))
})

test('TC-SN-2e: an Event sent back to planning has left the queue, with why, and opens the queue', async ({ browser, request }) => {
  const eventId = await awaitingCheck(request, 'Returned Summit')
  // The Organiser asks for more people; the Coordinator approves, which reopens the arrangements.
  const change = await call(
    request, 'post', `/events/${eventId}/change-requests`, await as(request, ORG),
    { description: 'More people', proposed_changes: { expected_attendance: 300 } }, 201,
  )
  await call(request, 'post', `/events/change-requests/${change.id}/approve`, await as(request, COORD), {})
  const sofia = await signedIn(browser, SOFIA)
  await sofia.goto('/notifications')
  const row = notice(sofia, "'Returned Summit' on")
  await expect(row.filter({ hasText: 'has left your Safety Check queue' })).toBeVisible()
  await row.filter({ hasText: 'has left your Safety Check queue' }).getByRole('link', { name: 'View event' }).click()
  await expect(sofia).toHaveURL(/\/safety-checks$/)
})

test('TC-SN-3e: every Safety Officer is told, and nobody else', async ({ browser, request }) => {
  await awaitingCheck(request, 'Everyone Summit')
  const sid = await signedIn(browser, SID)
  await sid.goto('/notifications')
  await expect(notice(sid, "'Everyone Summit' on")).toBeVisible()
  for (const who of [ORG, STAFF, TECH]) {
    const page = await openAs(browser, who)
    await page.goto('/notifications')
    await expect(page.getByText(/submitted for a Safety Check/)).toHaveCount(0)
  }
})

for (const colorScheme of ['light', 'dark'] as const) {
  test(`TC-SN-A1: the Safety Officer's Notifications page passes axe (${colorScheme})`, async ({ browser, request }) => {
    await awaitingCheck(request, `Axe Summit ${colorScheme}`)
    const sofia = await signedIn(browser, SOFIA, { colorScheme })
    await sofia.goto('/notifications')
    await expect(notice(sofia, `Axe Summit ${colorScheme}`)).toBeVisible()
    await expectNoSeriousViolations(sofia, `notifications ${colorScheme}`)
  })
}

test('TC-SN-A2: the notice\'s View event link is keyboard-reachable with visible focus', async ({ browser, request }) => {
  const eventId = await awaitingCheck(request, 'Keyboard Summit')
  const sofia = await signedIn(browser, SOFIA)
  await sofia.goto('/notifications')
  await tabToAndFollow(sofia, notice(sofia, 'Keyboard Summit').getByRole('link', { name: 'View event' }))
  await expect(sofia).toHaveURL(new RegExp(`/safety-checks/${eventId}$`))
})
