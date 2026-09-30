import type { APIRequestContext } from '@playwright/test'
import { E2E_API_PORT } from '../../playwright.config'

/** The e2e backend, for setup that is not what the spec is about. The specs
 *  drive the screens for the behaviour under test; creating and submitting an
 *  event first is just the arrival at the starting position, and doing it
 *  through the API keeps these specs from breaking whenever the request form
 *  is redesigned. */
export const API = `http://localhost:${E2E_API_PORT}`

const COMPLETE = {
  name: 'Regional Partner Conference',
  purpose: 'Annual partner briefing',
  event_type: 'conference',
  description: 'A full-day briefing for our regional partners.',
  proposed_start: '2026-11-02T09:00:00Z',
  proposed_end: '2026-11-02T17:00:00Z',
  expected_attendance: 120,
  venue_requirements: 'Main hall, stage, podium',
  accessibility_needs: 'Step-free access, hearing loop',
  equipment_requirements: '2 projectors, 4 radio mics',
  registration_enabled: true,
}

export async function login(
  request: APIRequestContext,
  email: string,
  password: string,
): Promise<Record<string, string>> {
  const res = await request.post(`${API}/auth/login`, { data: { email, password } })
  if (!res.ok()) throw new Error(`login failed for ${email}: ${res.status()} ${await res.text()}`)
  const { access_token } = await res.json()
  return { Authorization: `Bearer ${access_token}` }
}

/** Create a complete request and submit it; returns the event id. */
export async function submitEvent(
  request: APIRequestContext,
  headers: Record<string, string>,
  name = COMPLETE.name,
): Promise<number> {
  const created = await request.post(`${API}/events`, { data: { ...COMPLETE, name }, headers })
  if (!created.ok()) throw new Error(`create failed: ${created.status()} ${await created.text()}`)
  const { id } = await created.json()
  const submitted = await request.post(`${API}/events/${id}/submit`, { headers })
  if (!submitted.ok()) throw new Error(`submit failed: ${submitted.status()} ${await submitted.text()}`)
  return id
}
