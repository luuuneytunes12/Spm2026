import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { API, login, submitEvent } from './support/api'
import { EMAILS, OLIVIA, PRIYA, SAM, USERS, openAs } from './support/coordinator-users'
import { removeUsers, resetUsers, seedUsers } from './support/db'

/**
 * End-to-end coverage of the four Sprint 1 coordinator stories, driven
 * through a real browser against the real backend and a real Postgres.
 *
 *   SCRUM-23  View Coordinator Assignment          (the Organiser's side)
 *   SCRUM-24  Declare Coordinator Global Unavailability
 *   SCRUM-28  View Full Event Details as Coordinator
 *   SCRUM-64  Declare Coordinator Per-Event Unavailability
 *
 * Each test's title names the story and acceptance criterion it proves, the
 * same traceability convention as the unit tests
 * (see docs/test-cases-coordinator-availability.md).
 *
 * Three accounts are created for these specs and removed afterwards, so they
 * never linger in the assignment pool for the specs that run after:
 *   Olivia (Organiser), Sam Tan and Priya Nair (Coordinators).
 * Sam is created first, so when both carry the same load Sam is picked --
 * which is what lets the specs know who an event will go to.
 *
 * Getting an event submitted is done through the API (it is the starting
 * position, not the behaviour under test); everything a criterion is about is
 * done and checked on screen.
 */
test.beforeAll(() => seedUsers(USERS))
test.beforeEach(() => resetUsers(EMAILS))
test.afterAll(() => removeUsers(EMAILS))

async function submittedByOlivia(request: import('@playwright/test').APIRequestContext, name: string) {
  return submitEvent(request, await login(request, OLIVIA.email, OLIVIA.password), name)
}

/** The assigned coordinator's own Name / Email rows. Scoped to the detail
 *  list rather than the whole card, because the card also holds the pool
 *  dropdown, which names the same people. */
const coordinatorCard = (page: Page) =>
  page
    .locator('section', { has: page.getByRole('heading', { name: 'Your Assigned Event Coordinator' }) })
    .locator('dl.detail-list')

// ---------------------------------------------------------------------------
// SCRUM-23 -- the Organiser sees, and is told, who their coordinator is
// ---------------------------------------------------------------------------

test('SCRUM-23 AC1: after submitting, the Organiser sees the coordinator name and contact on the event page', async ({ browser, request }) => {
  const eventId = await submittedByOlivia(request, 'AC1 event')
  const olivia = await openAs(browser, OLIVIA)

  await olivia.goto(`/organiser/events/${eventId}`)

  const card = coordinatorCard(olivia)
  await expect(card.getByText('Sam Tan')).toBeVisible()
  await expect(card.getByRole('link', { name: SAM.email })).toHaveAttribute('href', `mailto:${SAM.email}`)
})

test('SCRUM-23 AC2: the Organiser is notified with the coordinator’s details, and the notice opens the event', async ({ browser, request }) => {
  const eventId = await submittedByOlivia(request, 'AC2 event')
  const olivia = await openAs(browser, OLIVIA)

  await expect(olivia.getByRole('button', { name: 'Notifications, 1 unread' })).toBeVisible()
  await olivia.goto('/notifications')

  const notice = olivia.getByRole('listitem').filter({ hasText: 'is now coordinating' })
  await expect(notice).toContainText(`Sam Tan (${SAM.email}) is now coordinating 'AC2 event'`)
  await notice.getByRole('link', { name: 'View event' }).click()
  await expect(olivia).toHaveURL(new RegExp(`/organiser/events/${eventId}$`))
})

test('SCRUM-23: the activity log (shared) and the notifications (per role) tell it differently', async ({ browser, request }) => {
  const eventId = await submittedByOlivia(request, 'Log vs notice')
  const olivia = await openAs(browser, OLIVIA)
  const sam = await openAs(browser, SAM)

  // The log is one record: Olivia and Sam read the same line.
  await olivia.goto(`/organiser/events/${eventId}`)
  await sam.goto(`/coordinator/events/${eventId}`)
  for (const page of [olivia, sam]) {
    await expect(page.getByRole('list', { name: 'Activity log' })).toContainText('Assigned to Sam Tan.')
  }

  // Notifications are worded for the reader and never cross over.
  await olivia.goto('/notifications')
  await expect(olivia.getByText(/is now coordinating/)).toBeVisible()
  await expect(olivia.getByText(/You have been assigned/)).toHaveCount(0)
  await sam.goto('/notifications')
  await expect(sam.getByText(/You have been assigned to coordinate 'Log vs notice'/)).toBeVisible()
  await expect(sam.getByText(/is now coordinating/)).toHaveCount(0)
})

