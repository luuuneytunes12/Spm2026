import { expect, test } from '@playwright/test'
import { E2E_ORGANISER } from '../playwright.config'

/**
 * End-to-end coverage of the "Edit User Profile" story, driven through a
 * real browser against a real backend and database.
 *
 * Traceability (see docs/test-cases-edit-profile.md):
 *   TC-EP-1e -- AC1, editing fields saves and reflects them on the page
 *   TC-EP-2c -- AC2, an invalid email is rejected and nothing is saved
 *   TC-EP-3e -- AC3, an invalid phone number is rejected and nothing is saved
 *   TC-EP-4b -- AC4, a saved change survives logout and a fresh login
 *
 * Test isolation: every run stamps the organisation field with a unique
 * value so assertions never depend on state left by a previous run. The
 * shared e2e organiser account's email/password are never changed here,
 * since other specs (draft-and-submit.spec.ts) sign in as the same user.
 */
const RUN = `E2E-${Date.now()}`

async function signIn(page: import('@playwright/test').Page) {
  await page.goto('/login')
  await page.getByLabel('Email').fill(E2E_ORGANISER.email)
  await page.getByLabel('Password').fill(E2E_ORGANISER.password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()
}

test.beforeEach(async ({ page }) => {
  await signIn(page)
})

test('TC-EP-1e: editing profile fields saves and reflects them immediately', async ({ page }) => {
  const organisation = `${RUN} Acme Events`

  await page.goto('/profile')
  await page.getByLabel('Organisation').fill(organisation)
  await page.getByLabel('Country code').selectOption('+65')
  await page.getByLabel('Phone number').fill('91234567')
  await page.getByLabel('How should we contact you?').selectOption('sms')
  await page.getByRole('button', { name: 'Save changes' }).click()

  await expect(page.getByText('Your profile has been updated.')).toBeVisible()
  // Reflected directly on the page, no reload needed.
  await expect(page.getByLabel('Organisation')).toHaveValue(organisation)
  await expect(page.getByLabel('Phone number')).toHaveValue('91234567')

  // And still there after a hard reload -- proves it was actually saved,
  // not just held in local component state.
  await page.reload()
  await expect(page.getByLabel('Organisation')).toHaveValue(organisation)
  await expect(page.getByLabel('Country code')).toHaveValue('+65')
  await expect(page.getByLabel('Phone number')).toHaveValue('91234567')
  await expect(page.getByLabel('How should we contact you?')).toHaveValue('sms')
})

test('TC-EP-2c: an invalid email format is rejected and nothing is saved', async ({ page }) => {
  const untouchedOrganisation = `${RUN} untouched by bad email`

  await page.goto('/profile')
  await page.getByLabel('Organisation').fill(untouchedOrganisation)
  await page.getByLabel('Email').fill('not-an-email')
  await page.getByRole('button', { name: 'Save changes' }).click()

  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.getByLabel('Email')).toHaveAttribute('aria-invalid', 'true')

  // Blocked means blocked -- reloading shows the organisation change was
  // never persisted either, since the whole request was rejected.
  await page.reload()
  await expect(page.getByLabel('Organisation')).not.toHaveValue(untouchedOrganisation)
})

test('TC-EP-3e: a phone number with letters is rejected and nothing is saved', async ({
  page,
}) => {
  const untouchedOrganisation = `${RUN} untouched by bad phone`

  await page.goto('/profile')
  await page.getByLabel('Organisation').fill(untouchedOrganisation)
  await page.getByLabel('Country code').selectOption('+65')
  await page.getByLabel('Phone number').fill('9123abcd')
  await page.getByRole('button', { name: 'Save changes' }).click()

  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.getByLabel('Phone number')).toHaveAttribute('aria-invalid', 'true')

  await page.reload()
  await expect(page.getByLabel('Organisation')).not.toHaveValue(untouchedOrganisation)
})

test('TC-EP-4b: a saved change survives logging out and back in', async ({ page }) => {
  const organisation = `${RUN} survives relogin`

  await page.goto('/profile')
  await page.getByLabel('Organisation').fill(organisation)
  await page.getByRole('button', { name: 'Save changes' }).click()
  await expect(page.getByText('Your profile has been updated.')).toBeVisible()

  await page.getByRole('button', { name: 'Log out' }).click()
  await expect(page).toHaveURL(/\/login/)

  await signIn(page)
  await page.goto('/profile')
  await expect(page.getByLabel('Organisation')).toHaveValue(organisation)
})
