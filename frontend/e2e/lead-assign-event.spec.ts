import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { API, login, submitEvent } from './support/api'
import { openAs } from './support/coordinator-users'
import type { SeedUser } from './support/db'
import { removeUsers, resetUsers, seedUsers } from './support/db'

/**
 * End-to-end coverage of SCRUM-80, "Assign Event Request to an Event
 * Coordinator as Coordinator Lead", plus its DoD accessibility checks.
 *
 *   TC-LA-1e -- AC1, assigning leaves the queue, becomes Under Review, appears for the Coordinator
 *   TC-LA-2e -- AC2, the list shows each Coordinator with their active Events
 *   TC-LA-3e -- AC3, the Activity Log records the Lead, the Coordinator and the time
 *   TC-LA-4e -- AC4, another Coordinator cannot open or act on it
 *   TC-LA-5e -- AC5, an Event no longer in the queue is refused, assignment unchanged
 *   TC-LA-6e -- AC6, other roles are refused, request stays unassigned
 *   TC-LA-A1 -- DoD 8, axe (light, dark)    TC-LA-A2 -- DoD 8, keyboard and focus
 */
const PASSWORD = 'e2e-lead-assign-123'
const LEAD: SeedUser = { email: 'e2e_la_lead@cs.local', name: 'Lena Marie Lead', role: 'event_coordinator_lead', password: PASSWORD }
const ORG: SeedUser = { email: 'e2e_la_org@cs.local', name: 'Olivia Organiser', role: 'organiser', password: PASSWORD }
const SAM: SeedUser = { email: 'e2e_la_sam@cs.local', name: 'Sam Tan', role: 'coordinator', password: PASSWORD }
const PRIYA: SeedUser = { email: 'e2e_la_priya@cs.local', name: 'Priya Nair', role: 'coordinator', password: PASSWORD }
const EMAILS = [LEAD.email, ORG.email, SAM.email, PRIYA.email]

test.beforeAll(() => seedUsers([LEAD, ORG, SAM, PRIYA]))
test.beforeEach(() => resetUsers(EMAILS))
test.afterAll(() => removeUsers(EMAILS))

const queued = async (request: Parameters<typeof login>[0], name = 'Needs an owner') =>
  submitEvent(request, await login(request, ORG.email, ORG.password), name, { assign: false })

async function assignInUi(page: Page, eventId: number, coordinator: string) {
  await page.goto(`/coordinator-lead/queue/${eventId}`)
  await page.getByLabel('Event Coordinator', { exact: true }).selectOption({ label: coordinator })
  await page.getByRole('button', { name: 'Assign' }).click()
}

async function expectNoSeriousViolations(page: Page, label: string) {
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))))
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  const blocking = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  expect(blocking.map((v) => `${v.impact} ${v.id}: ${v.help}`).join('\n'), label).toBe('')
}

test('TC-LA-1e: assigning leaves the queue, becomes Under Review and appears for the Coordinator', async ({ browser, request }) => {
  const id = await queued(request)
  const lead = await openAs(browser, LEAD)
  await assignInUi(lead, id, 'Sam Tan (0 active Events)')
  await expect(lead.getByRole('status')).toContainText('Assigned to Sam Tan')
  await expect(lead.getByRole('status')).toContainText('Under Review')

  await lead.goto('/coordinator-lead/queue')
  await expect(lead.getByText('Needs an owner')).toHaveCount(0)

  const sam = await openAs(browser, SAM)
  await sam.goto('/coordinator/events')
  const row = sam.locator('.request').filter({ hasText: 'Needs an owner' })
  await expect(row).toBeVisible()
  await expect(row).toContainText('Under Review')
})

test('TC-LA-2e: the list shows each Coordinator with their active Events', async ({ browser, request }) => {
  const first = await queued(request, 'First')
  const second = await queued(request, 'Second')
  const lead = await openAs(browser, LEAD)
  await lead.goto(`/coordinator-lead/queue/${first}`)
  await expect(lead.getByRole('option', { name: 'Sam Tan (0 active Events)' })).toBeAttached()
  await expect(lead.getByRole('option', { name: 'Priya Nair (0 active Events)' })).toBeAttached()
  await assignInUi(lead, first, 'Sam Tan (0 active Events)')
  await expect(lead.getByRole('status')).toBeVisible()

  await lead.goto(`/coordinator-lead/queue/${second}`)
  await expect(lead.getByRole('option', { name: 'Sam Tan (1 active Event)' })).toBeAttached()
  await expect(lead.getByRole('option', { name: 'Priya Nair (0 active Events)' })).toBeAttached()
})

test('TC-LA-3e: the Activity Log records the Lead, the Coordinator and the time', async ({ browser, request }) => {
  const id = await queued(request)
  const lead = await openAs(browser, LEAD)
  await assignInUi(lead, id, 'Sam Tan (0 active Events)')
  await expect(lead.getByRole('status')).toBeVisible()

  const sam = await login(request, SAM.email, SAM.password)
  const detail = await (await request.get(`${API}/events/assigned/${id}`, { headers: sam })).json()
  const line = detail.activity[0] // the log is newest-first
  expect(line.changed_by_name).toBe('Lena Marie Lead')
  expect(line.note).toContain('Sam Tan')
  expect(Date.parse(line.created_at)).not.toBeNaN()
})

