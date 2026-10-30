import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { API, login } from './support/api'
import { openAs } from './support/coordinator-users'
import type { SeedUser } from './support/db'
import { removeUsers, resetUsers, seedUsers } from './support/db'

/**
 * End-to-end coverage of SCRUM-19, "Record Department & Responsibilities",
 * plus its DoD accessibility checks (section 8).
 *
 *   TC-DR-1e -- AC1, only the listed departments can be chosen
 *   TC-DR-2e -- AC2, a saved department is visible to other internal users
 *   TC-DR-3e -- AC3, responsibilities are saved and shown on the profile
 *   TC-DR-4e -- AC4, a different department replaces the old one
 *   TC-DR-5e -- AC5, no department: save blocked and the field flagged
 *   TC-DR-6e -- AC6, someone else's profile cannot be changed
 *   TC-DR-7e -- non-staff: no Work section, no directory, API refuses
 *   TC-DR-A1 -- DoD 8, axe: no serious/critical violations (light, dark)
 *   TC-DR-A2 -- DoD 8, keyboard: fields reachable with visible focus
 */
const PASSWORD = 'e2e-dept-password-123'
const VENUE: SeedUser = { email: 'e2e_dr_venue@cs.local', name: 'Vera Venue', role: 'venue_staff', password: PASSWORD }
const COORD: SeedUser = { email: 'e2e_dr_coord@cs.local', name: 'Cora Coordinator', role: 'coordinator', password: PASSWORD }
// Never given a department by any test, so AC5 starts from "not selected".
const NEWBIE: SeedUser = { email: 'e2e_dr_newbie@cs.local', name: 'Nina Newbie', role: 'tech_support', password: PASSWORD }
const ORG: SeedUser = { email: 'e2e_dr_org@cs.local', name: 'Olivia Organiser', role: 'organiser', password: PASSWORD }
const EMAILS = [VENUE.email, COORD.email, NEWBIE.email, ORG.email]

test.beforeAll(() => seedUsers([VENUE, COORD, NEWBIE, ORG]))
test.beforeEach(() => resetUsers(EMAILS))
test.afterAll(() => removeUsers(EMAILS))

const DEPARTMENTS = ['Events Coordination', 'Venue Operations', 'Technical Support', 'Safety & Compliance']

async function expectNoSeriousViolations(page: Page, label: string) {
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))))
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  const blocking = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  expect(blocking.map((v) => `${v.impact} ${v.id}: ${v.help}`).join('\n'), label).toBe('')
}

async function save(page: Page) {
  await page.getByRole('button', { name: 'Save changes' }).click()
  await expect(page.getByText('Your profile has been updated.')).toBeVisible()
}

test('TC-DR-1e: only the listed departments can be chosen', async ({ browser }) => {
  const page = await openAs(browser, VENUE)
  await page.goto('/profile')
  await expect(page.locator('#department')).toBeVisible()
  const options = await page.locator('#department option').allTextContents()
  expect(options).toEqual(['Select a department', ...DEPARTMENTS])
  await expect(page.locator('#department')).toHaveJSProperty('tagName', 'SELECT')
})

test('TC-DR-2e: a saved department is visible to other internal users', async ({ browser }) => {
  const venue = await openAs(browser, VENUE)
  await venue.goto('/profile')
  await venue.getByLabel('Department').selectOption({ label: 'Venue Operations' })
  await save(venue)

  const coord = await openAs(browser, COORD)
  await coord.goto('/staff')
  await expect(coord.getByRole('heading', { level: 1, name: 'Staff directory' })).toBeVisible()
  const row = coord.getByRole('row').filter({ has: coord.getByRole('rowheader', { name: 'Vera Venue' }) })
  await expect(row).toContainText('Venue Operations')
})

test('TC-DR-3e: responsibilities are saved and still there after a reload', async ({ browser }) => {
  const text = `Approve venue bookings and manage setup ${Date.now()}`
  const page = await openAs(browser, VENUE)
  await page.goto('/profile')
  await page.getByLabel('Department').selectOption({ label: 'Venue Operations' })
  await page.getByLabel('Responsibilities').fill(text)
  await save(page)
  await page.reload()
  await expect(page.getByLabel('Responsibilities')).toHaveValue(text)
  await expect(page.getByLabel('Department')).toHaveValue('venue_operations')
})

test('TC-DR-4e: choosing a different department replaces the old one', async ({ browser }) => {
  const page = await openAs(browser, COORD)
  await page.goto('/profile')
  await page.getByLabel('Department').selectOption({ label: 'Events Coordination' })
  await save(page)
  await page.getByLabel('Department').selectOption({ label: 'Safety & Compliance' })
  await save(page)
  await page.reload()
  await expect(page.getByLabel('Department')).toHaveValue('safety_compliance')

  await page.goto('/staff')
  const row = page.getByRole('row').filter({ has: page.getByRole('rowheader', { name: 'Cora Coordinator' }) })
  await expect(row).toContainText('Safety & Compliance')
  await expect(row).not.toContainText('Events Coordination')
})

