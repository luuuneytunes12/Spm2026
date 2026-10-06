import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { API, login, submitEvent } from './support/api'
import { openAs } from './support/coordinator-users'
import type { SeedUser } from './support/db'
import { removeUsers, resetUsers, seedUsers } from './support/db'

/**
 * End-to-end coverage of SCRUM-82, "View All Coordinator Assignments & Active
 * Events as Coordinator Lead", plus its DoD accessibility checks (section 8).
 *
 *   TC-CA-1e -- AC1, active Events listed with name, Coordinator and status
 *   TC-CA-2e -- AC2, filtering by a Coordinator shows only theirs and how many
 *   TC-CA-3e -- AC3, opening one shows it in full, read-only
 *   TC-CA-4e -- AC4, other roles are denied (screen and direct request)
 *   TC-CA-A1 -- DoD 8, axe: no serious/critical violations (light, dark)
 *   TC-CA-A2 -- DoD 8, keyboard: filter and Review links reachable, visible focus
 *
 * Sam is seeded before Priya, and submitEvent hands each Event to the
 * least-loaded Coordinator (ties to Sam), so the three Events below land on
 * Sam, Priya, Sam -- see support/db.ts autoAssign.
 */
const PASSWORD = 'e2e-assign-password-123'
const LEAD: SeedUser = { email: 'e2e_ca_lead@cs.local', name: 'Lena Marie Lead', role: 'event_coordinator_lead', password: PASSWORD }
const ORG: SeedUser = { email: 'e2e_ca_org@cs.local', name: 'Olivia Organiser', role: 'organiser', password: PASSWORD }
const SAM: SeedUser = { email: 'e2e_ca_sam@cs.local', name: 'Sam Tan', role: 'coordinator', password: PASSWORD }
const PRIYA: SeedUser = { email: 'e2e_ca_priya@cs.local', name: 'Priya Nair', role: 'coordinator', password: PASSWORD }
const EMAILS = [LEAD.email, ORG.email, SAM.email, PRIYA.email]

test.beforeAll(() => seedUsers([LEAD, ORG, SAM, PRIYA]))
test.beforeEach(() => resetUsers(EMAILS))
test.afterAll(() => removeUsers(EMAILS))

const OVERVIEW = '/coordinator-lead/assignments'

async function submit(request: Parameters<typeof login>[0], name: string, assign = true) {
  return submitEvent(request, await login(request, ORG.email, ORG.password), name, { assign })
}

/** Three active Events: Sam, Priya, Sam. Returns their ids. */
async function threeEvents(request: Parameters<typeof login>[0]) {
  return [await submit(request, 'Sam one'), await submit(request, 'Priya one'), await submit(request, 'Sam two')]
}

async function expectNoSeriousViolations(page: Page, label: string) {
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))))
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  const blocking = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  expect(blocking.map((v) => `${v.impact} ${v.id}: ${v.help}`).join('\n'), label).toBe('')
}

test('TC-CA-1e: active Events are listed with name, Coordinator and status; unassigned ones are not', async ({ browser, request }) => {
  await threeEvents(request)
  await submit(request, 'Still in the queue', false)
  const lead = await openAs(browser, LEAD)
  await lead.goto(OVERVIEW)
  await expect(lead.locator('.request')).toHaveCount(3)
  const sam = lead.locator('.request').filter({ hasText: 'Sam one' })
  await expect(sam).toContainText('Coordinator: Sam Tan')
  await expect(sam).toContainText('Under Review')
  await expect(lead.locator('.request').filter({ hasText: 'Priya one' })).toContainText('Coordinator: Priya Nair')
  await expect(lead.getByText('Still in the queue')).toHaveCount(0)
  await expect(lead.getByText('3 active Events')).toBeVisible()
})

test('TC-CA-2e: filtering by a Coordinator shows only their Events and how many', async ({ browser, request }) => {
  await threeEvents(request)
  const lead = await openAs(browser, LEAD)
  await lead.goto(OVERVIEW)
  await expect(lead.getByRole('option', { name: 'Sam Tan (2)' })).toBeAttached()
  await expect(lead.getByRole('option', { name: 'Priya Nair (1)' })).toBeAttached()

  await lead.getByLabel('Filter by Coordinator').selectOption({ label: 'Sam Tan (2)' })
  await expect(lead.getByText('2 active Events')).toBeVisible()
  await expect(lead.locator('.request')).toHaveCount(2)
  await expect(lead.getByText('Priya one')).toHaveCount(0)

  await lead.getByLabel('Filter by Coordinator').selectOption({ label: 'Priya Nair (1)' })
  await expect(lead.getByText('1 active Event')).toBeVisible()
  await expect(lead.locator('.request')).toHaveCount(1)

  await lead.getByLabel('Filter by Coordinator').selectOption({ label: 'All Coordinators' })
  await expect(lead.getByText('3 active Events')).toBeVisible()
})

