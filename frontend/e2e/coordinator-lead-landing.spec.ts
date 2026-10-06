import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { login, submitEvent } from './support/api'
import { openAs } from './support/coordinator-users'
import type { SeedUser } from './support/db'
import { removeUsers, resetUsers, seedUsers } from './support/db'

/**
 * End-to-end coverage of the Event Coordinator Lead landing-page story, plus
 * its Definition of Done accessibility checks (section 8).
 *
 * Traceability (docs/test-cases-coordinator-lead-landing.md):
 *   TC-CLL-1e -- AC1, login lands on the Lead page, welcome by full name + role
 *   TC-CLL-2e -- AC2, each shortcut opens its feature
 *   TC-CLL-3e -- AC3, unassigned requests and unread notifications show a count
 *   TC-CLL-4e -- AC4, with none, no number is shown
 *   TC-CLL-A1 -- DoD 8, axe: no serious/critical violations (light, dark)
 *   TC-CLL-A2 -- DoD 8, keyboard: shortcuts reachable with visible focus
 *
 * The Lead and Organiser are seeded first; the Coordinator only in the second
 * block, so that in the first block a submitted request stays unassigned.
 */
const PASSWORD = 'e2e-lead-landing-123'
const LEAD: SeedUser = { email: 'e2e_cll_lead@cs.local', name: 'Lena Marie Lead', role: 'event_coordinator_lead', password: PASSWORD }
const ORG: SeedUser = { email: 'e2e_cll_org@cs.local', name: 'Olivia Organiser', role: 'organiser', password: PASSWORD }
const COORD: SeedUser = { email: 'e2e_cll_coord@cs.local', name: 'Sam Tan', role: 'coordinator', password: PASSWORD }
const EMAILS = [LEAD.email, ORG.email, COORD.email]

test.beforeAll(() => seedUsers([LEAD, ORG]))
test.beforeEach(() => resetUsers(EMAILS))
test.afterAll(() => removeUsers(EMAILS))

// Scoped to the tile grid: the navbar bell is also a link named "Notifications".
const tile = (page: Page, name: RegExp) => page.locator('.tile-grid').getByRole('link', { name })

async function submitAsOrganiser(request: Parameters<typeof login>[0], name: string, assign = false) {
  return submitEvent(request, await login(request, ORG.email, ORG.password), name, { assign })
}

async function expectNoSeriousViolations(page: Page, label: string) {
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))))
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  const blocking = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  expect(blocking.map((v) => `${v.impact} ${v.id}: ${v.help}`).join('\n'), label).toBe('')
}

test('TC-CLL-1e: login lands on the Lead page and welcomes them by full name and role', async ({ browser }) => {
  const page = await openAs(browser, LEAD)
  await expect(page).toHaveURL(/\/coordinator-lead$/)
  await expect(page.getByRole('heading', { level: 1, name: 'Welcome back, Lena Marie Lead' })).toBeVisible()
  await expect(page.getByText('Event Coordinator Lead').first()).toBeVisible()
})

test('TC-CLL-4e: with nothing unassigned and nothing unread, no number is shown', async ({ browser }) => {
  const page = await openAs(browser, LEAD)
  await expect(tile(page, /Unassigned Requests/)).toBeVisible()
  await expect(tile(page, /Notifications/)).toBeVisible()
  await expect(page.locator('.tile-count')).toHaveCount(0)
})

test('TC-CLL-3e: unassigned requests are counted on their shortcut', async ({ browser, request }) => {
  await submitAsOrganiser(request, 'First unassigned')
  await submitAsOrganiser(request, 'Second unassigned')
  const page = await openAs(browser, LEAD)
  await expect(tile(page, /Unassigned Requests/).locator('.tile-count')).toHaveText('2')
})

test('TC-CLL-2e: the Unassigned Requests shortcut opens the unassigned requests', async ({ browser, request }) => {
  await submitAsOrganiser(request, 'Needs a coordinator')
  const page = await openAs(browser, LEAD)
  await tile(page, /Unassigned Requests/).click()
  await expect(page).toHaveURL(/\/coordinator-lead\/queue$/)
  await expect(page.getByText('Needs a coordinator')).toBeVisible()
  await expect(page.getByText(/not yet assigned/)).toBeVisible()
})

test('TC-CLL-2e: the Notifications and My Profile shortcuts open their pages', async ({ browser }) => {
  const page = await openAs(browser, LEAD)
  await tile(page, /Notifications/).click()
  await expect(page).toHaveURL(/\/notifications$/)
  await page.goBack()
  await tile(page, /My Profile/).click()
  await expect(page).toHaveURL(/\/profile$/)
})

test('TC-CLL-A2: the shortcuts are reachable by keyboard with visible focus', async ({ browser }) => {
  const page = await openAs(browser, LEAD)
  const focused = new Set<string>()
  for (let i = 0; i < 14; i++) {
    await page.keyboard.press('Tab')
    const info = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null
      if (!el || el === document.body) return null
      const s = getComputedStyle(el)
      const visible = (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0) || s.boxShadow !== 'none'
      return { text: el.textContent?.trim() ?? '', visible }
    })
    if (info) {
      expect(info.visible, `no visible focus on "${info.text}"`).toBe(true)
      focused.add(info.text)
    }
  }
  for (const name of ['Unassigned Requests', 'Coordinator Assignments', 'Notifications', 'My Profile']) {
    expect([...focused].some((t) => t.includes(name)), `${name} not reachable by Tab`).toBe(true)
  }
})

for (const colorScheme of ['light', 'dark'] as const) {
  test(`TC-CLL-A1: Lead landing page and its two lists pass axe (${colorScheme})`, async ({ browser, request }) => {
    await submitAsOrganiser(request, 'Axe unassigned')
    const page = await openAs(browser, LEAD, { colorScheme })
    await expect(page.getByRole('heading', { level: 1, name: /Welcome back/ })).toBeVisible()
    await expect(tile(page, /Unassigned Requests/).locator('.tile-count')).toHaveText('1')
    await expectNoSeriousViolations(page, `landing ${colorScheme}`)
    await page.goto('/coordinator-lead/queue')
    await expect(page.getByText('Axe unassigned')).toBeVisible()
    await expectNoSeriousViolations(page, `unassigned ${colorScheme}`)
    await page.goto('/coordinator-lead/assignments')
    await expect(page.getByRole('heading', { level: 1, name: 'Coordinator Assignments' })).toBeVisible()
    await expectNoSeriousViolations(page, `assignments ${colorScheme}`)
  })
}

test.describe('with a Coordinator in the pool', () => {
  test.beforeAll(() => seedUsers([COORD]))

  test('TC-CLL-2e: the Coordinator Assignments shortcut shows who holds each event', async ({ browser, request }) => {
    await submitAsOrganiser(request, 'Held by Sam', true)
    const page = await openAs(browser, LEAD)
    await expect(tile(page, /Unassigned Requests/).locator('.tile-count')).toHaveCount(0) // assigned, so nothing unassigned
    await tile(page, /Coordinator Assignments/).click()
    await expect(page).toHaveURL(/\/coordinator-lead\/assignments$/)
    await expect(page.getByText('Held by Sam')).toBeVisible()
    await expect(page.getByText(/Coordinator: Sam Tan/)).toBeVisible()
  })
})