test('TC-DR-5e: with no department the save is blocked and the field is flagged', async ({ browser }) => {
  const page = await openAs(browser, NEWBIE)
  await page.goto('/profile')
  let patched = false
  page.on('request', (r) => {
    if (r.method() === 'PATCH' && r.url().includes('/users/me')) patched = true
  })
  await page.getByLabel('Responsibilities').fill('Keep the AV kit working')
  await page.getByRole('button', { name: 'Save changes' }).click()
  await expect(page.getByRole('alert').filter({ hasText: 'Select your department.' }).first()).toBeVisible()
  await expect(page.locator('#department')).toHaveAttribute('aria-invalid', 'true')
  await expect(page.getByText('Your profile has been updated.')).toHaveCount(0)
  expect(patched).toBe(false)
})

test('TC-DR-6e: another person\'s profile cannot be changed', async ({ request }) => {
  const venueH = await login(request, VENUE.email, PASSWORD)
  const coordH = await login(request, COORD.email, PASSWORD)
  const coordId = (await (await request.get(`${API}/auth/me`, { headers: coordH })).json()).user.id
  const before = (await (await request.get(`${API}/auth/me`, { headers: coordH })).json()).user

  for (const method of ['patch', 'put'] as const) {
    const res = await request[method](`${API}/users/${coordId}`, {
      headers: venueH,
      data: { department: 'venue_operations', responsibilities: 'hijacked' },
    })
    expect([404, 405]).toContain(res.status())
  }
  // An id in the body does not redirect the caller's own update to someone else.
  await request.patch(`${API}/users/me`, {
    headers: venueH,
    data: { id: coordId, department: 'venue_operations', responsibilities: 'mine' },
  })
  const after = (await (await request.get(`${API}/auth/me`, { headers: coordH })).json()).user
  expect(after.department).toBe(before.department)
  expect(after.responsibilities).toBe(before.responsibilities)
})

test('TC-DR-7e: an Organiser has no Work section, no directory, and the API refuses', async ({ browser, request }) => {
  const page = await openAs(browser, ORG)
  await page.goto('/profile')
  await expect(page.getByRole('heading', { level: 1, name: 'My profile' })).toBeVisible()
  await expect(page.getByLabel('Department')).toHaveCount(0)
  await expect(page.getByLabel('Responsibilities')).toHaveCount(0)
  await page.goto('/staff')
  await expect(page.getByRole('heading', { name: 'Staff directory' })).toHaveCount(0)

  const headers = await login(request, ORG.email, PASSWORD)
  expect((await request.get(`${API}/users/staff`, { headers })).status()).toBe(403)
  expect(
    (await request.patch(`${API}/users/me`, { headers, data: { department: 'venue_operations' } })).status(),
  ).toBe(403)
})

for (const colorScheme of ['light', 'dark'] as const) {
  test(`TC-DR-A1: the profile and the directory pass axe (${colorScheme})`, async ({ browser }) => {
    const page = await openAs(browser, VENUE, { colorScheme })
    await page.goto('/profile')
    await expect(page.getByLabel('Department')).toBeVisible()
    await expectNoSeriousViolations(page, `profile ${colorScheme}`)
    await page.getByLabel('Department').selectOption('')
    await page.getByRole('button', { name: 'Save changes' }).click()
    await expect(page.locator('#department')).toHaveAttribute('aria-invalid', 'true')
    await expectNoSeriousViolations(page, `profile with error ${colorScheme}`)
    await page.goto('/staff')
    await expect(page.getByRole('heading', { level: 1, name: 'Staff directory' })).toBeVisible()
    await expectNoSeriousViolations(page, `directory ${colorScheme}`)
  })
}

test('TC-DR-A2: Department and Responsibilities are keyboard-reachable with visible focus', async ({ browser }) => {
  const page = await openAs(browser, VENUE)
  await page.goto('/profile')
  await expect(page.getByLabel('Department')).toBeVisible()
  const focused = new Set<string>()
  for (let i = 0; i < 30; i++) {
    await page.keyboard.press('Tab')
    const info = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null
      if (!el || el === document.body) return null
      const s = getComputedStyle(el)
      const visible = (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0) || s.boxShadow !== 'none'
      return { id: el.id, tag: el.tagName, visible }
    })
    if (info) {
      expect(info.visible, `no visible focus on ${info.tag}#${info.id}`).toBe(true)
      focused.add(info.id)
    }
  }
  expect(focused.has('department'), 'Department not reachable by Tab').toBe(true)
  expect(focused.has('responsibilities'), 'Responsibilities not reachable by Tab').toBe(true)
})
