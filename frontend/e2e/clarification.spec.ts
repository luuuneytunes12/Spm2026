import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { login, submitEvent } from './support/api'
import { EMAILS, OLIVIA, SAM, USERS, openAs } from './support/coordinator-users'
import { removeUsers, resetUsers, seedUsers } from './support/db'

/**
 * End-to-end coverage of SCRUM-27 (Request Event Clarification), SCRUM-103
 * (Respond to Clarification Request) and the status/history side of SCRUM-30.
 *
 *   TC-CL-1e  -- 27 AC1-4: Sam asks, the status flips, Olivia can read it, the log shows it
 *   TC-CL-2e  -- 27 AC5: an empty request is blocked and the status is unchanged
 *   TC-CL-3e  -- 103 AC1-3: Olivia replies, status back to Under Review, log shows the reply
 *   TC-CL-4e  -- 103 AC5: an empty reply is blocked and the Event stays Awaiting Organiser Reply
 *   TC-CL-5e  -- 103 AC6: an amended field is saved and the log shows what changed
 *   TC-CL-6e  -- 30 AC3-4: the new status is shown on the Event and in its history
 *   TC-CL-A1  -- DoD 8, axe on both panels (light, dark)
 *   TC-CL-A2  -- DoD 8, keyboard: both text areas and buttons reachable with visible focus
 */
test.beforeAll(() => seedUsers(USERS))
test.beforeEach(() => resetUsers(EMAILS))
test.afterAll(() => removeUsers(EMAILS))

const MESSAGE = 'Please confirm the AV set-up for the main hall.'
const REPLY = 'The AV set-up is two projectors and four radio mics.'

async function submit(request: Parameters<typeof login>[0], name = 'Clarify me') {
  return submitEvent(request, await login(request, OLIVIA.email, OLIVIA.password), name)
}

/** Sam (the assigned Coordinator) asks for clarification; returns the Event id. */
async function ask(browser: Parameters<typeof openAs>[0], request: Parameters<typeof login>[0], name?: string) {
  const id = await submit(request, name)
  const sam = await openAs(browser, SAM)
  await sam.goto(`/coordinator/events/${id}`)
  await sam.getByLabel('Clarification request').fill(MESSAGE)
  await sam.getByRole('button', { name: 'Send clarification request' }).click()
  await expect(sam.getByText('Clarification request sent to the Event Organiser.')).toBeVisible()
  return { id, sam }
}

async function expectNoSeriousViolations(page: Page, label: string) {
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))))
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  const blocking = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  expect(blocking.map((v) => `${v.impact} ${v.id}: ${v.help} ${v.nodes.map((n) => n.target.join(' ') + ' ' + (n.any[0]?.message ?? '')).join(' | ')}`).join('\n'), label).toBe('')
}

test('TC-CL-1e: a clarification request is saved, flips the status and reaches the Organiser', async ({ browser, request }) => {
  const { id, sam } = await ask(browser, request)
  await expect(sam.getByText('Awaiting Organiser Reply').first()).toBeVisible()
  await expect(sam.getByText('Waiting for the Event Organiser to reply.')).toBeVisible()

  const olivia = await openAs(browser, OLIVIA)
  await olivia.goto(`/organiser/events/${id}`)
  await expect(olivia.getByText('Awaiting Organiser Reply').first()).toBeVisible()
  await expect(olivia.getByRole('list', { name: 'Clarification thread' })).toContainText(MESSAGE)
  await expect(olivia.getByRole('list', { name: 'Activity log' })).toContainText(MESSAGE)
  await expect(olivia.getByRole('list', { name: 'Activity log' })).toContainText('Sam Tan')
})

test('TC-CL-2e: an empty clarification request is blocked and the status is unchanged', async ({ browser, request }) => {
  const id = await submit(request)
  const sam = await openAs(browser, SAM)
  await sam.goto(`/coordinator/events/${id}`)
  await sam.getByRole('button', { name: 'Send clarification request' }).click()
  await expect(sam.locator('#clarification-message')).toHaveAttribute('aria-invalid', 'true')
  await expect(sam.getByText('Enter a message for the Event Organiser.')).toBeVisible()
  await expect(sam.getByText('Under Review').first()).toBeVisible()
  await expect(sam.getByText('Awaiting Organiser Reply')).toHaveCount(0)
})

test('TC-CL-3e: the Organiser replies; the Event returns to Under Review and the log shows the reply', async ({ browser, request }) => {
  const { id } = await ask(browser, request)
  const olivia = await openAs(browser, OLIVIA)
  await olivia.goto(`/organiser/events/${id}`)
  await olivia.getByLabel('Your reply').fill(REPLY)
  await olivia.getByRole('button', { name: 'Send reply' }).click()
  await expect(olivia.getByText('Your reply has been sent. The request is back under review.')).toBeVisible()
  await olivia.reload()
  await expect(olivia.getByText('Under Review').first()).toBeVisible()
  await expect(olivia.getByRole('list', { name: 'Activity log' })).toContainText(REPLY)
  await expect(olivia.getByRole('list', { name: 'Activity log' })).toContainText('Olivia Organiser')

  const sam = await openAs(browser, SAM)
  await sam.goto(`/coordinator/events/${id}`)
  await expect(sam.getByRole('list', { name: 'Clarification thread' })).toContainText(REPLY)
})

