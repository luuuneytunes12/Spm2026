import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import { API, login, submitEvent } from './support/api'
import { OLIVIA, PASSWORD, SAM, openAs } from './support/coordinator-users'
import { removeUsers, removeVenue, resetUsers, seedUsers, seedVenue } from './support/db'
import type { SeedUser } from './support/db'

/**
 * SCRUM-39 Submit Venue Booking Request, end to end (real browser, real
 * backend, real Postgres). Each title names the acceptance criterion it proves.
 *
 * Setup: an event is submitted (assigned to Sam) and approved through the API
 * -- that is the starting position, not the behaviour under test.
 */
const VERA: SeedUser = { email: 'e2e_vera@cs.local', name: 'Vera Staff', role: 'venue_staff', password: PASSWORD }
const USERS = [OLIVIA, SAM, VERA]
const EMAILS = USERS.map((u) => u.email)
const VENUE = 'E2E Test Hall'

test.beforeAll(() => {
  seedUsers(USERS)
  seedVenue({ name: VENUE, location: '1 Test Road', capacity: 500 })
})
test.beforeEach(() => resetUsers(EMAILS))
test.afterAll(() => {
  removeUsers(EMAILS)
  removeVenue(VENUE)
})

async function approvedEvent(request: import('@playwright/test').APIRequestContext, name: string) {
  const eventId = await submitEvent(request, await login(request, OLIVIA.email, OLIVIA.password), name)
  const approved = await request.post(`${API}/events/${eventId}/approve`, {
    headers: await login(request, SAM.email, SAM.password),
  })
  expect(approved.ok()).toBe(true)
  return eventId
}

test('SCRUM-39: no venue card while the event is still awaiting review', async ({ browser, request }) => {
  const eventId = await submitEvent(request, await login(request, OLIVIA.email, OLIVIA.password), 'Pending review')
  const sam = await openAs(browser, SAM)
  await sam.goto(`/coordinator/events/${eventId}`)
  await expect(sam.getByRole('heading', { name: 'Event Details' })).toBeVisible()
  await expect(sam.getByRole('heading', { name: 'Venue bookings' })).toHaveCount(0)
})

test('SCRUM-39 AC1: submitting with no venue selected shows an error and creates nothing', async ({ browser, request }) => {
  const eventId = await approvedEvent(request, 'AC1 event')
  const sam = await openAs(browser, SAM)
  const vera = await openAs(browser, VERA)

  await sam.goto(`/coordinator/events/${eventId}`)
  await sam.getByRole('button', { name: 'Submit booking request' }).click()
  await expect(sam.getByRole('alert')).toContainText('Select a venue')

  await vera.goto('/venue-staff/bookings')
  await expect(vera.getByText('No pending booking requests.')).toBeVisible()
})

test('SCRUM-39 AC2 + AC3: a submitted request appears in the Venue Staff queue carrying everything', async ({ browser, request }) => {
  const eventId = await approvedEvent(request, 'AC2 event')
  const sam = await openAs(browser, SAM)
  const vera = await openAs(browser, VERA)

  await sam.goto(`/coordinator/events/${eventId}`)
  await sam.getByRole('checkbox', { name: new RegExp(VENUE) }).check()
  await sam.getByLabel(`Facilities for ${VENUE}`).fill('Two radio microphones') // needs entered for that venue
  await sam.getByRole('button', { name: 'Submit booking request' }).click()
  const bookings = sam.getByRole('region', { name: 'Venue bookings' })
  await expect(bookings).toContainText(VENUE) // AC2 (coordinator side)
  await expect(bookings).toContainText('Pending review')
  // SCRUM-39 AC3: the first booking moves the event on, and the page shows it without a reload.
  await expect(sam.getByRole('heading', { level: 1 }).locator('..').locator('.badge')).toHaveText('Planning Event')
  await sam.reload() // persisted, not just on screen
  await expect(bookings).toContainText(VENUE)
  await expect(sam.getByRole('checkbox', { name: /already requested/ })).toBeDisabled() // no duplicate

  await vera.goto('/venue-staff/bookings')
  const card = vera.getByRole('region', { name: /AC2 event/ })
  await expect(card).toBeVisible() // AC2
  await expect(card).toContainText(VENUE) // AC3
  await expect(card).toContainText('120')
  await expect(card).toContainText('Step-free access, hearing loop')
  await expect(card).toContainText('Two radio microphones') // the facilities entered for this venue
  await expect(card).toContainText('Sam Tan')
})

test('SCRUM-39 negative: a Coordinator cannot open the Venue Staff queue', async ({ browser }) => {
  const sam = await openAs(browser, SAM)
  await sam.goto('/venue-staff/bookings')
  await expect(sam).toHaveURL(/forbidden/)
})

test('SCRUM-39 accessibility: the booking card has no serious axe violations and its fields are labelled', async ({ browser, request }) => {
  const eventId = await approvedEvent(request, 'A11y event')
  const sam = await openAs(browser, SAM)
  await sam.goto(`/coordinator/events/${eventId}`)
  await expect(sam.getByRole('checkbox', { name: new RegExp(VENUE) })).toBeVisible()
  await sam.getByRole('checkbox', { name: new RegExp(VENUE) }).check()
  await expect(sam.getByLabel(`Room layout for ${VENUE}`)).toBeVisible() // fields are labelled
  await sam.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))))
  const { violations } = await new AxeBuilder({ page: sam }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  expect(violations.filter((v) => v.impact === 'serious' || v.impact === 'critical').map((v) => v.id)).toEqual([])

  // Keyboard: a venue is chosen with Space, and the submit button is reachable.
  await sam.getByRole('checkbox', { name: new RegExp(VENUE) }).uncheck()
  await sam.getByRole('checkbox', { name: new RegExp(VENUE) }).focus()
  await sam.keyboard.press('Space')
  await expect(sam.getByRole('checkbox', { name: new RegExp(VENUE) })).toBeChecked()
  await sam.getByRole('button', { name: 'Submit booking request' }).focus()
  await expect(sam.getByRole('button', { name: 'Submit booking request' })).toBeFocused()
})
