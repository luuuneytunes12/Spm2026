import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { APIRequestContext, Page } from '@playwright/test'
import { login, submitEvent } from './support/api'
import { EMAILS, OLIVIA, SAM, USERS, openAs } from './support/coordinator-users'
import { removeUsers, resetUsers, seedUsers } from './support/db'

/**
 * Accessibility of the screens the four coordinator stories touch
 * (SCRUM-23, 24, 28, 64) -- Definition of Done, section 8:
 *
 *   - automated axe checks pass with no serious or critical violations
 *   - new UI is keyboard-navigable, with visible focus and labelled fields
 *
 * axe runs against the real rendered pages, in both colour schemes: the app
 * has a light and a dark theme and colour contrast is the rule most likely
 * to differ between them. Only serious and critical findings fail a test,
 * as the DoD sets; lesser ones are printed so they are not lost.
 */
test.beforeAll(() => seedUsers(USERS))
test.beforeEach(() => resetUsers(EMAILS))
test.afterAll(() => removeUsers(EMAILS))

const SCHEMES = ['light', 'dark'] as const

async function expectNoSeriousViolations(page: Page, label: string) {
  // A button that has just changed state is still fading between colours, and
  // axe would measure a half-way blend that no user ever rests on. Let every
  // running animation and transition finish so it reads the real colours.
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))))

  const { violations } = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze()

  const minor = violations.filter((v) => v.impact !== 'serious' && v.impact !== 'critical')
  if (minor.length > 0) {
    console.log(`[axe] ${label}: ${minor.length} minor/moderate finding(s): ${minor.map((v) => v.id).join(', ')}`)
  }

  const blocking = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  const report = blocking
    .map((v) => `${v.impact} ${v.id}: ${v.help}\n${v.nodes.slice(0, 3).map((n) => `    ${n.target.join(' ')}`).join('\n')}`)
    .join('\n')
  // Compared as text so a failure prints the rules and elements, not raw axe objects.
  expect(report, `${label}: ${blocking.length} serious/critical violation(s)`).toBe('')
}

async function eventFor(request: APIRequestContext, name: string) {
  return submitEvent(request, await login(request, OLIVIA.email, OLIVIA.password), name)
}

for (const colorScheme of SCHEMES) {
  test.describe(`axe, ${colorScheme} theme`, () => {
    test.use({ colorScheme })

    test('Coordinator page: available, then unavailable, with history', async ({ browser }) => {
      const sam = await openAs(browser, SAM, { colorScheme })
      await sam.goto('/coordinator')
      await expect(sam.getByRole('button', { name: 'Mark myself unavailable' })).toBeVisible()
      await expectNoSeriousViolations(sam, `/coordinator available (${colorScheme})`)

      await sam.getByRole('button', { name: 'Mark myself unavailable' }).click()
      await expect(sam.getByRole('list', { name: 'Availability history' })).toBeVisible()
      await expectNoSeriousViolations(sam, `/coordinator unavailable + history (${colorScheme})`)
    })

    test('Coordinator profile: availability card and the form', async ({ browser }) => {
      const sam = await openAs(browser, SAM, { colorScheme })
      await sam.goto('/profile')
      await expect(sam.getByRole('region', { name: 'Availability' })).toBeVisible()
      await expectNoSeriousViolations(sam, `/profile (${colorScheme})`)
    })

    test('My Assigned Events and the assigned event detail', async ({ browser, request }) => {
      const eventId = await eventFor(request, 'Accessible event')
      const sam = await openAs(browser, SAM, { colorScheme })

      await sam.goto('/coordinator/events')
      await expect(sam.getByText('Accessible event')).toBeVisible()
      await expectNoSeriousViolations(sam, `/coordinator/events (${colorScheme})`)

      await sam.goto(`/coordinator/events/${eventId}`)
      await expect(sam.getByRole('heading', { name: 'Event Details' })).toBeVisible()
      await expectNoSeriousViolations(sam, `/coordinator/events/:id (${colorScheme})`)
    })

    test('Organiser request list, with the coordinator pool collapsed and open', async ({ browser, request }) => {
      await eventFor(request, 'Organiser view')
      const olivia = await openAs(browser, OLIVIA, { colorScheme })
      await olivia.goto('/organiser/events')
      const summary = olivia.getByText(/Coordinators currently available for assignment/)
      await expect(summary).toBeVisible()
      await expectNoSeriousViolations(olivia, `/organiser/events, pool collapsed (${colorScheme})`)

      await summary.click()
      await expect(olivia.getByRole('list', { name: 'Coordinators in the assignment pool' })).toBeVisible()
      await expectNoSeriousViolations(olivia, `/organiser/events, pool open (${colorScheme})`)
    })

    test('Organiser event page: assigned coordinator card, pool and activity log', async ({ browser, request }) => {
      const eventId = await eventFor(request, 'Organiser event')
      const olivia = await openAs(browser, OLIVIA, { colorScheme })
      await olivia.goto(`/organiser/events/${eventId}`)
      await expect(olivia.getByRole('heading', { name: 'Your Assigned Event Coordinator' })).toBeVisible()
      await olivia.getByText(/Coordinators currently available for assignment/).click()
      await expectNoSeriousViolations(olivia, `/organiser/events/:id (${colorScheme})`)
    })

    test('Notifications page and the navbar bell panel', async ({ browser, request }) => {
      await eventFor(request, 'Notified event')
      const olivia = await openAs(browser, OLIVIA, { colorScheme })
      await olivia.goto('/notifications')
      await expect(olivia.getByText(/is now coordinating/)).toBeVisible()
      await expectNoSeriousViolations(olivia, `/notifications (${colorScheme})`)

      await olivia.getByRole('button', { name: /^Notifications/ }).click()
      await expect(olivia.getByRole('region', { name: 'Recent notifications' })).toBeVisible()
      await expectNoSeriousViolations(olivia, `bell panel (${colorScheme})`)
    })
  })
}

