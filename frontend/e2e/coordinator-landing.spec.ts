import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { login, submitEvent } from './support/api'
import { openAs } from './support/coordinator-users'
import type { SeedUser } from './support/db'
import { addNotifications, assignEventTo, removeUsers, resetUsers, seedUsers } from './support/db'

/**
 * End-to-end coverage of the Event Coordinator landing-page story, plus its
 * Definition of Done accessibility checks (section 8).
 *
 * Traceability:
 *   TC-CL-1e -- AC1, login lands on the Coordinator page, welcome by name + role
 *   TC-CL-2e -- AC2, each shortcut opens its feature
 *   TC-CL-3e -- AC3, assigned events and unread notifications are counted
 *   TC-CL-4e -- AC4, with none, no number is shown
 *   TC-CL-A1 -- DoD 8, axe: no serious/critical violations (light, dark)
 *   TC-CL-A2 -- DoD 8, keyboard: shortcuts reachable with visible focus
 *
 * Events are handed to a named Coordinator, never to "whoever is least
 * loaded", so the counts below do not depend on who else is in the database.
 */
const PASSWORD = 'e2e-coord-landing-123'
const COORD: SeedUser = { email: 'e2e_cl_coord@cs.local', name: 'Sam Tan', role: 'coordinator', password: PASSWORD }
const OTHER: SeedUser = { email: 'e2e_cl_other@cs.local', name: 'Priya Nair', role: 'coordinator', password: PASSWORD }
const ORG: SeedUser = { email: 'e2e_cl_org@cs.local', name: 'Olivia Organiser', role: 'organiser', password: PASSWORD }
const EMAILS = [COORD.email, OTHER.email, ORG.email]

test.beforeAll(() => seedUsers([COORD, OTHER, ORG]))
test.beforeEach(() => resetUsers(EMAILS))
test.afterAll(() => removeUsers(EMAILS))

// Scoped to the tile grid: the navbar bell is also a link named "Notifications".
const tile = (page: Page, name: RegExp) => page.locator('.tile-grid').getByRole('link', { name })

/** Submit `count` events and hand them to `to` (the Lead's job in the app). */
async function assignedEvents(request: Parameters<typeof login>[0], to: SeedUser, count: number) {
  const headers = await login(request, ORG.email, ORG.password)
  for (let i = 0; i < count; i++) {
    const id = await submitEvent(request, headers, `${to.name} event ${i + 1}`, { assign: false })
    assignEventTo(id, to.email)
  }
}

async function expectNoSeriousViolations(page: Page, label: string) {
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))))
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  const blocking = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  expect(blocking.map((v) => `${v.impact} ${v.id}: ${v.help}`).join('\n'), label).toBe('')
}

test('TC-CL-1e: login lands on the Coordinator page and welcomes them by name and role', async ({ browser }) => {
  const page = await openAs(browser, COORD)
  await expect(page).toHaveURL(/\/coordinator$/)
  await expect(page.getByRole('heading', { level: 1, name: 'Welcome back, Sam Tan' })).toBeVisible()
  await expect(page.getByText('Event Coordinator').first()).toBeVisible()
})

test('TC-CL-4e: with nothing assigned and nothing unread, no number is shown', async ({ browser }) => {
  const page = await openAs(browser, COORD)
  await expect(tile(page, /My Assigned Events/)).toBeVisible()
  await expect(tile(page, /Notifications/)).toBeVisible()
  await expect(page.locator('.tile-count')).toHaveCount(0)
})

test('TC-CL-3e: assigned events and unread notifications are counted', async ({ browser, request }) => {
  await assignedEvents(request, COORD, 2)
  await assignedEvents(request, OTHER, 3) // never counted for Sam
  addNotifications(COORD.email, 4)
  const page = await openAs(browser, COORD)
  await expect(tile(page, /My Assigned Events/).locator('.tile-count')).toHaveText('2')
  await expect(tile(page, /Notifications/).locator('.tile-count')).toHaveText('4')
})

test('TC-CL-2e: the My Assigned Events shortcut opens the events assigned to them', async ({ browser, request }) => {
  await assignedEvents(request, COORD, 1)
  const page = await openAs(browser, COORD)
  await tile(page, /My Assigned Events/).click()
  await expect(page).toHaveURL(/\/coordinator\/events$/)
  await expect(page.getByText('Sam Tan event 1')).toBeVisible()
})

test('TC-CL-2e: the Venues, Notifications and My Profile shortcuts open their pages', async ({ browser }) => {
  const page = await openAs(browser, COORD)
  await tile(page, /Venues/).click()
  await expect(page).toHaveURL(/\/venues$/)
  await page.goBack()
  await tile(page, /Notifications/).click()
  await expect(page).toHaveURL(/\/notifications$/)
  await page.goBack()
  await tile(page, /My Profile/).click()
  await expect(page).toHaveURL(/\/profile$/)
})

test('TC-CL-A2: the shortcuts are reachable by keyboard with visible focus', async ({ browser }) => {
  const page = await openAs(browser, COORD)
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
  for (const name of ['My Assigned Events', 'Venues', 'Notifications', 'My Profile']) {
    expect([...focused].some((t) => t.includes(name)), `${name} not reachable by Tab`).toBe(true)
  }
})

for (const colorScheme of ['light', 'dark'] as const) {
  test(`TC-CL-A1: Coordinator landing page passes axe with counts showing (${colorScheme})`, async ({ browser, request }) => {
    await assignedEvents(request, COORD, 1)
    addNotifications(COORD.email, 2)
    const page = await openAs(browser, COORD, { colorScheme })
    await expect(tile(page, /My Assigned Events/).locator('.tile-count')).toHaveText('1')
    await expect(tile(page, /Notifications/).locator('.tile-count')).toHaveText('2')
    await expectNoSeriousViolations(page, `landing ${colorScheme}`)
  })
}