test('TC-LA-4e: another Coordinator cannot open or act on an assigned Event', async ({ browser, request }) => {
  const id = await queued(request)
  const lead = await openAs(browser, LEAD)
  await assignInUi(lead, id, 'Sam Tan (0 active Events)')
  await expect(lead.getByRole('status')).toBeVisible()

  const priya = await login(request, PRIYA.email, PRIYA.password)
  for (const [method, path] of [['get', `/events/assigned/${id}`], ['post', `/events/${id}/approve`]] as const) {
    const res = await request[method](`${API}${path}`, { headers: priya })
    expect([403, 404], `${method} ${path}`).toContain(res.status())
  }
  const page = await openAs(browser, PRIYA)
  await page.goto('/coordinator/events')
  await expect(page.getByText('Needs an owner')).toHaveCount(0)
})

test('TC-LA-5e: an Event no longer in the queue is refused and its assignment is unchanged', async ({ browser, request }) => {
  const id = await queued(request)
  const lead = await openAs(browser, LEAD)
  await assignInUi(lead, id, 'Sam Tan (0 active Events)')
  await expect(lead.getByRole('status')).toBeVisible()

  const leadToken = await login(request, LEAD.email, LEAD.password)
  const again = await request.post(`${API}/lead/unassigned-queue/${id}/assign`, { data: { coordinator_id: 0 }, headers: leadToken })
  expect(again.status()).toBe(422) // not even a Coordinator

  await lead.reload()
  await expect(lead.getByRole('alert')).toContainText('not in the Unassigned Queue')
  const sam = await login(request, SAM.email, SAM.password)
  const detail = await (await request.get(`${API}/events/assigned/${id}`, { headers: sam })).json()
  expect(detail.coordinator.name).toBe('Sam Tan')
})

test('TC-LA-6e: other roles are refused and the request stays unassigned', async ({ browser, request }) => {
  const id = await queued(request)
  const lead = await login(request, LEAD.email, LEAD.password)
  const coords = await (await request.get(`${API}/lead/coordinators`, { headers: lead })).json()
  const samId = coords.find((c: { name: string }) => c.name === 'Sam Tan').id
  for (const user of [SAM, ORG]) {
    const headers = await login(request, user.email, user.password)
    const res = await request.post(`${API}/lead/unassigned-queue/${id}/assign`, { data: { coordinator_id: samId }, headers })
    expect(res.status(), user.email).toBe(403)
  }
  const page = await openAs(browser, SAM)
  await page.goto(`/coordinator-lead/queue/${id}`)
  await expect(page).toHaveURL(/\/forbidden/)
  const queue = await (await request.get(`${API}/lead/unassigned-queue`, { headers: lead })).json()
  expect(queue.map((e: { id: number }) => e.id)).toContain(id)
})

for (const colorScheme of ['light', 'dark'] as const) {
  test(`TC-LA-A1: the assign panel passes axe (${colorScheme})`, async ({ browser, request }) => {
    const id = await queued(request, 'Axe assign')
    const lead = await openAs(browser, LEAD, { colorScheme })
    await lead.goto(`/coordinator-lead/queue/${id}`)
    await expect(lead.getByRole('heading', { name: 'Assign to an Event Coordinator' })).toBeVisible()
    await expectNoSeriousViolations(lead, `panel ${colorScheme}`)
    await lead.getByLabel('Event Coordinator', { exact: true }).selectOption({ label: 'Sam Tan (0 active Events)' })
    await lead.getByRole('button', { name: 'Assign' }).click()
    await expect(lead.getByRole('status')).toBeVisible()
    await expectNoSeriousViolations(lead, `confirmed ${colorScheme}`)
  })
}

test('TC-LA-A2: the select and Assign button are keyboard-operable with visible focus', async ({ browser, request }) => {
  const id = await queued(request, 'Keyboard assign')
  const lead = await openAs(browser, LEAD)
  await lead.goto(`/coordinator-lead/queue/${id}`)
  await expect(lead.getByLabel('Event Coordinator', { exact: true })).toBeVisible()
  await lead.getByLabel('Event Coordinator', { exact: true }).selectOption({ label: 'Sam Tan (0 active Events)' })
  await lead.getByLabel('Event Coordinator', { exact: true }).focus()
  await lead.keyboard.press('Tab') // from the select to the Assign button
  const focus = await lead.evaluate(() => {
    const el = document.activeElement as HTMLElement
    const s = getComputedStyle(el)
    return { text: (el.textContent ?? '').trim(), visible: (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0) || s.boxShadow !== 'none' }
  })
  expect(focus.text).toBe('Assign')
  expect(focus.visible, 'no visible focus on Assign').toBe(true)
  await lead.keyboard.press('Enter')
  await expect(lead.getByRole('status')).toContainText('Assigned to')
})
