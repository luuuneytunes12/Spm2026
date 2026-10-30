/**
 * Unit tests for the event client's request shapes.
 *
 * FastAPI parses a body as JSON only when it is labelled application/json;
 * without the header the browser sends text/plain and the server answers
 * 422 "Input should be a valid dictionary or object to extract fields from".
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { editPlanningEvent } from './events'

vi.mock('./api', async () => {
  const actual = await vi.importActual<typeof import('./api')>('./api')
  return { ...actual, apiFetch: vi.fn() }
})

import { apiFetch } from './api'

const mockFetch = vi.mocked(apiFetch)

beforeEach(() => {
  mockFetch.mockReset()
  mockFetch.mockResolvedValue({})
})

describe('editPlanningEvent', () => {
  it('sends the changes as a JSON PATCH to the assigned planning endpoint', async () => {
    await editPlanningEvent(7, { name: 'Orientation Day', expected_attendance: 120 })

    expect(mockFetch).toHaveBeenCalledWith('/events/assigned/7/planning', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'Orientation Day', expected_attendance: 120 }),
    })
  })
})
