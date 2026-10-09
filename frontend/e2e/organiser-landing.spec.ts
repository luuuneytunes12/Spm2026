import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { API, login } from './support/api'
import { openAs } from './support/coordinator-users'
import type { SeedUser } from './support/db'
import { addNotifications, removeUsers, resetUsers, seedUsers } from './support/db'

/**
 * End-to-end coverage of the Event Organiser landing-page story, plus its
 * Definition of Done accessibility checks (section 8).
 *
 * Traceability:
 *   TC-OL-1e -- AC1, login lands on the Organiser page, welcome by name + role
 *   TC-OL-2e -- AC2, each shortcut opens its feature
 *   TC-OL-3e -- AC3, drafts, submitted requests and unread notifications are counted
 *   TC-OL-4e -- AC4, with none, no number is shown
 *   TC-OL-A1 -- DoD 8, axe: no serious/critical violations (light, dark)
 *   TC-OL-A2 -- DoD 8, keyboard: shortcuts reachable with visible focus
 */
const PASSWORD = 'e2e-org-landing-123'
const ORG: SeedUser = { email: 'e2e_ol_org@cs.local', name: 'Olivia Organiser', role: 'organiser', password: PASSWORD }
const OTHER: SeedUser = { email: 'e2e_ol_other@cs.local', name: 'Otto Other', role: 'organiser', password: PASSWORD }
const EMAILS = [ORG.email, OTHER.email]

test.beforeAll(() => seedUsers([ORG, OTHER]))
test.beforeEach(() => resetUsers(EMAILS))
test.afterAll(() => removeUsers(EMAILS))

// Scoped to the tile grid: the navbar bell is also a link named "Notifications".
const tile = (page: Page, name: RegExp) => page.locator('.tile-grid').getByRole('link', { name })

const REQUEST = {
  purpose: 'Annual partner briefing',
  event_type: 'conference',
  description: 'A full-day briefing.',
  proposed_start: '2026-11-02T09:00:00Z',
  proposed_end: '2026-11-02T17:00:00Z',
  expected_attendance: 120,
  venue_requirements: 'Main hall',
  accessibility_needs: 'Step-free access',
  equipment_requirements: '2 projectors',
  registration_enabled: true,
}

/** Create `drafts` drafts and `submitted` submitted requests for `who`. */
async function seedRequests(
  request: Parameters<typeof login>[0],
  who: SeedUser,
  { drafts, submitted }: { drafts: number; submitted: number },
) {
  const headers = await login(request, who.email, who.password)
  for (let i = 0; i < drafts + submitted; i++) {
    const created = await request.post(`${API}/events`, { data: { ...REQUEST, name: `${who.name} request ${i + 1}` }, headers })
    expect(created.ok()).toBe(true)
    if (i >= drafts) {
      const { id } = await created.json()
      expect((await request.post(`${API}/events/${id}/submit`, { headers })).ok()).toBe(true)
    }
  }
}

async function expectNoSeriousViolations(page: Page, label: string) {
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))))
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  const blocking = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  expect(blocking.map((v) => `${v.impact} ${v.id}: ${v.help}`).join('\n'), label).toBe('')
}

test('TC-OL-1e: login lands on the Organiser page and welcomes them by name and role', async ({ browser }) => {
  const page = await openAs(browser, ORG)
  await expect(page).toHaveURL(/\/organiser$/)
  await expect(page.getByRole('heading', { level: 1, name: 'Welcome back, Olivia Organiser' })).toBeVisible()
  await expect(page.getByText('Event Organiser').first()).toBeVisible()
})

test('TC-OL-4e: with no requests and nothing unread, no number is shown', async ({ browser }) => {
  const page = await openAs(browser, ORG)
  await expect(tile(page, /Drafted Requests/)).toBeVisible()
  await expect(tile(page, /Submitted Requests/)).toBeVisible()
  await expect(tile(page, /Notifications/)).toBeVisible()
  await expect(page.locator('.tile-count')).toHaveCount(0)
})

test('TC-OL-3e: drafts, submitted requests and unread notifications are counted', async ({ browser, request }) => {
  await seedRequests(request, ORG, { drafts: 2, submitted: 3 })
  await seedRequests(request, OTHER, { drafts: 4, submitted: 1 }) // never counted for Olivia
  addNotifications(ORG.email, 5)
  const page = await openAs(browser, ORG)
  await expect(tile(page, /Drafted Requests/).locator('.tile-count')).toHaveText('2')
  await expect(tile(page, /Submitted Requests/).locator('.tile-count')).toHaveText('3')
  await expect(tile(page, /Notifications/).locator('.tile-count')).toHaveText('5')
})

test('TC-OL-2e: New Event Request, Drafted Requests and Submitted Requests open their features', async ({ browser, request }) => {
  await seedRequests(request, ORG, { drafts: 1, submitted: 1 })
  const page = await openAs(browser, ORG)

  await tile(page, /New Event Request/).click()
  await expect(page).toHaveURL(/\/organiser\/events\/new$/)
  await page.goBack()

  await tile(page, /Drafted Requests/).click()
  await expect(page).toHaveURL(/\/organiser\/events$/)
  await expect(page.getByRole('tab', { name: 'Drafts', selected: true })).toBeVisible()
  await page.goBack()

  await tile(page, /Submitted Requests/).click()
  await expect(page).toHaveURL(/\/organiser\/events\?tab=submitted$/)
  await expect(page.getByRole('tab', { name: 'Submitted Requests', selected: true })).toBeVisible()
})

test('TC-OL-2e: the Notifications and My Profile shortcuts open their pages', async ({ browser }) => {
  const page = await openAs(browser, ORG)
  await tile(page, /Notifications/).click()
  await expect(page).toHaveURL(/\/notifications$/)
  await page.goBack()
  await tile(page, /My Profile/).click()
  await expect(page).toHaveURL(/\/profile$/)
})

test('TC-OL-A2: the shortcuts are reachable by keyboard with visible focus', async ({ browser }) => {
  const page = await openAs(browser, ORG)
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
  for (const name of ['New Event Request', 'Drafted Requests', 'Submitted Requests', 'Notifications', 'My Profile']) {
    expect([...focused].some((t) => t.includes(name)), `${name} not reachable by Tab`).toBe(true)
  }
})

for (const colorScheme of ['light', 'dark'] as const) {
  test(`TC-OL-A1: Organiser landing page passes axe with counts showing (${colorScheme})`, async ({ browser, request }) => {
    await seedRequests(request, ORG, { drafts: 1, submitted: 1 })
    addNotifications(ORG.email, 2)
    const page = await openAs(browser, ORG, { colorScheme })
    await expect(tile(page, /Drafted Requests/).locator('.tile-count')).toHaveText('1')
    await expect(tile(page, /Notifications/).locator('.tile-count')).toHaveText('2')
    await expectNoSeriousViolations(page, `landing ${colorScheme}`)
  })
}