test('TC-CL-4e: an empty reply is blocked and the Event stays Awaiting Organiser Reply', async ({ browser, request }) => {
  const { id } = await ask(browser, request)
  const olivia = await openAs(browser, OLIVIA)
  await olivia.goto(`/organiser/events/${id}`)
  await olivia.getByRole('button', { name: 'Send reply' }).click()
  await expect(olivia.locator('#clarification-reply')).toHaveAttribute('aria-invalid', 'true')
  await expect(olivia.getByText('Enter your reply.')).toBeVisible()
  await olivia.reload()
  await expect(olivia.getByText('Awaiting Organiser Reply').first()).toBeVisible()
})

test('TC-CL-5e: an amended field is saved with the reply and the log shows what changed', async ({ browser, request }) => {
  const { id } = await ask(browser, request)
  const olivia = await openAs(browser, OLIVIA)
  await olivia.goto(`/organiser/events/${id}`)
  await olivia.getByLabel('Your reply').fill(REPLY)
  await olivia.getByLabel('Update the request fields').check()
  await olivia.locator('#amend-expected_attendance').fill('250')
  await olivia.getByRole('button', { name: 'Send reply' }).click()
  await expect(olivia.getByText('Your reply has been sent. The request is back under review.')).toBeVisible()
  await olivia.reload()
  await expect(olivia.getByRole('list', { name: 'Activity log' })).toContainText('expected_attendance')
  await expect(olivia.getByRole('list', { name: 'Activity log' })).toContainText('250')
})

test('TC-CL-6e: each status change is shown on the Event with its time', async ({ browser, request }) => {
  const { id } = await ask(browser, request)
  const olivia = await openAs(browser, OLIVIA)
  await olivia.goto(`/organiser/events/${id}`)
  const log = olivia.getByRole('list', { name: 'Activity log' })
  await expect(log).toContainText('Awaiting Organiser Reply')
  await expect(log.locator('.activity-meta').filter({ hasText: 'Sam Tan' }).first()).toContainText(/ · \S+/)
})

for (const colorScheme of ['light', 'dark'] as const) {
  test(`TC-CL-A1: both clarification panels pass axe (${colorScheme})`, async ({ browser, request }) => {
    const id = await submit(request)
    const sam = await openAs(browser, SAM, { colorScheme })
    await sam.goto(`/coordinator/events/${id}`)
    await expect(sam.getByLabel('Clarification request')).toBeVisible()
    await expectNoSeriousViolations(sam, `coordinator panel ${colorScheme}`)
    await sam.getByLabel('Clarification request').fill(MESSAGE)
    await sam.getByRole('button', { name: 'Send clarification request' }).click()
    await expect(sam.getByText('Clarification request sent to the Event Organiser.')).toBeVisible()

    const olivia = await openAs(browser, OLIVIA, { colorScheme })
    await olivia.goto(`/organiser/events/${id}`)
    await expect(olivia.getByLabel('Your reply')).toBeVisible()
    await expectNoSeriousViolations(olivia, `organiser panel ${colorScheme}`)
    await olivia.getByLabel('Update the request fields').check()
    await olivia.getByRole('button', { name: 'Send reply' }).click()
    await expect(olivia.locator('#clarification-reply')).toHaveAttribute('aria-invalid', 'true')
    await expectNoSeriousViolations(olivia, `organiser panel with error ${colorScheme}`)
  })
}

test('TC-CL-A2: the clarification fields and buttons are keyboard-reachable with visible focus', async ({ browser, request }) => {
  const id = await submit(request)
  const sam = await openAs(browser, SAM)
  await sam.goto(`/coordinator/events/${id}`)
  await expect(sam.getByLabel('Clarification request')).toBeVisible()
  const focused = new Set<string>()
  for (let i = 0; i < 60; i++) {
    await sam.keyboard.press('Tab')
    const info = await sam.evaluate(() => {
      const el = document.activeElement as HTMLElement | null
      if (!el || el === document.body) return null
      const s = getComputedStyle(el)
      const visible = (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0) || s.boxShadow !== 'none'
      return { id: el.id, text: (el.textContent ?? '').trim().slice(0, 40), tag: el.tagName, visible }
    })
    if (info) {
      expect(info.visible, `no visible focus on ${info.tag} "${info.text}"`).toBe(true)
      focused.add(info.id || info.text)
    }
  }
  expect(focused.has('clarification-message'), 'textarea not reachable by Tab').toBe(true)
  expect(focused.has('Send clarification request'), 'button not reachable by Tab').toBe(true)
})