// ---------------------------------------------------------------------------
// SCRUM-64 (and SCRUM-23 AC3/AC4) -- declining one event
// ---------------------------------------------------------------------------

test('SCRUM-64 AC1 + SCRUM-23 AC3/AC4: declining reassigns the event and the Organiser sees and is told the new coordinator', async ({ browser, request }) => {
  const eventId = await submittedByOlivia(request, 'Declined event')
  const olivia = await openAs(browser, OLIVIA)
  const sam = await openAs(browser, SAM)
  const priya = await openAs(browser, PRIYA)

  await sam.goto('/coordinator/events')
  await sam.getByRole('button', { name: 'Decline this event' }).click()
  await expect(sam.getByText('Nothing assigned to you yet.')).toBeVisible()

  await priya.goto('/coordinator/events')
  await expect(priya.getByText('Declined event')).toBeVisible()

  await olivia.goto(`/organiser/events/${eventId}`)
  const card = coordinatorCard(olivia)
  await expect(card.getByText('Priya Nair')).toBeVisible() // AC3
  await expect(card.getByText('Sam Tan')).toHaveCount(0)
  await olivia.goto('/notifications')
  await expect(olivia.getByText(new RegExp(`Priya Nair \\(${PRIYA.email}\\) is now coordinating`))).toBeVisible() // AC4
})

test('SCRUM-64 AC2 + AC3: after declining, the coordinator is still available and still receives new events', async ({ browser, request }) => {
  await submittedByOlivia(request, 'To decline')
  const sam = await openAs(browser, SAM)
  await sam.goto('/coordinator/events')
  await sam.getByRole('button', { name: 'Decline this event' }).click()
  await expect(sam.getByText('Nothing assigned to you yet.')).toBeVisible()

  // AC3: nothing about their status changed.
  await sam.goto('/coordinator')
  await expect(sam.getByText('Available', { exact: true })).toBeVisible()
  await expect(sam.getByText('Unavailable', { exact: true })).toHaveCount(0)
  await sam.goto('/profile')
  await expect(sam.getByRole('region', { name: 'Availability' }).getByText('Available', { exact: true })).toBeVisible()

  // AC2: Sam now holds the fewest, so the next event comes to Sam.
  const nextId = await submittedByOlivia(request, 'Next event')
  await sam.goto('/coordinator/events')
  await expect(sam.getByText('Next event')).toBeVisible()
  const olivia = await openAs(browser, OLIVIA)
  await olivia.goto(`/organiser/events/${nextId}`)
  await expect(coordinatorCard(olivia).getByText('Sam Tan')).toBeVisible()
})

test('SCRUM-64 AC4: the decline is in the activity log with the coordinator’s name and a timestamp', async ({ browser, request }) => {
  const eventId = await submittedByOlivia(request, 'Logged decline')
  const sam = await openAs(browser, SAM)
  await sam.goto('/coordinator/events')
  await sam.getByRole('button', { name: 'Decline this event' }).click()
  await expect(sam.getByText('Nothing assigned to you yet.')).toBeVisible()

  const olivia = await openAs(browser, OLIVIA)
  await olivia.goto(`/organiser/events/${eventId}`)
  const entry = olivia.locator('.activity-item', { hasText: 'declined this event' })
  await expect(entry).toContainText('Reassigned from Sam Tan to Priya Nair')
  await expect(entry.locator('.activity-meta')).toContainText('Sam Tan')
  await expect(entry.locator('.activity-meta')).toContainText('·') // "name · timestamp"
})

test('SCRUM-64 AC4: a decline with nobody to take over is still logged, and the event reads as unassigned', async ({ browser, request }) => {
  // Only Sam is in the pool: Priya steps out first.
  const priya = await openAs(browser, PRIYA)
  await priya.goto('/coordinator')
  await priya.getByRole('button', { name: 'Mark myself unavailable' }).click()
  await expect(priya.getByText('Unavailable', { exact: true })).toBeVisible()
  const eventId = await submittedByOlivia(request, 'Nobody else')
  const sam = await openAs(browser, SAM)

  await sam.goto('/coordinator/events')
  await sam.getByRole('button', { name: 'Decline this event' }).click()
  await expect(sam.getByText('Nothing assigned to you yet.')).toBeVisible()

  const olivia = await openAs(browser, OLIVIA)
  await olivia.goto(`/organiser/events/${eventId}`)
  await expect(olivia.getByText(/Not yet assigned/)).toBeVisible()
  await expect(olivia.locator('.activity-item', { hasText: 'declined this event' })).toContainText('Sam Tan')
})

