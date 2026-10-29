/**
 * E2E SEARCH: AUTHENTICATION, OWNERSHIP, DRAFT, VALIDATION, ASSIGNMENT, CLARIFICATION, APPROVAL, REJECTION
 *
 * Access, intake and review journeys (E01–E08).
 *
 * Real browsers and separate role sessions exercise the UI against the
 * Playwright-configured backend and disposable local Postgres. The tests
 * follow the event across organiser, lead and coordinator hand-offs rather
 * than testing isolated components. Story specs retain detailed edge cases.
 *
 * Jira: SCRUM-20, 21, 23, 25–27, 79–81 and 103. Users are seeded only as
 * prerequisites; each test makes and decides its own event through the UI.
 */
import { expect, test } from '@playwright/test'
import type { Browser, Page } from '@playwright/test'
import { openAs } from './support/coordinator-users'
import { removeUsers, resetUsers, seedUsers } from './support/db'
import type { SeedUser } from './support/db'

const password = 'e2e-intake-password-123'
const organiser: SeedUser = { name: 'Journey Organiser', email: 'e2e_journey_org@cs.local', role: 'organiser', password }
const otherOrganiser: SeedUser = { name: 'Other Organiser', email: 'e2e_journey_other@cs.local', role: 'organiser', password }
const lead: SeedUser = { name: 'Journey Lead', email: 'e2e_journey_lead@cs.local', role: 'event_coordinator_lead', password }
const coordinator: SeedUser = { name: 'Journey Coordinator', email: 'e2e_journey_coord@cs.local', role: 'coordinator', password }
const replacement: SeedUser = { name: 'Replacement Coordinator', email: 'e2e_journey_replacement@cs.local', role: 'coordinator', password }
const users = [organiser, otherOrganiser, lead, coordinator, replacement]
const emails = users.map((user) => user.email)

test.beforeAll(() => seedUsers(users))
test.beforeEach(() => resetUsers(emails))
// BROWSER CONTEXT ISOLATION: openAs creates separate sessions for each role.
// Close them after every test, including failures, so sessions do not accumulate.
test.afterEach(async ({ browser }) => {
  await Promise.all(browser.contexts().map((context) => context.close()))
})
test.afterAll(() => removeUsers(emails))

/** Give each person a separate authenticated browser session. */
async function open(browser: Browser, user: SeedUser) {
  return openAs(browser, user)
}

/** Complete the required fields using future dates, avoiding calendar-dependent tests. */
async function completeRequest(page: Page) {
  const year = new Date().getFullYear() + 2
  await page.getByLabel('Event type').fill('Conference')
  await page.getByLabel('Purpose').fill('Partner briefing')
  await page.getByLabel('Preferred start').fill(`${year}-11-02T09:00`)
  await page.getByLabel('Preferred end').fill(`${year}-11-02T17:00`)
  await page.getByLabel('Expected attendees').fill('120')
  await page.getByLabel('Venue requirements').fill('Main hall and stage')
  await page.getByLabel('Accessibility requirements').fill('Step-free access')
  await page.getByLabel('Other equipment notes').fill('Two projectors')
}

/** Create a submitted event through the organiser's actual request form. */
async function submitFromUi(page: Page, name: string) {
  await page.goto('/organiser/events/new')
  await page.getByLabel('Event name').fill(name)
  await completeRequest(page)
  await page.getByRole('button', { name: 'Submit request' }).click()
  const row = page.getByRole('listitem').filter({ hasText: name })
  await expect(row).toBeVisible()
  await expect(row).toContainText('Submitted')
  return row
}

