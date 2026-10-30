import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { API, login, submitEvent } from './support/api'
import { openAs } from './support/coordinator-users'
import type { SeedUser } from './support/db'
import { assignEventTo, removeUsers, resetUsers, seedUsers } from './support/db'

/**
 * End-to-end coverage of "Notify the Event Organiser of their Event's
 * status, Venue Booking and equipment outcomes", plus its DoD accessibility
 * checks. Venue and equipment outcomes are proven in the backend suites;
 * here the Organiser reads what reached them, in the browser.
 *
 *   TC-ON-1e -- AC1/AC3, a status change shows in the Organiser's Notifications after logging in
 *   TC-ON-2e -- AC1, the Coordinator's approval reaches the Organiser
 *   TC-ON-3e -- AC2/AC6, another Organiser is not sent it
 *   TC-ON-A1 -- DoD 8, axe on the Organiser's Notifications page (light, dark)
 *   TC-ON-A2 -- DoD 8, keyboard: the notice's "View event" link is reachable, visible focus
 */
const PASSWORD = 'e2e-org-notice-123'
const ORG: SeedUser = { email: 'e2e_on_org@cs.local', name: 'Olivia Organiser', role: 'organiser', password: PASSWORD }
const OTHER: SeedUser = { email: 'e2e_on_other@cs.local', name: 'Otto Other', role: 'organiser', password: PASSWORD }
const SAM: SeedUser = { email: 'e2e_on_sam@cs.local', name: 'Sam Tan', role: 'coordinator', password: PASSWORD }
const EMAILS = [ORG.email, OTHER.email, SAM.email]

test.beforeAll(() => seedUsers([ORG, OTHER, SAM]))
test.beforeEach(() => resetUsers(EMAILS))
test.afterAll(() => removeUsers(EMAILS))

const orgHeaders = (request: Parameters<typeof login>[0]) => login(request, ORG.email, ORG.password)

async function expectNoSeriousViolations(page: Page, label: string) {
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))))
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  const blocking = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  expect(blocking.map((v) => `${v.impact} ${v.id}: ${v.help}`).join('\n'), label).toBe('')
}

test('TC-ON-1e: a status change shows in the Organiser\'s Notifications after logging in', async ({ browser, request }) => {
  await submitEvent(request, await orgHeaders(request), 'Status Summit', { assign: false })
  const org = await openAs(browser, ORG)
  await org.goto('/notifications')
  const row = org.locator('.notif-row').filter({ hasText: "Your event 'Status Summit' is now Submitted – Awaiting Coordinator." })
  await expect(row).toBeVisible()
  await expect(row.getByRole('link', { name: 'View event' })).toHaveAttribute('href', /\/organiser\/events\/\d+/)
})

test('TC-ON-2e: the Coordinator\'s approval reaches the Organiser', async ({ browser, request }) => {
  const id = await submitEvent(request, await orgHeaders(request), 'Approved Summit', { assign: false })
  assignEventTo(id, SAM.email)
  const approved = await request.post(`${API}/events/${id}/approve`, { headers: await login(request, SAM.email, SAM.password) })
  expect(approved.ok(), await approved.text()).toBe(true)
  const org = await openAs(browser, ORG)
  await org.goto('/notifications')
  await expect(org.locator('.notif-row').filter({ hasText: "Your event 'Approved Summit' has been approved." })).toBeVisible()
})

test('TC-ON-3e: another Organiser is not sent it', async ({ browser, request }) => {
  await submitEvent(request, await orgHeaders(request), 'Private Summit', { assign: false })
  const other = await openAs(browser, OTHER)
  await other.goto('/notifications')
  await expect(other.getByText('Private Summit')).toHaveCount(0)
})

for (const colorScheme of ['light', 'dark'] as const) {
  test(`TC-ON-A1: the Organiser's Notifications page passes axe (${colorScheme})`, async ({ browser, request }) => {
    await submitEvent(request, await orgHeaders(request), 'Axe Summit', { assign: false })
    const org = await openAs(browser, ORG, { colorScheme })
    await org.goto('/notifications')
    await expect(org.getByText(/Axe Summit/)).toBeVisible()
    await expectNoSeriousViolations(org, `notifications ${colorScheme}`)
  })
}

test('TC-ON-A2: the notice\'s View event link is keyboard-reachable with visible focus', async ({ browser, request }) => {
  await submitEvent(request, await orgHeaders(request), 'Keyboard Summit', { assign: false })
  const org = await openAs(browser, ORG)
  await org.goto('/notifications')
  const link = org.locator('.notif-row').filter({ hasText: 'Keyboard Summit' }).getByRole('link', { name: 'View event' })
  await expect(link).toBeVisible()
  let reached = false
  for (let i = 0; i < 25 && !reached; i++) {
    await org.keyboard.press('Tab')
    reached = await link.evaluate((el) => el === document.activeElement)
  }
  expect(reached, 'View event link not reachable by Tab').toBe(true)
  const visible = await link.evaluate((el) => {
    const s = getComputedStyle(el)
    return (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0) || s.boxShadow !== 'none'
  })
  expect(visible, 'no visible focus on View event').toBe(true)
  await org.keyboard.press('Enter')
  await expect(org).toHaveURL(/\/organiser\/events\/\d+/)
})
