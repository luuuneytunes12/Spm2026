import { expect, test } from '@playwright/test'
import { E2E_ORGANISER } from '../playwright.config'

/**
 * End-to-end coverage of the two Organiser stories, driven through a real
 * browser against a real backend and database.
 *
 * Traceability (see docs/test-cases-organiser-event-requests.md):
 *   TC-S1-2g -- Story 1 AC2, draft persists and reopens with input intact
 *   TC-S2-1e -- Story 2 AC1, incomplete submission blocked and flagged
 *   TC-S2-3c -- Story 2 AC3, the request moves from Drafts to Submitted
 *
 * Test isolation: every run stamps its event names with a unique prefix and
 * every assertion is scoped to that prefix. Cheaper and far less brittle
 * than truncating tables between tests, and it keeps these specs free of any
 * database coupling.
 */
const RUN = `E2E-${Date.now()}`

test.beforeEach(async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('Email').fill(E2E_ORGANISER.email)
  await page.getByLabel('Password').fill(E2E_ORGANISER.password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  // Landing on the dashboard is what proves the session was established.
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()
})

test('TC-S1-2g: an incomplete request saves as a draft and reopens intact', async ({ page }) => {
  const name = `${RUN} incomplete`

  await page.goto('/organiser/events/new')
  // Deliberately partial: no dates, no attendance, no requirements. This is
  // the case the original NOT NULL columns made impossible.
  await page.getByLabel('Event name').fill(name)
  await page.getByLabel('Purpose').fill('Captured over time')
  await page.getByRole('button', { name: 'Save as draft' }).click()

  const row = page.getByRole('listitem').filter({ hasText: name })
  await expect(row).toBeVisible()
  await expect(row.getByText('Draft')).toBeVisible()

  // Reopen it -- everything typed earlier must still be there.
  await row.getByRole('link', { name: /continue editing/i }).click()
  await expect(page.getByLabel('Event name')).toHaveValue(name)
  await expect(page.getByLabel('Purpose')).toHaveValue('Captured over time')
  await expect(page.getByLabel('Expected attendees')).toHaveValue('')
})

test('TC-S2-1e: submitting an incomplete request is blocked and flags the gaps', async ({
  page,
}) => {
  const name = `${RUN} blocked`

  await page.goto('/organiser/events/new')
  await page.getByLabel('Event name').fill(name)
  await page.getByRole('button', { name: 'Submit request' }).click()

  // Still on the form -- submission really was blocked.
  await expect(page.getByRole('alert')).toContainText('required')
  await expect(page.getByLabel('Venue requirements')).toHaveAttribute('aria-invalid', 'true')
  await expect(page.getByLabel('Expected attendees')).toHaveAttribute('aria-invalid', 'true')
  // The one field that was filled in is not flagged.
  await expect(page.getByLabel('Event name')).not.toHaveAttribute('aria-invalid', 'true')

  // And it is still only a draft.
  await page.goto('/organiser/events')
  await expect(page.getByRole('listitem').filter({ hasText: name })).toBeVisible()
})

test('TC-S2-3c: a completed request submits and moves out of Drafts', async ({ page }) => {
  const name = `${RUN} complete`

  await page.goto('/organiser/events/new')
  await page.getByLabel('Event name').fill(name)
  await page.getByLabel('Event type').fill('conference')
  await page.getByLabel('Purpose').fill('Annual partner briefing')
  await page.getByLabel('Preferred start').fill('2026-11-02T09:00')
  await page.getByLabel('Preferred end').fill('2026-11-02T17:00')
  await page.getByLabel('Expected attendees').fill('120')
  await page.getByLabel('Venue requirements').fill('Main hall, stage, podium')
  await page.getByLabel('Accessibility requirements').fill('Step-free access, hearing loop')
  await page.getByLabel('Equipment requirements').fill('2 projectors, 4 radio mics')

  await page.getByRole('button', { name: 'Submit request' }).click()

  // Redirected to the Submitted tab, with the request on it.
  await expect(page.getByRole('tab', { name: 'Submitted Requests' })).toHaveAttribute(
    'aria-selected',
    'true',
  )
  const submittedRow = page.getByRole('listitem').filter({ hasText: name })
  await expect(submittedRow).toBeVisible()
  await expect(submittedRow.getByText('Submitted')).toBeVisible()

  // ...and gone from Drafts. This is the half of AC3 that is easy to forget.
  await page.getByRole('tab', { name: 'Drafts' }).click()
  await expect(page.getByRole('listitem').filter({ hasText: name })).toHaveCount(0)
})
