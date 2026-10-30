import AxeBuilder from '@axe-core/playwright'
import { expect } from '@playwright/test'
import type { APIRequestContext, Browser, BrowserContextOptions, Page } from '@playwright/test'
import { call, login } from './api'
import type { SeedUser } from './db'
import { assignEventTo } from './db'

/**
 * Starting positions for the notification specs: an Event moved through the
 * real API by the people who would do it (Organiser, Coordinator, Venue
 * Staff, Technical Support). The notification each spec proves is what is
 * under test; these steps are not.
 *
 * Dates are relative to today, so the specs do not expire: the Event is 30
 * days away, 09:00-17:00 UTC.
 */

export type Headers = Record<string, string>

const DAY = 24 * 60 * 60 * 1000

/** 09:00 UTC (or `hour`) `days` from today, as an ISO string. */
export function inDays(days: number, hour = 9): string {
  const d = new Date(Date.now() + days * DAY)
  d.setUTCHours(hour, 0, 0, 0)
  return d.toISOString()
}

export const as = (request: APIRequestContext, who: SeedUser) => login(request, who.email, who.password)

/** A signed-in page for any role. support/openAs waits for the "Welcome
 *  back" landing page, which the Safety Officer does not have (they land on
 *  their queue), so this waits for the sign-in page to be left instead. */
export async function signedIn(browser: Browser, who: SeedUser, options: BrowserContextOptions = {}): Promise<Page> {
  const page = await (await browser.newContext(options)).newPage()
  await page.goto('/login')
  await page.getByLabel('Email').fill(who.email)
  await page.getByLabel('Password').fill(who.password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).not.toHaveURL(/\/login$/)
  return page
}

/** An approved Event of `org`'s, coordinated by `coord`. With `equipmentId`
 *  the Organiser also asked for 2 of that item. */
export async function approvedEvent(
  request: APIRequestContext,
  org: SeedUser,
  coord: SeedUser,
  name: string,
  equipmentId?: number,
): Promise<number> {
  const created = await call(
    request,
    'post',
    '/events',
    await as(request, org),
    {
      name,
      purpose: 'Annual partner briefing',
      event_type: 'conference',
      description: 'A full-day briefing.',
      proposed_start: inDays(30),
      proposed_end: inDays(30, 17),
      expected_attendance: 120,
      venue_requirements: 'Main hall',
      accessibility_needs: 'Step-free access',
      registration_enabled: false,
      equipment_items: equipmentId ? [{ equipment_id: equipmentId, quantity_requested: 2 }] : [],
    },
    201,
  )
  await call(request, 'post', `/events/${created.id}/submit`, await as(request, org))
  assignEventTo(created.id, coord.email)
  await call(request, 'post', `/events/${created.id}/approve`, await as(request, coord))
  return created.id as number
}

/** `venueName` requested by `coord` and approved by `staff`; with
 *  `equipmentId`, the Organiser's item reserved by `tech`. */
export async function arrange(
  request: APIRequestContext,
  eventId: number,
  people: { coord: SeedUser; staff: SeedUser; tech?: SeedUser },
  venueName: string,
  equipmentId?: number,
): Promise<void> {
  const coordH = await as(request, people.coord)
  const venues = await call(request, 'get', '/venues', coordH)
  const venue = venues.find((v: { name: string }) => v.name === venueName)
  const [booking] = await call(request, 'post', `/venue-bookings/events/${eventId}`, coordH, { venues: [{ venue_id: venue.id }] }, 201)
  await call(request, 'post', `/venue-bookings/${booking.id}/approve`, await as(request, people.staff))
  if (equipmentId && people.tech) {
    await call(request, 'post', '/equipment-reservations', await as(request, people.tech), {
      event_id: eventId,
      equipment_id: equipmentId,
    })
  }
}

/** Notifications page rows whose text includes `text`. */
export const notice = (page: Page, text: string | RegExp) => page.locator('.notif-row').filter({ hasText: text })

export async function expectNoSeriousViolations(page: Page, label: string) {
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))))
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze()
  const blocking = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
  expect(blocking.map((v) => `${v.impact} ${v.id}: ${v.help}`).join('\n'), label).toBe('')
}

/** Tab to `link` (it must be reachable), check it shows focus, and follow it. */
export async function tabToAndFollow(page: Page, link: ReturnType<Page['locator']>) {
  await expect(link).toBeVisible()
  let reached = false
  for (let i = 0; i < 30 && !reached; i++) {
    await page.keyboard.press('Tab')
    reached = await link.evaluate((el) => el === document.activeElement)
  }
  expect(reached, 'link not reachable by Tab').toBe(true)
  const visible = await link.evaluate((el) => {
    const s = getComputedStyle(el)
    return (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0) || s.boxShadow !== 'none'
  })
  expect(visible, 'no visible focus on the link').toBe(true)
  await page.keyboard.press('Enter')
}
