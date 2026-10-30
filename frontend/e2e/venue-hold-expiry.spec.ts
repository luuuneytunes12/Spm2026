import { E2E_TEST_YEAR } from './support/dates'
import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { APIRequestContext } from '@playwright/test'
import { API, login, submitEvent } from './support/api'
import { OLIVIA, PASSWORD, SAM, openAs } from './support/coordinator-users'
import { lapseHold, removeUsers, removeVenue, resetUsers, seedUsers, seedVenue } from './support/db'
import type { SeedUser } from './support/db'

/**
 * Tentative hold expiry, end to end (real browser, real backend, real
 * Postgres). The reminder timing is backend/tests/test_venue_hold_expiry.py;
 * this proves what the Coordinator and Venue Staff see once a hold lapses.
 *
 * Setup: an approved event of Sam's with a request for VENUE, put on hold by
 * Venue Staff through the API; the hold's expiry is then moved into the past.
 */
const VERA: SeedUser = { email: 'e2e_expiry_vera@cs.local', name: 'Vera Staff', role: 'venue_staff', password: PASSWORD }
const USERS = [OLIVIA, SAM, VERA]
const EMAILS = USERS.map((u) => u.email)
const VENUE = 'E2E Expiry Hall'

test.beforeAll(() => {
  seedUsers(USERS)
  seedVenue({ name: VENUE, location: '4 Test Road', capacity: 500 })
})
test.beforeEach(() => resetUsers(EMAILS))
test.afterAll(() => {
  removeUsers(EMAILS)
  removeVenue(VENUE)
})

async function lapsedHold(request: APIRequestContext, name: string) {
  const eventId = await submitEvent(request, await login(request, OLIVIA.email, OLIVIA.password), name)
  const headers = await login(request, SAM.email, SAM.password)
  expect((await request.post(`${API}/events/${eventId}/approve`, { headers })).ok()).toBe(true)
  const venues: { id: number; name: string }[] = await (await request.get(`${API}/venues`, { headers })).json()
  const booked = await request.post(`${API}/venue-bookings/events/${eventId}`, {
    data: { venues: [{ venue_id: venues.find((v) => v.name === VENUE)!.id }] },
    headers,
  })
  const bookingId = (await booked.json())[0].id as number
  const staff = await login(request, VERA.email, VERA.password)
  const held = await request.post(`${API}/venue-bookings/${bookingId}/hold`, {
    data: { expires_at: `${E2E_TEST_YEAR - 1}-01-02T10:00:00Z`, required_action: 'Pay the deposit' },
    headers: staff,
  })
  expect(held.ok()).toBe(true)
  lapseHold(bookingId)
  return { eventId, bookingId }
}

test('AC2 + AC3 + AC4: a lapsed hold shows as expired, never confirmed, and both sides are told', async ({ browser, request }) => {
  const { eventId } = await lapsedHold(request, 'Lapsed hold')
  const sam = await openAs(browser, SAM)

  await sam.goto(`/coordinator/events/${eventId}`)
  const bookings = sam.getByRole('region', { name: 'Venue bookings' })
  await expect(bookings).toContainText(/Hold expired/i) // AC2
  await expect(bookings).toContainText('Request it again or choose another venue.')
  await expect(bookings.getByText('Approved', { exact: true })).toHaveCount(0) // AC4
  await expect(sam.getByRole('checkbox', { name: new RegExp(VENUE) })).toBeEnabled() // the venue is free again
  // AC4: in the history. The page read its activity before this load's
  // booking request expired the hold, so read it again.
  await sam.reload()
  await expect(sam.getByText(`Tentative hold on '${VENUE}' expired.`)).toBeVisible()

  // AC3: both are told.
  for (const who of [SAM, VERA]) {
    const headers = await login(request, who.email, who.password)
    const notes: { type: string }[] = await (await request.get(`${API}/notifications`, { headers })).json()
    expect(notes.some((n) => n.type === 'venue_hold_expired')).toBe(true)
  }
})

test('accessibility: the expired hold on the Event page has no serious axe violations', async ({ browser, request }) => {
  const { eventId } = await lapsedHold(request, 'A11y lapsed hold')
  const sam = await openAs(browser, SAM)
  await sam.goto(`/coordinator/events/${eventId}`)
  await expect(sam.getByRole('region', { name: 'Venue bookings' })).toContainText(/Hold expired/i)

  await sam.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))))
  const { violations } = await new AxeBuilder({ page: sam }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  expect(violations.filter((v) => v.impact === 'serious' || v.impact === 'critical').map((v) => v.id)).toEqual([])
})
