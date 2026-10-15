import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { BookingCalendar, type CalendarBlock } from './BookingCalendar'

// Local-time ISO helpers (Mon 5 Oct 2026 week; Mon 12 Oct next week).
const iso = (d: number, h: number, m = 0) => new Date(2026, 9, d, h, m).toISOString()

const base: CalendarBlock = {
  id: 'a', label: 'Hackathon', start: iso(7, 8), end: iso(7, 18),
  eventStart: iso(7, 9), eventEnd: iso(7, 17), kind: 'request', conflict: false,
}
const nextWeek: CalendarBlock = { ...base, id: 'b', label: 'Gala', start: iso(14, 8), end: iso(14, 18), eventStart: iso(14, 9), eventEnd: iso(14, 17), kind: 'existing' }

describe('BookingCalendar', () => {
  it('renders blocks only in the displayed week with event time', () => {
    render(<BookingCalendar blocks={[base, nextWeek]} selectedId={null} onSelect={() => {}} focusDate={iso(7, 12)} />)
    expect(screen.getByRole('button', { name: 'Hackathon, occupied 08:00–18:00, event 09:00–17:00' })).toBeInTheDocument()
    expect(screen.queryByText('Gala')).toBeNull()
    expect(screen.getByText('5 Oct – 11 Oct 2026')).toBeInTheDocument()
  })

  it('navigates weeks', () => {
    render(<BookingCalendar blocks={[base, nextWeek]} selectedId={null} onSelect={() => {}} focusDate={iso(7, 12)} />)
    fireEvent.click(screen.getByRole('button', { name: 'Next week' }))
    expect(screen.getByText('Gala')).toBeInTheDocument()
    expect(screen.queryByText('Hackathon')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Previous week' }))
    expect(screen.getByText('Hackathon')).toBeInTheDocument()
  })

  it('calls onSelect and marks selection', () => {
    const onSelect = vi.fn()
    render(<BookingCalendar blocks={[base]} selectedId="a" onSelect={onSelect} focusDate={iso(7, 12)} />)
    const btn = screen.getByRole('button', { name: /Hackathon/ })
    expect(btn).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(btn)
    expect(onSelect).toHaveBeenCalledWith('a')
  })

  it('flags conflicts with a glyph and accessible name, plus a legend', () => {
    render(<BookingCalendar blocks={[{ ...base, conflict: true }]} selectedId={null} onSelect={() => {}} focusDate={iso(7, 12)} />)
    expect(screen.getByText('!')).toBeInTheDocument()
    expect(screen.getAllByText('Conflict')).toHaveLength(1) // legend only
    expect(screen.getByRole('button', { name: 'Hackathon, occupied 08:00–18:00, event 09:00–17:00, conflict' })).toBeInTheDocument()
  })

  it('clips multi-day blocks per day with continuation markers', () => {
    const m = { ...base, start: iso(7, 20), end: iso(8, 10), eventStart: iso(7, 20), eventEnd: iso(8, 10) }
    render(<BookingCalendar blocks={[m]} selectedId={null} onSelect={() => {}} focusDate={iso(7, 12)} />)
    const btns = screen.getAllByRole('button', { name: /Hackathon/ })
    expect(btns).toHaveLength(2)
    expect(btns[0]).toHaveClass('cont-down')
    expect(btns[1]).toHaveClass('cont-up')
    expect(btns[0]).toHaveAttribute('title', expect.stringContaining('7 Oct 20:00 – 8 Oct 10:00'))
  })

  it('renders ONE block per booking with in-block setup and turnaround markers and the event time', () => {
    render(<BookingCalendar blocks={[base]} selectedId={null} onSelect={() => {}} focusDate={iso(7, 12)} />)
    expect(screen.getAllByRole('button', { name: /Hackathon/ })).toHaveLength(1)
    const btn = screen.getByRole('button', { name: /Hackathon/ })
    expect(screen.getByTestId('block-setup')).toHaveTextContent('Setup')
    expect(screen.getByTestId('block-turnaround')).toHaveTextContent('Turnaround')
    expect(btn).toContainElement(screen.getByTestId('block-setup'))
    expect(btn).toContainElement(screen.getByTestId('block-turnaround'))
    expect(btn).toHaveTextContent('Event 09:00–17:00')
    expect(screen.getByTestId('block-setup')).toHaveStyle({ height: '48px' })
  })

  it('shows no markers when the event fills the occupied window', () => {
    render(<BookingCalendar blocks={[{ ...base, eventStart: base.start, eventEnd: base.end }]} selectedId={null} onSelect={() => {}} focusDate={iso(7, 12)} />)
    expect(screen.queryByTestId('block-setup')).toBeNull()
    expect(screen.queryByTestId('block-turnaround')).toBeNull()
    expect(screen.getByRole('button', { name: /Hackathon/ })).toHaveTextContent('08:00–18:00')
  })

  it('hatches short buffers without text', () => {
    render(<BookingCalendar blocks={[{ ...base, eventStart: iso(7, 8, 10), eventEnd: iso(7, 17, 50) }]} selectedId={null} onSelect={() => {}} focusDate={iso(7, 12)} />)
    expect(screen.getByTestId('block-setup')).toBeEmptyDOMElement()
    expect(screen.getByTestId('block-turnaround')).toBeEmptyDOMElement()
  })

  it('navigates when focusDate changes', () => {
    const { rerender } = render(<BookingCalendar blocks={[base, nextWeek]} selectedId={null} onSelect={() => {}} focusDate={iso(7, 12)} />)
    expect(screen.queryByText('Gala')).toBeNull()
    rerender(<BookingCalendar blocks={[base, nextWeek]} selectedId={null} onSelect={() => {}} focusDate={iso(15, 12)} />)
    expect(screen.getByText('Gala')).toBeInTheDocument()
  })

  it('lays overlapping blocks side by side', () => {
    const o = { ...base, id: 'o', label: 'Other' }
    render(<BookingCalendar blocks={[base, o]} selectedId={null} onSelect={() => {}} focusDate={iso(7, 12)} />)
    const a = screen.getByRole('button', { name: /Hackathon/ })
    const c = screen.getByRole('button', { name: /Other/ })
    expect(a.style.width).toContain('50%')
    expect(c.style.left).not.toBe(a.style.left)
    const onSelect = vi.fn()
    cleanup()
    render(<BookingCalendar blocks={[base, o]} selectedId={null} onSelect={onSelect} focusDate={iso(7, 12)} />)
    fireEvent.click(screen.getByRole('button', { name: /Other/ }))
    fireEvent.click(screen.getByRole('button', { name: /Hackathon/ }))
    expect(onSelect).toHaveBeenNthCalledWith(1, 'o')
    expect(onSelect).toHaveBeenNthCalledWith(2, 'a')
  })

  it('marks approved blocks with class and accessible text', () => {
    render(<BookingCalendar blocks={[{ ...base, kind: 'existing', approved: true, conflict: true }]} selectedId={null} onSelect={() => {}} focusDate={iso(7, 12)} />)
    const btn = screen.getByRole('button', { name: /, conflict, approved$/ })
    expect(btn).toHaveClass('is-approved')
    expect(btn).toHaveAttribute('title', expect.stringContaining(', approved'))
    expect(btn.textContent).toContain('!')
  })

  it('renders an unavailable block with its reason, grey class, no buffers, and is clickable', () => {
    const onSelect = vi.fn()
    const u: CalendarBlock = { ...base, id: 'u', label: 'Maintenance: pipe repair', kind: 'unavailable' }
    render(<BookingCalendar blocks={[u]} selectedId={null} onSelect={onSelect} focusDate={iso(7, 12)} />)
    const btn = screen.getByRole('button', { name: /Maintenance: pipe repair/ })
    expect(btn).toHaveTextContent('Maintenance: pipe repair')
    expect(btn).toHaveClass('k-unavailable')
    expect(btn).toHaveAttribute('aria-label', expect.stringContaining('Maintenance: pipe repair'))
    expect(screen.queryByTestId('block-setup')).toBeNull()
    expect(screen.queryByTestId('block-turnaround')).toBeNull()
    fireEvent.click(btn)
    expect(onSelect).toHaveBeenCalledWith('u')
  })
})