// ---------------------------------------------------------------------------
// SCRUM-24 -- global unavailability
// ---------------------------------------------------------------------------

test('SCRUM-24 AC1 + AC4: going unavailable shows on the Coordinator page and profile until they return, and each change is logged with a time', async ({ browser }) => {
  const sam = await openAs(browser, SAM)
  await sam.goto('/coordinator')
  await expect(sam.getByText('Available', { exact: true })).toBeVisible()

  await sam.getByRole('button', { name: 'Mark myself unavailable' }).click()

  await expect(sam.getByText('Unavailable', { exact: true })).toBeVisible()
  await expect(sam.getByRole('button', { name: 'Mark myself available' })).toBeVisible()
  const history = sam.getByRole('list', { name: 'Availability history' })
  await expect(history.getByRole('listitem').first()).toContainText('Marked unavailable')
  await expect(history.getByRole('listitem').first().locator('.activity-meta')).not.toBeEmpty() // AC4: timestamp

  // AC1: it is still what the profile says after a reload, and on /profile.
  await sam.reload()
  await expect(sam.getByText('Unavailable', { exact: true })).toBeVisible()
  await sam.goto('/profile')
  await expect(sam.getByRole('region', { name: 'Availability' }).getByText('Unavailable', { exact: true })).toBeVisible()

  // ...until they mark themselves available again.
  await sam.goto('/coordinator')
  await sam.getByRole('button', { name: 'Mark myself available' }).click()
  await expect(sam.getByText('Available', { exact: true })).toBeVisible()
  await expect(history.getByRole('listitem')).toHaveCount(2)
  await expect(history.getByRole('listitem').first()).toContainText('Marked available') // newest first
  await sam.goto('/profile')
  await expect(sam.getByRole('region', { name: 'Availability' }).getByText('Available', { exact: true })).toBeVisible()
})

test('SCRUM-24 AC2 + AC3: an unavailable coordinator is left out of new assignments, but keeps what they hold, and rejoins when available', async ({ browser, request }) => {
  const heldId = await submittedByOlivia(request, 'Already held')
  const olivia = await openAs(browser, OLIVIA)
  const sam = await openAs(browser, SAM)

  // The pool, as the Organiser sees it: both coordinators.
  await olivia.goto('/organiser/events')
  await expect(olivia.getByText(/Coordinators currently available for assignment/)).toContainText('2')
  await olivia.getByText(/Coordinators currently available for assignment/).click()
  const pool = olivia.getByRole('list', { name: 'Coordinators in the assignment pool' })
  await expect(pool).toContainText('Sam Tan')
  await expect(pool).toContainText('Priya Nair')

  // Sam steps out.
  await sam.goto('/coordinator')
  await sam.getByRole('button', { name: 'Mark myself unavailable' }).click()
  await expect(sam.getByText('Unavailable', { exact: true })).toBeVisible()

  // AC2: out of the pool -- and the event Sam already held did not move.
  await olivia.reload()
  await expect(olivia.getByText(/Coordinators currently available for assignment/)).toContainText('1')
  await olivia.getByText(/Coordinators currently available for assignment/).click()
  await expect(pool).toContainText('Priya Nair')
  await expect(pool).not.toContainText('Sam Tan')
  const newId = await submittedByOlivia(request, 'Submitted while Sam is away')
  await olivia.goto(`/organiser/events/${newId}`)
  await expect(coordinatorCard(olivia).getByText('Priya Nair')).toBeVisible()
  await olivia.goto(`/organiser/events/${heldId}`)
  await expect(coordinatorCard(olivia).getByText('Sam Tan')).toBeVisible()
  await sam.goto('/coordinator/events')
  await expect(sam.getByText('Already held')).toBeVisible() // still Sam's, and still workable

  // AC3: Sam returns, and is back in the pool.
  await sam.goto('/coordinator')
  await sam.getByRole('button', { name: 'Mark myself available' }).click()
  await expect(sam.getByText('Available', { exact: true })).toBeVisible()
  await olivia.goto('/organiser/events')
  await expect(olivia.getByText(/Coordinators currently available for assignment/)).toContainText('2')
})

