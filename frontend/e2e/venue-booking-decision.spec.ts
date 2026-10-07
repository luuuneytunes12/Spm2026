import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { APIRequestContext } from '@playwright/test'
import { API, login, submitEvent } from './support/api'
import { OLIVIA, PASSWORD, SAM, openAs } from './support/coordinator-users'
import { removeUsers, removeVenue, resetUsers, seedUsers, seedVenue } from './support/db'
import type { SeedUser } from './support/db'

/**
 * Approve or Reject Venue Booking Request, end to end (real browser, real
 * backend, real Postgres). Each title names the acceptance criteria it proves.
 *
 * Setup: an event is submitted (assigned to Sam), approved, and a venue
 * requested for it through the API -- that is the starting position
 * (SCRUM-39), not the behaviour under test.
 */
const VERA: SeedUser = { email: 'e2e_vera@cs.local', name: 'Vera Staff', role: 'venue_staff', password: PASSWORD }
const USERS = [OLIVIA, SAM, VERA]
const EMAILS = USERS.map((u) => u.email)
const VENUE = 'E2E Decision Hall'

test.beforeAll(() => {
  seedUsers(USERS)
  seedVenue({ name: VENUE, location: '2 Test Road', capacity: 500 })
})
test.beforeEach(() => resetUsers(EMAILS))
test.afterAll(() => {
  removeUsers(EMAILS)
  removeVenue(VENUE)
})

/** An approved event of Sam's with a pending request for VENUE. */
async function pendingRequest(request: APIRequestContext, name: string) {
  const eventId = await submitEvent(request, await login(request, OLIVIA.email, OLIVIA.password), name)
  const headers = await login(request, SAM.email, SAM.password)
  expect((await request.post(`${API}/events/${eventId}/approve`, { headers })).ok()).toBe(true)
  const venues: { id: number; name: string }[] = await (await request.get(`${API}/venues`, { headers })).json()
  const booked = await request.post(`${API}/venue-bookings/events/${eventId}`, {
    data: { venue_id: venues.find((v) => v.name === VENUE)!.id },
    headers,
  })
  expect(booked.ok()).toBe(true)
  return { eventId, bookingId: (await booked.json()).id as number }
}

test('AC1 + AC2 + AC4: Venue Staff approve a queued request and the Coordinator sees the outcome', async ({ browser, request }) => {
  const { eventId } = await pendingRequest(request, 'Approve me')
  const vera = await openAs(browser, VERA)
  const sam = await openAs(browser, SAM)

  await vera.goto('/venue-staff/bookings')
  const card = vera.getByRole('region', { name: /Approve me/ })
  await expect(card).toBeVisible() // AC1
  await expect(card.getByRole('button', { name: 'Reject' })).toBeVisible() // AC2: either decision
  await card.getByRole('button', { name: 'Approve' }).click()
  await expect(vera.getByRole('status')).toContainText(`Approved: ${VENUE}`)
  await expect(card).toHaveCount(0)
  await vera.reload() // decided for good, not just on screen
  await expect(vera.getByText('No pending booking requests.')).toBeVisible()

  await sam.goto(`/coordinator/events/${eventId}`) // AC4
  await expect(sam.getByRole('region', { name: 'Venue booking' }).getByRole('status')).toContainText(VENUE)
  await expect(sam.getByRole('region', { name: 'Venue booking' }).getByRole('status')).toContainText('Approved')
  await expect(sam.getByRole('region', { name: 'Venue booking' }).getByRole('status')).toContainText('Vera Staff')
  await expect(sam.getByRole('button', { name: 'Submit booking request' })).toHaveCount(0)
})

