import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { API, login, submitEvent, userId } from './support/api'
import { openAs } from './support/coordinator-users'
import type { SeedUser } from './support/db'
import { assignEventTo, removeUsers, resetUsers, seedUsers } from './support/db'

/**
 * End-to-end coverage of "Notify the Event Coordinator about the Events they
 * are responsible for", plus its DoD accessibility checks. Venue and
 * equipment outcomes, and reassignment, are proven in the backend suites;
 * here the Coordinator reads what reached them, in the browser.
 *
 *   TC-CN-1e -- AC1, the Lead's assignment names the Event and its Organiser
 *   TC-CN-2e -- AC6, a submitted change request reaches the Coordinator
 *   TC-CN-3e -- AC7, another Coordinator is not sent it
 *   TC-CN-A1 -- DoD 8, axe on the Coordinator's Notifications page (light, dark)
 *   TC-CN-A2 -- DoD 8, keyboard: the notice's "View event" link is reachable, visible focus
 */
const PASSWORD = 'e2e-coord-notice-123'
const ORG: SeedUser = { email: 'e2e_cn_org@cs.local', name: 'Olivia Organiser', role: 'organiser', password: PASSWORD }
const SAM: SeedUser = { email: 'e2e_cn_sam@cs.local', name: 'Sam Tan', role: 'coordinator', password: PASSWORD }
const PRIYA: SeedUser = { email: 'e2e_cn_priya@cs.local', name: 'Priya Nair', role: 'coordinator', password: PASSWORD }
const LEAD: SeedUser = { email: 'e2e_cn_lead@cs.local', name: 'Lena Lead', role: 'event_coordinator_lead', password: PASSWORD }
const EMAILS = [ORG.email, SAM.email, PRIYA.email, LEAD.email]

test.beforeAll(() => seedUsers([ORG, SAM, PRIYA, LEAD]))
test.beforeEach(() => resetUsers(EMAILS))
test.afterAll(() => removeUsers(EMAILS))

type Request = Parameters<typeof login>[0]
const as = (request: Request, who: SeedUser) => login(request, who.email, who.password)

/** An Event of Olivia's, assigned to Sam, with a change request on it. */
async function changeRequested(request: Request, name: string) {
  const id = await submitEvent(request, await as(request, ORG), name, { assign: false })
  assignEventTo(id, SAM.email)
  const res = await request.post(`${API}/events/${id}/change-requests`, {
    data: { description: 'A bigger room, please', proposed_changes: { expected_attendance: 150 } },
    headers: await as(request, ORG),
  })
  expect(res.status(), await res.text()).toBe(201)
  return id
}

async function expectNoSeriousViolations(page: Page, label: string) {
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))))
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  const blocking = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  expect(blocking.map((v) => `${v.impact} ${v.id}: ${v.help}`).join('\n'), label).toBe('')
}

test('TC-CN-1e: the Lead\'s assignment names the Event and its Organiser', async ({ browser, request }) => {
  const id = await submitEvent(request, await as(request, ORG), 'Assigned Summit', { assign: false })
  const res = await request.post(`${API}/lead/unassigned-queue/${id}/assign`, {
    data: { coordinator_id: await userId(request, await as(request, SAM)) },
    headers: await as(request, LEAD),
  })
  expect(res.ok(), await res.text()).toBe(true)
  const sam = await openAs(browser, SAM)
  await sam.goto('/notifications')
  await expect(
    sam.locator('.notif-row').filter({ hasText: "You have been assigned to coordinate 'Assigned Summit' for Olivia Organiser (Event Organiser)." }),
  ).toBeVisible()
})

test('TC-CN-2e: a submitted change request reaches the Coordinator', async ({ browser, request }) => {
  await changeRequested(request, 'Change Summit')
  const sam = await openAs(browser, SAM)
  await sam.goto('/notifications')
  const row = sam.locator('.notif-row').filter({ hasText: "Olivia Organiser submitted a change request for 'Change Summit': A bigger room, please" })
  await expect(row).toBeVisible()
  await expect(row.getByRole('link', { name: 'View event' })).toHaveAttribute('href', /\/coordinator\/events\/\d+/)
})

test('TC-CN-3e: another Coordinator is not sent it', async ({ browser, request }) => {
  await changeRequested(request, 'Not Priyas Summit')
  const priya = await openAs(browser, PRIYA)
  await priya.goto('/notifications')
  await expect(priya.getByText('Not Priyas Summit')).toHaveCount(0)
})

for (const colorScheme of ['light', 'dark'] as const) {
  test(`TC-CN-A1: the Coordinator's Notifications page passes axe (${colorScheme})`, async ({ browser, request }) => {
    await changeRequested(request, 'Axe Summit')
    const sam = await openAs(browser, SAM, { colorScheme })
    await sam.goto('/notifications')
    await expect(sam.getByText(/submitted a change request for 'Axe Summit'/)).toBeVisible()
    await expectNoSeriousViolations(sam, `notifications ${colorScheme}`)
  })
}

test('TC-CN-A2: the notice\'s View event link is keyboard-reachable with visible focus', async ({ browser, request }) => {
  await changeRequested(request, 'Keyboard Summit')
  const sam = await openAs(browser, SAM)
  await sam.goto('/notifications')
  const link = sam
    .locator('.notif-row')
    .filter({ hasText: "submitted a change request for 'Keyboard Summit'" })
    .getByRole('link', { name: 'View event' })
  await expect(link).toBeVisible()
  let reached = false
  for (let i = 0; i < 25 && !reached; i++) {
    await sam.keyboard.press('Tab')
    reached = await link.evaluate((el) => el === document.activeElement)
  }
  expect(reached, 'View event link not reachable by Tab').toBe(true)
  const visible = await link.evaluate((el) => {
    const s = getComputedStyle(el)
    return (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0) || s.boxShadow !== 'none'
  })
  expect(visible, 'no visible focus on View event').toBe(true)
  await sam.keyboard.press('Enter')
  await expect(sam).toHaveURL(/\/coordinator\/events\/\d+/)
})