test('with nobody available the Organiser is told why: the count is 0 and a new request stays unassigned', async ({ browser, request }) => {
  for (const user of [SAM, PRIYA]) {
    const headers = await login(request, user.email, user.password)
    await request.patch(`${API}/coordinators/me/availability`, { data: { is_available: false }, headers })
  }
  const olivia = await openAs(browser, OLIVIA)

  await olivia.goto('/organiser/events')
  const line = olivia.getByTestId('available-coordinators')
  await expect(line).toContainText('available for assignment: 0')
  await expect(line).toContainText('new submissions will stay unassigned')

  const eventId = await submittedByOlivia(request, 'Nobody home')
  await olivia.goto(`/organiser/events/${eventId}`)
  await expect(olivia.getByText(/Not yet assigned/)).toBeVisible()
})

// ---------------------------------------------------------------------------
// SCRUM-28 -- the coordinator's full view of an assigned event
// ---------------------------------------------------------------------------

test('SCRUM-28 AC1-AC4: the assigned coordinator sees every requirement, the organiser’s contact, the status and the activity log', async ({ browser, request }) => {
  const eventId = await submittedByOlivia(request, 'Full details')
  const sam = await openAs(browser, SAM)

  await sam.goto('/coordinator/events')
  await sam.getByRole('link', { name: 'View details →' }).click()
  await expect(sam).toHaveURL(new RegExp(`/coordinator/events/${eventId}$`))

  await expect(sam.getByRole('heading', { name: 'Full details', level: 1 })).toBeVisible()
  const details = sam.locator('section', { has: sam.getByRole('heading', { name: 'Event Details' }) })
  for (const expected of [
    'Annual partner briefing', // purpose
    'A full-day briefing for our regional partners.', // description
    '120', // expected attendance
    'Main hall, stage, podium', // venue requirements
    'Step-free access, hearing loop', // accessibility needs
    '2 projectors, 4 radio mics', // equipment requirements
  ]) {
    await expect(details).toContainText(expected)
  }
  await expect(details).toContainText('Attendees must register') // registration needs

  const organiser = sam.locator('section', { has: sam.getByRole('heading', { name: 'Event Organiser' }) })
  await expect(organiser).toContainText('Olivia Organiser') // AC2
  await expect(organiser.getByRole('link', { name: OLIVIA.email })).toBeVisible()
  await expect(sam.getByText('Under review').first()).toBeVisible() // AC3
  await expect(sam.getByRole('list', { name: 'Activity log' })).toContainText('Assigned to Sam Tan.') // AC4
})

test('SCRUM-28 AC5: a coordinator cannot open an event that is assigned to someone else', async ({ browser, request }) => {
  const eventId = await submittedByOlivia(request, 'Not for Priya') // goes to Sam
  const priya = await openAs(browser, PRIYA)

  await priya.goto(`/coordinator/events/${eventId}`)

  await expect(priya.getByText('That event is not assigned to you.')).toBeVisible()
  await expect(priya.getByText('Not for Priya')).toHaveCount(0)
  await expect(priya.getByRole('heading', { name: 'Event Details' })).toHaveCount(0)
  await priya.goto('/coordinator/events')
  await expect(priya.getByText('Not for Priya')).toHaveCount(0)
})

// ---------------------------------------------------------------------------
// Keyboard: the pool dropdown (jsdom cannot do this -- only a real browser)
// ---------------------------------------------------------------------------

test('the coordinator dropdown opens and closes from the keyboard, with a visible focus indicator', async ({ browser }) => {
  const olivia = await openAs(browser, OLIVIA)
  await olivia.goto('/organiser/events')
  const summary = olivia.locator('details.pool-details > summary')
  const list = olivia.getByRole('list', { name: 'Coordinators in the assignment pool' })

  await summary.focus()
  await expect(summary).toBeFocused()
  const indicator = await summary.evaluate((el) => {
    const s = getComputedStyle(el)
    return { outline: s.outlineStyle, width: s.outlineWidth, shadow: s.boxShadow }
  })
  expect(indicator.outline !== 'none' || indicator.shadow !== 'none').toBe(true)

  await olivia.keyboard.press('Enter')
  await expect(list).toBeVisible()
  await olivia.keyboard.press('Space')
  await expect(list).toBeHidden()
})
