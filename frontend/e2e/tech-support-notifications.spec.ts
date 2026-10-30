import { expect, test } from '@playwright/test'
import { call } from './support/api'
import { approvedEvent, as, expectNoSeriousViolations, inDays, notice, tabToAndFollow } from './support/arranged'
import { openAs } from './support/coordinator-users'
import type { SeedUser } from './support/db'
import { removeEquipment, removeUsers, resetUsers, seedEquipment, seedUsers } from './support/db'

/**
 * End-to-end coverage of "Notify Technical Support of equipment changes",
 * plus its DoD accessibility checks.
 *
 *   TC-TN-1e -- AC1, a recorded requirement names the Event, equipment, quantity and date; it opens the record
 *   TC-TN-2e -- AC2, a changed requirement says what changed
 *   TC-TN-3e -- AC3, a rescheduled Event gives the old and new date/time
 *   TC-TN-4e -- every Technical Support Staff member is told; nobody else
 *   TC-TN-A1 -- DoD 8, axe on the Technical Support Notifications page (light, dark)
 *   TC-TN-A2 -- DoD 8, keyboard: the notice's "View event" link is reachable, visible focus
 */
const PASSWORD = 'e2e-tech-notice-123'
const user = (key: string, name: string, role: SeedUser['role']): SeedUser => ({
  email: `e2e_tn_${key}@cs.local`, name, role, password: PASSWORD,
})
const ORG = user('org', 'Olivia Organiser', 'organiser')
const COORD = user('coord', 'Sam Tan', 'coordinator')
const TESS = user('tess', 'Tess Tech', 'tech_support')
const TOM = user('tom', 'Tom Tech', 'tech_support')
const USERS = [ORG, COORD, TESS, TOM]
const EMAILS = USERS.map((u) => u.email)
const ITEM = { name: 'TN Projector', category: 'TN Projection', total_quantity: 10 }

test.beforeAll(() => {
  seedUsers(USERS)
  seedEquipment(ITEM)
})
test.beforeEach(() => resetUsers(EMAILS))
test.afterAll(() => {
  removeUsers(EMAILS)
  removeEquipment(ITEM.name)
})

/** An approved Event with a requirement for 2 x ITEM's category. */
async function required(request: Parameters<typeof as>[0], name: string) {
  const eventId = await approvedEvent(request, ORG, COORD, name)
  const requirement = await call(
    request, 'post', `/equipment-requirements/events/${eventId}`, await as(request, COORD),
    { category: ITEM.category, quantity_needed: 2, technical_notes: 'Front of hall' }, 201,
  )
  return { eventId, requirementId: requirement.id as number }
}

test('TC-TN-1e: a recorded requirement names the Event, equipment, quantity and date, and opens the record', async ({ browser, request }) => {
  const { eventId } = await required(request, 'Required Summit')
  const tess = await openAs(browser, TESS)
  await tess.goto('/notifications')
  const row = notice(tess, "Equipment required for 'Required Summit'")
  await expect(row).toContainText(`2 x ${ITEM.category}. Notes: Front of hall`)
  await expect(row).toContainText(/\d{1,2} \w{3} \d{4}, 09:00-17:00 UTC/)
  await row.getByRole('link', { name: 'View event' }).click()
  await expect(tess).toHaveURL(new RegExp(`/equipment-requirements/${eventId}$`))
})

test('TC-TN-2e: a changed requirement says what changed', async ({ browser, request }) => {
  const { requirementId } = await required(request, 'Changed Summit')
  await call(request, 'patch', `/equipment-requirements/${requirementId}`, await as(request, COORD), { quantity_needed: 4 })
  const tess = await openAs(browser, TESS)
  await tess.goto('/notifications')
  await expect(notice(tess, "Equipment requirement changed for 'Changed Summit'")).toContainText('quantity 2 -> 4')
})

test('TC-TN-3e: a rescheduled Event gives the old and new date/time', async ({ browser, request }) => {
  const { eventId } = await required(request, 'Moved Summit')
  const change = await call(
    request, 'post', `/events/${eventId}/change-requests`, await as(request, ORG),
    { description: 'One day later', proposed_changes: { proposed_start: inDays(31), proposed_end: inDays(31, 17) } }, 201,
  )
  await call(request, 'post', `/events/change-requests/${change.id}/approve`, await as(request, COORD), {})
  const tess = await openAs(browser, TESS)
  await tess.goto('/notifications')
  await expect(notice(tess, "'Moved Summit' has moved from")).toContainText(/from .+ UTC to .+ UTC/)
})

test('TC-TN-4e: every Technical Support Staff member is told, and nobody else', async ({ browser, request }) => {
  await required(request, 'Everyone Summit')
  const tom = await openAs(browser, TOM)
  await tom.goto('/notifications')
  await expect(notice(tom, "Equipment required for 'Everyone Summit'")).toBeVisible()
  for (const who of [ORG, COORD]) {
    const page = await openAs(browser, who)
    await page.goto('/notifications')
    await expect(page.getByText(/Equipment required for/)).toHaveCount(0)
  }
})

for (const colorScheme of ['light', 'dark'] as const) {
  test(`TC-TN-A1: the Technical Support Notifications page passes axe (${colorScheme})`, async ({ browser, request }) => {
    await required(request, `Axe Summit ${colorScheme}`)
    const tess = await openAs(browser, TESS, { colorScheme })
    await tess.goto('/notifications')
    await expect(notice(tess, `Axe Summit ${colorScheme}`)).toBeVisible()
    await expectNoSeriousViolations(tess, `notifications ${colorScheme}`)
  })
}

test('TC-TN-A2: the notice\'s View event link is keyboard-reachable with visible focus', async ({ browser, request }) => {
  const { eventId } = await required(request, 'Keyboard Summit')
  const tess = await openAs(browser, TESS)
  await tess.goto('/notifications')
  await tabToAndFollow(tess, notice(tess, 'Keyboard Summit').getByRole('link', { name: 'View event' }))
  await expect(tess).toHaveURL(new RegExp(`/equipment-requirements/${eventId}$`))
})