/** Find the request in the lead's queue and assign the named coordinator. */
async function assignFromQueue(page: Page, name: string) {
  await page.goto('/coordinator-lead/queue')
  const row = page.getByRole('listitem').filter({ hasText: name })
  await expect(row).toBeVisible()
  await row.getByRole('link', { name: /review/i }).click()
  const select = page.getByLabel('Event Coordinator', { exact: true })
  const label = await select.getByRole('option', { name: /Journey Coordinator/ }).textContent()
  await select.selectOption({ label: label!.trim() })
  await page.getByRole('button', { name: 'Assign', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('Assigned to Journey Coordinator')
}

/** Navigate through the assigned-events list, confirming the hand-off is visible. */
async function openAssigned(page: Page, name: string) {
  await page.goto('/coordinator/events')
  const row = page.getByRole('listitem').filter({ hasText: name })
  await expect(row).toBeVisible()
  await row.getByRole('link', { name: /view details/i }).click()
  await expect(page.getByRole('heading', { level: 1, name })).toBeVisible()
}

/** Follow the same request from a private draft to a reviewed and approved event. */
test('E03–E08: draft, submit, assign, clarify and approve across three roles', async ({ browser }) => {
  // This journey covers three logins and several hand-offs, so allow more time
  // than a single-screen test without using fixed sleeps.
  test.setTimeout(60_000)
  const name = 'Journey: partner briefing'
  const org = await open(browser, organiser)
  const leadPage = await open(browser, lead)

  // Save one partial draft, then try submitting that same draft incomplete.
  await org.goto('/organiser/events/new')
  await org.getByLabel('Event name').fill(name)
  await org.getByLabel('Purpose').fill('Partner briefing')
  await org.getByRole('button', { name: 'Save as draft' }).click()
  const draft = org.getByRole('listitem').filter({ hasText: name })
  await expect(draft).toContainText('Draft')
  await draft.getByRole('link', { name: /continue editing/i }).click()
  await org.getByRole('button', { name: 'Submit request' }).click()
  await expect(org.getByRole('alert')).toContainText('required')
  await leadPage.goto('/coordinator-lead/queue')
  await expect(leadPage.getByText(name)).toHaveCount(0)

  // A draft remains editable after a new login, then moves out of Drafts.
  await org.getByRole('button', { name: 'Log out' }).click()
  await org.goto('/login')
  await org.getByLabel('Email').fill(organiser.email)
  await org.getByLabel('Password').fill(password)
  await org.getByRole('button', { name: 'Sign in' }).click()
  await expect(org.getByRole('heading', { name: /Welcome back/ })).toBeVisible()
  await org.goto('/organiser/events')
  await org.getByRole('listitem').filter({ hasText: name }).getByRole('link', { name: /continue editing/i }).click()
  await expect(org.getByLabel('Purpose')).toHaveValue('Partner briefing')
  await completeRequest(org)
  await org.getByRole('button', { name: 'Submit request' }).click()
  const submitted = org.getByRole('listitem').filter({ hasText: name })
  await expect(submitted).toContainText('Submitted')
  await org.getByRole('tab', { name: 'Drafts' }).click()
  await expect(org.getByRole('listitem').filter({ hasText: name })).toHaveCount(0)

  // The coordinator and organiser exchange a clarification before approval.
  await assignFromQueue(leadPage, name)
  const coord = await open(browser, coordinator)
  await openAssigned(coord, name)
  await coord.getByLabel('Clarification request').fill('Please confirm the accessibility arrangements.')
  await coord.getByRole('button', { name: 'Send clarification request' }).click()
  await expect(coord.getByText('Awaiting Organiser Reply').first()).toBeVisible()

  await org.goto('/organiser/events?tab=submitted')
  await org.getByRole('listitem').filter({ hasText: name }).getByRole('link', { name: /view/i }).click()
  await expect(org.getByRole('list', { name: 'Clarification thread' })).toContainText('Please confirm the accessibility arrangements.')
  await org.getByLabel('Your reply').fill('The venue needs step-free access.')
  await org.getByRole('button', { name: 'Send reply' }).click()
  await expect(org.getByText('Your reply has been sent. The request is back under review.')).toBeVisible()
  await coord.reload()
  await expect(coord.getByRole('list', { name: 'Clarification thread' })).toContainText('The venue needs step-free access.')
  await coord.getByRole('button', { name: 'Approve request' }).click()
  await expect(coord.getByText('Event Approved').first()).toBeVisible()
  await org.reload()
  await expect(org.getByText('Event Approved').first()).toBeVisible()
  await expect(org.getByRole('list', { name: 'Activity log' })).toContainText('Journey Coordinator')
})

/** Check the alternative review outcome, including the organiser's notification. */
test('E08: rejection requires a reason and the organiser sees the decision', async ({ browser }) => {
  const name = 'Journey: rejected request'
  const org = await open(browser, organiser)
  await submitFromUi(org, name)
  const leadPage = await open(browser, lead)
  await assignFromQueue(leadPage, name)
  const coord = await open(browser, coordinator)
  await openAssigned(coord, name)
  // No reason means no rejection; after a decision, approval is unavailable.
  await expect(coord.getByRole('button', { name: 'Reject request' })).toBeDisabled()
  await coord.getByLabel('Rejection reason').fill('The requested event cannot be accommodated.')
  await coord.getByRole('button', { name: 'Reject request' }).click()
  await expect(coord.getByText('Event Rejected').first()).toBeVisible()
  await expect(coord.getByRole('button', { name: 'Approve request' })).toHaveCount(0)
  await org.goto('/organiser/events?tab=submitted')
  await org.getByRole('listitem').filter({ hasText: name }).getByRole('link', { name: /view/i }).click()
  await expect(org.getByText('Event Rejected').first()).toBeVisible()
  await expect(org.getByRole('list', { name: 'Activity log' })).toContainText('The requested event cannot be accommodated.')
  await org.goto('/notifications')
  await expect(org.getByText(/The requested event cannot be accommodated/).first()).toBeVisible()
})

/** Prove that reassignment changes who can manage the same event. */
test('E06: reassignment transfers the event and preserves the organiser’s view', async ({ browser }) => {
  const name = 'Journey: reassignment'
  const org = await open(browser, organiser)
  await submitFromUi(org, name)
  const leadPage = await open(browser, lead)
  await assignFromQueue(leadPage, name)
  await leadPage.goto('/coordinator-lead/assignments')
  await leadPage.getByRole('listitem').filter({ hasText: name }).getByRole('link', { name: /review/i }).click()
  const select = leadPage.getByLabel('New Event Coordinator', { exact: true })
  const label = await select.getByRole('option', { name: /Replacement Coordinator/ }).textContent()
  await select.selectOption({ label: label!.trim() })
  await leadPage.getByRole('button', { name: 'Reassign' }).click()
  await expect(leadPage.getByRole('status')).toContainText('Reassigned to Replacement Coordinator')
  // The old owner loses the event; its new owner and organiser see the hand-off.
  const oldCoordinator = await open(browser, coordinator)
  await oldCoordinator.goto('/coordinator/events')
  await expect(oldCoordinator.getByText(name)).toHaveCount(0)
  const newCoordinator = await open(browser, replacement)
  await openAssigned(newCoordinator, name)
  await expect(newCoordinator.getByText('Under Review').first()).toBeVisible()
  await org.goto('/organiser/events?tab=submitted')
  await org.getByRole('listitem').filter({ hasText: name }).getByRole('link', { name: /view/i }).click()
  await expect(org.getByText('Replacement Coordinator').first()).toBeVisible()
})

/** Check sign-in, role restrictions and the boundary between two organisers. */
test('E01–E02: authentication and role/ownership boundaries', async ({ browser }) => {
  // Check both the login boundary and the separate ownership/role boundaries.
  const page = await (await browser.newContext()).newPage()
  await page.goto('/coordinator-lead/queue')
  await expect(page).toHaveURL(/\/login/)
  await page.getByLabel('Email').fill(organiser.email)
  await page.getByLabel('Password').fill('wrong-password')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('alert')).toHaveText('Invalid credentials')

  const org = await open(browser, organiser)
  const row = await submitFromUi(org, 'Journey: private event')
  const href = await row.getByRole('link', { name: /view/i }).getAttribute('href')
  const other = await open(browser, otherOrganiser)
  await other.goto('/organiser/events?tab=submitted')
  await expect(other.getByText('Journey: private event')).toHaveCount(0)
  await other.goto(href!)
  await expect(other.getByRole('heading', { name: 'Journey: private event' })).toHaveCount(0)
  await expect(other.getByRole('alert')).toBeVisible()
  await other.goto('/coordinator-lead/queue')
  await expect(other).toHaveURL(/\/forbidden/)
})
