import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { API, login, submitEvent } from './support/api'
import { openAs } from './support/coordinator-users'
import type { SeedUser } from './support/db'
import { removeUsers, resetUsers, seedUsers } from './support/db'

/**
 * End-to-end coverage of SCRUM-81, "Reassign Event as Coordinator Lead", plus
 * its DoD accessibility checks.
 *
 *   TC-LR-1e -- AC1, the new Coordinator can open and act on it; the previous one cannot
 *   TC-LR-2e -- AC2, status and details unchanged; earlier Activity Log entries kept
 *   TC-LR-3e -- AC3, the Activity Log records the Lead, both Coordinators and the time
 *   TC-LR-4e -- AC4, a finished Event cannot be reassigned
 *   TC-LR-5e -- AC5, other roles are refused; assignment unchanged
 *   TC-LR-A1 -- DoD 8, axe (light, dark)    TC-LR-A2 -- DoD 8, keyboard and focus
 *
 * Sam is seeded first and holds each Event (submitEvent's autoAssign picks the
 * least-loaded Coordinator, ties to Sam); the Lead then moves it to Priya.
 */
const PASSWORD = 'e2e-lead-reassign-123'
const LEAD: SeedUser = { email: 'e2e_lr_lead@cs.local', name: 'Lena Marie Lead', role: 'event_coordinator_lead', password: PASSWORD }
const ORG: SeedUser = { email: 'e2e_lr_org@cs.local', name: 'Olivia Organiser', role: 'organiser', password: PASSWORD }
const SAM: SeedUser = { email: 'e2e_lr_sam@cs.local', name: 'Sam Tan', role: 'coordinator', password: PASSWORD }
const PRIYA: SeedUser = { email: 'e2e_lr_priya@cs.local', name: 'Priya Nair', role: 'coordinator', password: PASSWORD }
const EMAILS = [LEAD.email, ORG.email, SAM.email, PRIYA.email]

test.beforeAll(() => seedUsers([LEAD, ORG, SAM, PRIYA]))
test.beforeEach(() => resetUsers(EMAILS))
test.afterAll(() => removeUsers(EMAILS))

/** An Event held by Sam. */
const held = async (request: Parameters<typeof login>[0], name = 'Held by Sam') =>
  submitEvent(request, await login(request, ORG.email, ORG.password), name)

async function reassignInUi(page: Page, eventId: number, to = 'Priya Nair (0 active Events)') {
  await page.goto(`/coordinator-lead/assignments/${eventId}`)
  await page.getByLabel('New Event Coordinator', { exact: true }).selectOption({ label: to })
  await page.getByRole('button', { name: 'Reassign' }).click()
}

async function activity(request: Parameters<typeof login>[0], user: SeedUser, id: number) {
  const headers = await login(request, user.email, user.password)
  return (await (await request.get(`${API}/events/assigned/${id}`, { headers })).json()).activity
}

async function expectNoSeriousViolations(page: Page, label: string) {
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))))
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  const blocking = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  expect(blocking.map((v) => `${v.impact} ${v.id}: ${v.help}`).join('\n'), label).toBe('')
}

test('TC-LR-1e: the new Coordinator can open and act on it; the previous one cannot', async ({ browser, request }) => {
  const id = await held(request)
  const lead = await openAs(browser, LEAD)
  await reassignInUi(lead, id, 'Priya Nair (0 active Events)')
  await expect(lead.getByRole('status')).toContainText('Reassigned to Priya Nair')

  const priya = await openAs(browser, PRIYA)
  await priya.goto('/coordinator/events')
  await expect(priya.getByText('Held by Sam')).toBeVisible()
  await priya.goto(`/coordinator/events/${id}`)
  await expect(priya.getByRole('heading', { level: 1, name: 'Held by Sam' })).toBeVisible()
  const pH = await login(request, PRIYA.email, PRIYA.password)
  expect((await request.post(`${API}/events/${id}/approve`, { headers: pH })).status()).toBe(200) // can act

  const sam = await openAs(browser, SAM)
  await sam.goto('/coordinator/events')
  await expect(sam.getByText('Held by Sam')).toHaveCount(0)
  const sH = await login(request, SAM.email, SAM.password)
  expect((await request.get(`${API}/events/assigned/${id}`, { headers: sH })).status()).toBe(409) // told it moved
  const reject = await request.post(`${API}/events/${id}/reject`, { headers: sH, data: { reason: 'no' } })
  expect([403, 404]).toContain(reject.status())
})

test('TC-LR-6e: the previous Coordinator opening it sees who it was reassigned to', async ({ browser, request }) => {
  const id = await held(request, 'Moved away')
  const lead = await openAs(browser, LEAD)
  await reassignInUi(lead, id, 'Priya Nair (0 active Events)')
  await expect(lead.getByRole('status')).toContainText('Reassigned to Priya Nair')

  const sam = await openAs(browser, SAM)
  await sam.goto(`/coordinator/events/${id}`)
  await expect(sam.getByRole('alert')).toHaveText(
    "'Moved away' that was initially assigned to you by the Event Coordinator Lead has been reassigned to Priya Nair.",
  )
  // A Coordinator who never held it learns nothing: still "not assigned to you".
  const other = await openAs(browser, ORG)
  await other.goto(`/coordinator/events/${id}`)
  await expect(other.getByText('Priya Nair')).toHaveCount(0)
})

