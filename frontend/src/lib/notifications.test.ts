import { describe, expect, it } from 'vitest'
import { notificationLink, parseSseChunk } from './notifications'
import type { Notification } from './notifications'

describe('parseSseChunk', () => {
  it('returns each complete data payload', () => {
    const { events, rest } = parseSseChunk('data: {"id":1}\n\ndata: {"id":2}\n\n')

    expect(events).toEqual(['{"id":1}', '{"id":2}'])
    expect(rest).toBe('')
  })

  it('keeps a half-received event for the next chunk', () => {
    const first = parseSseChunk('data: {"id":1}\n\ndata: {"id"')
    expect(first.events).toEqual(['{"id":1}'])

    const second = parseSseChunk(first.rest + ':2}\n\n')
    expect(second.events).toEqual(['{"id":2}'])
  })

  it('skips keep-alive comments and accepts CRLF line endings', () => {
    const { events } = parseSseChunk(': ping\r\n\r\ndata: {"id":3}\r\n\r\n')

    expect(events).toEqual(['{"id":3}'])
  })
})

describe('notificationLink', () => {
  const n: Notification = {
    id: 1,
    event_id: 7,
    type: 'event_assigned',
    message: 'x',
    is_read: false,
    created_at: '2026-09-29T00:00:00Z',
  }

  it("sends each role to its own event page", () => {
    expect(notificationLink(n, 'coordinator')).toBe('/coordinator/events/7')
    expect(notificationLink(n, 'organiser')).toBe('/organiser/events/7')
  })

  it('has no link without an event, or for roles with no event page', () => {
    expect(notificationLink({ ...n, event_id: null }, 'coordinator')).toBeNull()
    expect(notificationLink(n, 'attendee')).toBeNull()
  })
})