test('AC2 + AC3 + AC4 + AC5: a rejection carries a reason and an alternative, and the request can be resubmitted again and again', async ({ browser, request }) => {
  const { eventId } = await pendingRequest(request, 'Reject me')
  const vera = await openAs(browser, VERA)
  const sam = await openAs(browser, SAM)
  const card = vera.getByRole('region', { name: /Reject me/ })

  const resubmit = async () => {
    const value = await sam.locator('option', { hasText: VENUE }).getAttribute('value')
    await sam.getByRole('combobox', { name: /^Venue/ }).selectOption(value!)
    await sam.getByRole('button', { name: 'Submit booking request' }).click()
    await expect(sam.getByRole('region', { name: 'Venue booking' }).getByRole('status')).toContainText('Pending review')
  }

  // Round 1: rejected with both a reason and an alternative.
  await vera.goto('/venue-staff/bookings')
  await card.getByRole('button', { name: 'Reject' }).click()
  await card.getByLabel('Reason').fill('Closed for repairs that week.')
  await card.getByLabel('Suggested alternative').fill('The Annex is free on the same day.')
  await card.getByRole('button', { name: 'Confirm rejection' }).click()
  await expect(vera.getByRole('status')).toContainText(`Rejected: ${VENUE}`)
  await expect(card).toHaveCount(0)

  await sam.goto(`/coordinator/events/${eventId}`)
  await expect(sam.getByRole('region', { name: 'Venue booking' }).getByRole('status')).toContainText('Rejected') // AC4
  await expect(sam.getByRole('region', { name: 'Venue booking' }).getByRole('status')).toContainText('Closed for repairs that week.') // AC3
  await expect(sam.getByRole('region', { name: 'Venue booking' }).getByRole('status')).toContainText('The Annex is free on the same day.')
  await expect(sam.getByRole('region', { name: 'Venue booking' }).getByRole('status')).toContainText('Vera Staff')
  await resubmit() // AC5

  // Round 2: back in the queue; rejected with an alternative alone.
  await vera.reload()
  await expect(card).toBeVisible()
  await card.getByRole('button', { name: 'Reject' }).click()
  await card.getByLabel('Suggested alternative').fill('Try the following Monday.')
  await card.getByRole('button', { name: 'Confirm rejection' }).click()
  await expect(card).toHaveCount(0)

  await sam.reload()
  await expect(sam.getByRole('region', { name: 'Venue booking' }).getByRole('status')).toContainText('Try the following Monday.')
  await expect(sam.getByRole('listitem').filter({ hasText: 'Closed for repairs that week.' })).toBeVisible() // history kept
  await resubmit() // AC5, a second time

  // Round 3: back in the queue once more, and this time approved.
  await vera.reload()
  await card.getByRole('button', { name: 'Approve' }).click()
  await expect(vera.getByRole('status')).toContainText(`Approved: ${VENUE}`)
  await sam.reload()
  await expect(sam.getByRole('region', { name: 'Venue booking' }).getByRole('status')).toContainText('Approved')
  await expect(sam.getByRole('listitem').filter({ hasText: 'Rejected' })).toHaveCount(2)
})

test('negative: a Coordinator cannot decide on a booking request', async ({ browser, request }) => {
  const { bookingId } = await pendingRequest(request, 'Not yours to decide')
  const headers = await login(request, SAM.email, SAM.password)
  expect((await request.post(`${API}/venue-bookings/${bookingId}/approve`, { headers })).status()).toBe(403)
  const rejected = await request.post(`${API}/venue-bookings/${bookingId}/reject`, { data: { reason: 'No.' }, headers })
  expect(rejected.status()).toBe(403)

  const vera = await openAs(browser, VERA)
  await vera.goto('/venue-staff/bookings')
  await expect(vera.getByRole('region', { name: /Not yours to decide/ })).toBeVisible() // still pending
})

test('accessibility: the decision controls have no serious axe violations and work from the keyboard', async ({ browser, request }) => {
  await pendingRequest(request, 'A11y decision')
  const vera = await openAs(browser, VERA)
  await vera.goto('/venue-staff/bookings')
  const card = vera.getByRole('region', { name: /A11y decision/ })

  await card.getByRole('button', { name: 'Approve' }).focus()
  await vera.keyboard.press('Tab')
  await expect(card.getByRole('button', { name: 'Reject' })).toBeFocused()
  await vera.keyboard.press('Enter')
  await expect(card.getByLabel('Reason')).toBeFocused() // focus follows into the form

  await vera.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))))
  const { violations } = await new AxeBuilder({ page: vera }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  expect(violations.filter((v) => v.impact === 'serious' || v.impact === 'critical').map((v) => v.id)).toEqual([])

  await vera.keyboard.type('Closed for repairs.')
  await vera.keyboard.press('Tab')
  await expect(card.getByLabel('Suggested alternative')).toBeFocused()
  await vera.keyboard.press('Tab')
  await expect(card.getByRole('button', { name: 'Confirm rejection' })).toBeFocused()
  await vera.keyboard.press('Enter')
  await expect(vera.getByRole('status')).toBeFocused() // not dropped when the card goes
  await expect(vera.getByRole('status')).toContainText('Rejected')
})