test('TC-LR-2e: status and details are unchanged and earlier history is kept', async ({ browser, request }) => {
  const id = await held(request)
  const before = await activity(request, SAM, id)
  const sH = await login(request, SAM.email, SAM.password)
  const detailBefore = await (await request.get(`${API}/events/assigned/${id}`, { headers: sH })).json()

  const lead = await openAs(browser, LEAD)
  await reassignInUi(lead, id)
  await expect(lead.getByRole('status')).toBeVisible()

  const after = await activity(request, PRIYA, id)
  expect(after).toHaveLength(before.length + 1)
  expect(after.slice(1)).toEqual(before)
  const pH = await login(request, PRIYA.email, PRIYA.password)
  const detailAfter = await (await request.get(`${API}/events/assigned/${id}`, { headers: pH })).json()
  expect(detailAfter.status).toBe(detailBefore.status)
  for (const field of ['name', 'purpose', 'description', 'expected_attendance', 'venue_requirements', 'accessibility_needs', 'registration_enabled']) {
    expect(detailAfter[field], field).toEqual(detailBefore[field])
  }
})

test('TC-LR-3e: the Activity Log records the Lead, both Coordinators and the time', async ({ browser, request }) => {
  const id = await held(request)
  const lead = await openAs(browser, LEAD)
  await reassignInUi(lead, id)
  await expect(lead.getByRole('status')).toBeVisible()
  const line = (await activity(request, PRIYA, id))[0]
  expect(line.changed_by_name).toBe('Lena Marie Lead')
  expect(line.note).toBe('Reassigned from Sam Tan to Priya Nair.')
  expect(Date.parse(line.created_at)).not.toBeNaN()
})

test('TC-LR-4e: a finished Event cannot be reassigned', async ({ request }) => {
  const id = await held(request)
  const sH = await login(request, SAM.email, SAM.password)
  expect((await request.post(`${API}/events/${id}/reject`, { headers: sH, data: { reason: 'Not viable' } })).status()).toBe(200)
  const lead = await login(request, LEAD.email, LEAD.password)
  const coords = await (await request.get(`${API}/lead/coordinators`, { headers: lead })).json()
  const priyaId = coords.find((c: { name: string }) => c.name === 'Priya Nair').id
  const res = await request.post(`${API}/lead/assignments/${id}/reassign`, { headers: lead, data: { coordinator_id: priyaId } })
  expect(res.status()).toBe(409)
  const detail = await (await request.get(`${API}/events/assigned/${id}`, { headers: sH })).json()
  expect(detail.coordinator.name).toBe('Sam Tan')
})

test('TC-LR-5e: other roles are refused and the assignment is unchanged', async ({ browser, request }) => {
  const id = await held(request)
  const lead = await login(request, LEAD.email, LEAD.password)
  const priyaId = (await (await request.get(`${API}/lead/coordinators`, { headers: lead })).json()).find((c: { name: string }) => c.name === 'Priya Nair').id
  for (const user of [SAM, PRIYA, ORG]) {
    const headers = await login(request, user.email, user.password)
    const res = await request.post(`${API}/lead/assignments/${id}/reassign`, { headers, data: { coordinator_id: priyaId } })
    expect(res.status(), user.email).toBe(403)
  }
  const page = await openAs(browser, SAM)
  await page.goto(`/coordinator-lead/assignments/${id}`)
  await expect(page).toHaveURL(/\/forbidden/)
  const sH = await login(request, SAM.email, SAM.password)
  expect((await (await request.get(`${API}/events/assigned/${id}`, { headers: sH })).json()).coordinator.name).toBe('Sam Tan')
})

for (const colorScheme of ['light', 'dark'] as const) {
  test(`TC-LR-A1: the reassign panel passes axe (${colorScheme})`, async ({ browser, request }) => {
    const id = await held(request, 'Axe reassign')
    const lead = await openAs(browser, LEAD, { colorScheme })
    await lead.goto(`/coordinator-lead/assignments/${id}`)
    await expect(lead.getByRole('heading', { name: 'Reassign to another Event Coordinator' })).toBeVisible()
    await expectNoSeriousViolations(lead, `panel ${colorScheme}`)
    await lead.getByLabel('New Event Coordinator', { exact: true }).selectOption({ label: 'Priya Nair (0 active Events)' })
    await lead.getByRole('button', { name: 'Reassign' }).click()
    await expect(lead.getByRole('status')).toBeVisible()
    await expectNoSeriousViolations(lead, `confirmed ${colorScheme}`)
  })
}

test('TC-LR-A2: the select and Reassign button are keyboard-operable with visible focus', async ({ browser, request }) => {
  const id = await held(request, 'Keyboard reassign')
  const lead = await openAs(browser, LEAD)
  await lead.goto(`/coordinator-lead/assignments/${id}`)
  const select = lead.getByLabel('New Event Coordinator', { exact: true })
  await expect(select).toBeVisible()
  await select.selectOption({ label: 'Priya Nair (0 active Events)' })
  await select.focus()
  await lead.keyboard.press('Tab')
  const focus = await lead.evaluate(() => {
    const el = document.activeElement as HTMLElement
    const s = getComputedStyle(el)
    return { text: (el.textContent ?? '').trim(), visible: (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0) || s.boxShadow !== 'none' }
  })
  expect(focus.text).toBe('Reassign')
  expect(focus.visible, 'no visible focus on Reassign').toBe(true)
  await lead.keyboard.press('Enter')
  await expect(lead.getByRole('status')).toContainText('Reassigned to')
})