test('TC-CA-3e: opening an Event shows it in full, read-only', async ({ browser, request }) => {
  await submit(request, 'Review me')
  const lead = await openAs(browser, LEAD)
  await lead.goto(OVERVIEW)
  await lead.getByRole('link', { name: /Review/ }).click()
  await expect(lead).toHaveURL(/\/coordinator-lead\/assignments\/\d+$/)
  await expect(lead.getByRole('heading', { level: 1, name: 'Review me' })).toBeVisible()
  for (const text of ['Annual partner briefing', 'A full-day briefing for our regional partners.', 'Main hall, stage, podium', 'Step-free access, hearing loop', '2 projectors, 4 radio mics', 'Olivia Organiser', ORG.email, 'Under Review']) {
    await expect(lead.getByText(text).first()).toBeVisible()
  }
  for (const label of ['Purpose', 'Description', 'Proposed date and time', 'Expected attendance', 'Venue requirements', 'Accessibility needs', 'Registration needed']) {
    await expect(lead.getByText(label, { exact: true })).toBeVisible()
  }
  // The Event's own fields are not editable: no text inputs. The only controls are
  // the reassign panel's one select and one button (SCRUM-81).
  await expect(lead.locator('main input, main textarea')).toHaveCount(0)
  await expect(lead.locator('main select')).toHaveCount(1)
  await expect(lead.locator('main button')).toHaveText(['Reassign'])
})

test('TC-CA-4e: other roles are denied on screen and by direct request', async ({ browser, request }) => {
  const [id] = await threeEvents(request)
  for (const user of [SAM, ORG]) {
    const page = await openAs(browser, user)
    await page.goto(OVERVIEW)
    await expect(page).toHaveURL(/\/forbidden/)
    await expect(page.getByText('Sam one')).toHaveCount(0)
    await page.goto(`${OVERVIEW}/${id}`)
    await expect(page).toHaveURL(/\/forbidden/)
  }
  const sam = await login(request, SAM.email, SAM.password)
  for (const path of ['/lead/assignments', `/lead/assignments/${id}`, '/lead/coordinators']) {
    const res = await request.get(`${API}${path}`, { headers: sam })
    expect(res.status(), path).toBe(403)
    expect(await res.text()).not.toContain('Sam one')
  }
})

for (const colorScheme of ['light', 'dark'] as const) {
  test(`TC-CA-A1: the overview and an Event pass axe (${colorScheme})`, async ({ browser, request }) => {
    const [id] = await threeEvents(request)
    const lead = await openAs(browser, LEAD, { colorScheme })
    await lead.goto(OVERVIEW)
    await expect(lead.getByText('Sam one')).toBeVisible()
    await expectNoSeriousViolations(lead, `overview ${colorScheme}`)
    await lead.getByLabel('Filter by Coordinator').selectOption({ label: 'Sam Tan (2)' })
    await expect(lead.getByText('2 active Events')).toBeVisible()
    await expectNoSeriousViolations(lead, `filtered ${colorScheme}`)
    await lead.goto(`${OVERVIEW}/${id}`)
    await expect(lead.getByRole('heading', { level: 1, name: 'Sam one' })).toBeVisible()
    await expectNoSeriousViolations(lead, `event ${colorScheme}`)
  })
}

test('TC-CA-A2: the filter and Review links are keyboard-reachable with visible focus', async ({ browser, request }) => {
  await threeEvents(request)
  const lead = await openAs(browser, LEAD)
  await lead.goto(OVERVIEW)
  await expect(lead.getByText('Sam one')).toBeVisible()
  const focused = new Set<string>()
  for (let i = 0; i < 16; i++) {
    await lead.keyboard.press('Tab')
    const info = await lead.evaluate(() => {
      const el = document.activeElement as HTMLElement | null
      if (!el || el === document.body) return null
      const s = getComputedStyle(el)
      const visible = (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0) || s.boxShadow !== 'none'
      return { text: (el.textContent ?? '').trim().slice(0, 40), tag: el.tagName, visible }
    })
    if (info) {
      expect(info.visible, `no visible focus on "${info.text}"`).toBe(true)
      focused.add(`${info.tag}:${info.text}`)
    }
  }
  expect([...focused].some((t) => t.startsWith('SELECT')), 'filter not reachable by Tab').toBe(true)
  expect([...focused].some((t) => t.includes('Review')), 'Review link not reachable by Tab').toBe(true)
})
