import { expect } from '@playwright/test'
import type { Browser, BrowserContextOptions, Page } from '@playwright/test'
import type { SeedUser } from './db'

/**
 * The three accounts the coordinator specs share: Olivia (Organiser) and
 * Sam Tan and Priya Nair (Coordinators). They are created before a spec and
 * removed after it -- see support/db.ts -- so they never linger in the
 * assignment pool for the specs that follow. Sam is created first, so when
 * both carry the same load Sam is the one picked.
 */
export const PASSWORD = 'e2e-story-password-123'
export const OLIVIA: SeedUser = { email: 'e2e_olivia@cs.local', name: 'Olivia Organiser', role: 'organiser', password: PASSWORD }
export const SAM: SeedUser = { email: 'e2e_sam@cs.local', name: 'Sam Tan', role: 'coordinator', password: PASSWORD }
export const PRIYA: SeedUser = { email: 'e2e_priya@cs.local', name: 'Priya Nair', role: 'coordinator', password: PASSWORD }
export const USERS = [OLIVIA, SAM, PRIYA]
export const EMAILS = USERS.map((u) => u.email)

/** A signed-in page for `user`, in its own browser context so several people
 *  can be on screen at once. */
export async function openAs(
  browser: Browser,
  user: SeedUser,
  options: BrowserContextOptions = {},
): Promise<Page> {
  const page = await (await browser.newContext(options)).newPage()
  await page.goto('/login')
  await page.getByLabel('Email').fill(user.email)
  await page.getByLabel('Password').fill(user.password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: /Welcome back/ })).toBeVisible()
  return page
}
