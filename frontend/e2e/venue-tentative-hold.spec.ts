import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'
import type { APIRequestContext } from '@playwright/test'
import { API, login, submitEvent } from './support/api'
import { OLIVIA, PASSWORD, SAM, openAs } from './support/coordinator-users'
import { removeUsers, removeVenue, resetUsers, seedUsers, seedVenue } from './support/db'
import type { SeedUser } from './support/db'

/**
 * Place a Tentative Hold on a Venue with an expiry, end to end (real browser,
 * real backend, real Postgres). Each title names the acceptance criteria it
 * proves; the rules themselves are backend/tests/test_venue_tentative_hold.py.
 *
 * Setup: an event is submitted (assigned to Sam), approved, and a venue
 * requested for it through the API -- the starting position, not the
 * behaviour under test.
 */
const VERA: SeedUser = { email: 'e2e_hold_vera@cs.local', name: 'Vera Staff', role: 'venue_staff', password: PASSWORD }
const USERS = [OLIVIA, SAM, VERA]
const EMAILS = USERS.map((u) => u.email)
const VENUE = 'E2E Hold Hall'
const ACTION = 'Confirm final headcount and pay the deposit'

test.beforeAll(() => {
  seedUsers(USERS)
  seedVenue({ name: VENUE, location: '3 Test Road', capacity: 500 })
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
  const venueId = venues.find((v) => v.name === VENUE)!.id
  const booked = await request.post(`${API}/venue-bookings/events/${eventId}`, {
    data: { venues: [{ venue_id: venueId }] },
    headers,
  })
  expect(booked.ok()).toBe(true)
  return { eventId, venueId, bookingId: (await booked.json())[0].id as number }
}

test('AC1 + AC4: Venue Staff hold a venue with an expiry and an action; calendar and Event show both', async ({ browser, request }) => {
  const { eventId, venueId } = await pendingRequest(request, 'Hold me')
  const vera = await openAs(browser, VERA)
  const sam = await openAs(browser, SAM)

  await vera.goto('/venue-staff/bookings')
  const card = vera.getByRole('region', { name: /Hold me/ })
  await card.getByRole('button', { name: 'Place tentative hold' }).click()
  await card.getByLabel('Hold expires').fill('2030-01-02T10:00')
  await card.getByLabel('Required action').fill(ACTION)
  await card.getByRole('button', { name: 'Confirm hold' }).click()
  await expect(vera.getByRole('status')).toContainText(`Tentative hold placed for ${VENUE}`)
  await expect(vera.getByRole('status')).toContainText(`Required action: ${ACTION}`)

  // Still awaiting a decision, now showing the hold.
  await vera.reload()
  await expect(card).toContainText('Hold expires')
  await expect(card).toContainText(ACTION)

  // AC4: on the availability calendar (Venue Staff see the action).
  await vera.goto(`/venues/${venueId}/availability`)
  await vera.getByLabel('From').fill('2026-11-02T00:00')
  await vera.getByLabel('Until').fill('2026-11-03T00:00')
  await vera.getByRole('button', { name: 'Check availability' }).click()
  const day = vera.getByRole('region', { name: /Availability on 2026-11-02/ })
  await expect(day).toContainText('Tentative hold')
  await expect(day).toContainText(`Required action: ${ACTION}`)

  // AC4: on the Event, for its Coordinator.
  await sam.goto(`/coordinator/events/${eventId}`)
  const bookings = sam.getByRole('region', { name: 'Venue bookings' })
  await expect(bookings).toContainText('Tentative hold')
  await expect(bookings).toContainText(`Required action: ${ACTION}`)
})

test('AC2: a missing or past expiry is not saved and the field is flagged', async ({ browser, request }) => {
  const { bookingId } = await pendingRequest(request, 'Bad expiry')
  const vera = await openAs(browser, VERA)
  await vera.goto('/venue-staff/bookings')
  const card = vera.getByRole('region', { name: /Bad expiry/ })
  await card.getByRole('button', { name: 'Place tentative hold' }).click()
  const expiry = card.getByLabel('Hold expires')

  await expiry.fill('')
  await card.getByLabel('Required action').fill(ACTION)
  await card.getByRole('button', { name: 'Confirm hold' }).click()
  await expect(expiry).toHaveAttribute('aria-invalid', 'true')
  await expect(expiry).toBeFocused()

  await expiry.fill('2020-01-01T10:00')
  await card.getByRole('button', { name: 'Confirm hold' }).click()
  await expect(card).toContainText('The expiry must be in the future.')

  // The server refuses it too, naming the field.
  const headers = await login(request, VERA.email, VERA.password)
  const res = await request.post(`${API}/venue-bookings/${bookingId}/hold`, {
    data: { expires_at: '2020-01-01T10:00:00Z', required_action: ACTION },
    headers,
  })
  expect(res.status()).toBe(422)
  expect((await res.json()).detail[0].loc).toEqual(['body', 'expires_at'])
  await vera.reload()
  await expect(card.getByRole('button', { name: 'Place tentative hold' })).toBeEnabled() // still pending
})

test('AC5: an approved hold becomes an approved Venue Booking', async ({ browser, request }) => {
  const { eventId, bookingId } = await pendingRequest(request, 'Hold then approve')
  const headers = await login(request, VERA.email, VERA.password)
  const held = await request.post(`${API}/venue-bookings/${bookingId}/hold`, {
    data: { expires_at: '2030-01-02T10:00:00Z', required_action: ACTION },
    headers,
  })
  expect(held.ok()).toBe(true)

  const vera = await openAs(browser, VERA)
  await vera.goto('/venue-staff/bookings')
  await vera.getByRole('region', { name: /Hold then approve/ }).getByRole('button', { name: 'Approve' }).click()
  await expect(vera.getByRole('status')).toContainText(`Approved: ${VENUE}`)

  const sam = await openAs(browser, SAM)
  await sam.goto(`/coordinator/events/${eventId}`)
  const bookings = sam.getByRole('region', { name: 'Venue bookings' })
  await expect(bookings).toContainText('Approved')
  await expect(bookings).not.toContainText('Required action')
})

test('accessibility: the hold form has no serious axe violations and works from the keyboard', async ({ browser, request }) => {
  await pendingRequest(request, 'A11y hold')
  const vera = await openAs(browser, VERA)
  await vera.goto('/venue-staff/bookings')
  const card = vera.getByRole('region', { name: /A11y hold/ })

  await card.getByRole('button', { name: 'Place tentative hold' }).focus()
  await vera.keyboard.press('Enter')
  await expect(card.getByLabel('Hold expires')).toBeFocused() // focus follows into the form
  // Tab walks the date/time segments of the native input first, then leaves it.
  const action = card.getByLabel('Required action')
  for (let i = 0; i < 8 && !(await action.evaluate((el) => el === document.activeElement)); i++) {
    await vera.keyboard.press('Tab')
  }
  await expect(action).toBeFocused()
  await vera.keyboard.press('Tab')
  await expect(card.getByRole('button', { name: 'Confirm hold' })).toBeFocused()
  await vera.keyboard.press('Enter') // blank action: flagged, focus moves to it
  await expect(card.getByLabel('Required action')).toBeFocused()
  await expect(card.getByLabel('Required action')).toHaveAttribute('aria-invalid', 'true')

  await vera.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))))
  const { violations } = await new AxeBuilder({ page: vera }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  expect(violations.filter((v) => v.impact === 'serious' || v.impact === 'critical').map((v) => v.id)).toEqual([])

  await vera.keyboard.type(ACTION)
  await vera.keyboard.press('Tab')
  await vera.keyboard.press('Enter')
  await expect(vera.getByRole('status')).toBeFocused() // not dropped when the card goes
  await expect(vera.getByRole('status')).toContainText('Tentative hold placed')
})