// ---------------------------------------------------------------------------
// Keyboard-only operation
// ---------------------------------------------------------------------------

/** Press Tab until `target` has focus, failing if it is never reached: proves
 *  it is in the tab order, not merely focusable by a script. */
async function tabTo(page: Page, target: import('@playwright/test').Locator, max = 60) {
  for (let i = 0; i < max; i++) {
    await page.keyboard.press('Tab')
    if (await target.evaluate((el) => el === document.activeElement)) return
  }
  throw new Error(`Never reached ${target} in ${max} Tab presses`)
}

async function hasVisibleFocus(locator: import('@playwright/test').Locator): Promise<boolean> {
  return locator.evaluate((el) => {
    const s = getComputedStyle(el)
    return (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0) || s.boxShadow !== 'none'
  })
}

test.describe('keyboard only', () => {
  test('a coordinator can reach and operate "Mark myself unavailable" with the keyboard, and sees where focus is', async ({ browser }) => {
    const sam = await openAs(browser, SAM)
    await sam.goto('/coordinator')
    const toggle = sam.getByRole('button', { name: 'Mark myself unavailable' })

    await tabTo(sam, toggle)
    expect(await hasVisibleFocus(toggle)).toBe(true)
    await sam.keyboard.press('Enter')

    await expect(sam.getByText('Unavailable', { exact: true })).toBeVisible()
  })

  test('a coordinator can reach and operate "Decline this event" with the keyboard', async ({ browser, request }) => {
    await eventFor(request, 'Keyboard decline')
    const sam = await openAs(browser, SAM)
    await sam.goto('/coordinator/events')
    const decline = sam.getByRole('button', { name: 'Decline this event' })

    await tabTo(sam, decline)
    expect(await hasVisibleFocus(decline)).toBe(true)
    await sam.keyboard.press('Enter')

    await expect(sam.getByText('Nothing assigned to you yet.')).toBeVisible()
  })

  test('the organiser can reach the coordinator pool dropdown by Tab and open it with the keyboard', async ({ browser }) => {
    const olivia = await openAs(browser, OLIVIA)
    await olivia.goto('/organiser/events')
    const summary = olivia.locator('details.pool-details > summary')

    await tabTo(olivia, summary)
    expect(await hasVisibleFocus(summary)).toBe(true)
    await olivia.keyboard.press('Enter')

    await expect(olivia.getByRole('list', { name: 'Coordinators in the assignment pool' })).toBeVisible()
  })

  test('every field on the profile form is labelled', async ({ browser }) => {
    const sam = await openAs(browser, SAM)
    await sam.goto('/profile')
    await expect(sam.getByRole('heading', { name: 'My profile' })).toBeVisible()

    const fields = sam.locator('form input:not([type="hidden"]), form select, form textarea')
    const count = await fields.count()
    expect(count).toBeGreaterThan(0)
    for (let i = 0; i < count; i++) {
      const name = await fields.nth(i).evaluate((el) => {
        const input = el as HTMLInputElement
        return (input.labels?.[0]?.textContent ?? el.getAttribute('aria-label') ?? '').trim()
      })
      expect(name, `field #${i} has no accessible label`).not.toBe('')
    }
  })
})
