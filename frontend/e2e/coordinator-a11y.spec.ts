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

    test('Coordinator landing page', async ({ browser }) => {
      const sam = await openAs(browser, SAM, { colorScheme })
      await sam.goto('/coordinator')
      await expect(sam.getByRole('heading', { name: /Welcome back/ })).toBeVisible()
      await expectNoSeriousViolations(sam, `/coordinator (${colorScheme})`)
    })

    test('Coordinator profile: the form', async ({ browser }) => {
      const sam = await openAs(browser, SAM, { colorScheme })
      await sam.goto('/profile')
      await expect(sam.getByLabel('Name')).toBeVisible()
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

    test('Organiser request list', async ({ browser, request }) => {
      await eventFor(request, 'Organiser view')
      const olivia = await openAs(browser, OLIVIA, { colorScheme })
      await olivia.goto('/organiser/events')
      await expect(olivia.getByRole('heading', { level: 1 })).toBeVisible()
      await expectNoSeriousViolations(olivia, `/organiser/events (${colorScheme})`)
    })

    test('Organiser event page: assigned coordinator card and activity log', async ({ browser, request }) => {
      const eventId = await eventFor(request, 'Organiser event')
      const olivia = await openAs(browser, OLIVIA, { colorScheme })
      await olivia.goto(`/organiser/events/${eventId}`)
      await expect(olivia.getByRole('heading', { name: 'Your Assigned Event Coordinator' })).toBeVisible()
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

test.describe('keyboard only', () => {
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
