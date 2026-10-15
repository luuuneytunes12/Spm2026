import { useEffect, useMemo, useRef, useState } from 'react'
import './BookingCalendar.css'

export interface CalendarBlock {
  id: string
  label: string
  start: string
  end: string
  eventStart: string
  eventEnd: string
  kind: 'request' | 'existing' | 'unavailable'
  conflict: boolean
  approved?: boolean
}
export interface BookingCalendarProps {
  blocks: CalendarBlock[]
  selectedId: string | null
  onSelect: (id: string) => void
  focusDate?: string
}

const HOUR_PX = 48
const MIN_SEG_PX = 22
const BUFFER_TEXT_PX = 13
const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

function mondayOf(d: Date): Date {
  const m = new Date(d.getFullYear(), d.getMonth(), d.getDate())
  m.setDate(m.getDate() - ((m.getDay() + 6) % 7))
  return m
}
function addDays(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n)
}
const pad = (n: number) => String(n).padStart(2, '0')
function hhmm(ms: number): string {
  const d = new Date(ms)
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`
}
function fmtRange(a: number, z: number): string {
  const f = (ms: number) =>
    `${new Date(ms).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })} ${hhmm(ms)}`
  return `${f(a)} – ${f(z)}`
}
function weekTitle(mon: Date): string {
  const sun = addDays(mon, 6)
  const f = (d: Date, y: boolean) =>
    d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', ...(y ? { year: 'numeric' } : {}) })
  return `${f(mon, false)} – ${f(sun, true)}`
}

interface Seg {
  block: CalendarBlock
  s: number // ms
  e: number
  top: number
  height: number
  lane: number
  lanes: number
}

function layoutDay(blocks: CalendarBlock[], day: Date): Seg[] {
  const dayS = day.getTime()
  const dayE = addDays(day, 1).getTime()
  const segs: Seg[] = []
  for (const block of blocks) {
    const bs = new Date(block.start).getTime()
    const be = new Date(block.end).getTime()
    const s = Math.max(bs, dayS)
    const e = Math.min(be, dayE)
    if (!(e > s) || Number.isNaN(bs) || Number.isNaN(be)) continue
    const top = ((s - dayS) / 60000 / 60) * HOUR_PX
    const height = Math.max(((e - s) / 60000 / 60) * HOUR_PX, MIN_SEG_PX)
    segs.push({ block, s, e, top, height, lane: 0, lanes: 1 })
  }
  segs.sort((a, b) => a.top - b.top || b.height - a.height)
  let cluster: Seg[] = []
  let clusterEnd = -Infinity
  const laneEnds: number[] = []
  const flush = () => {
    cluster.forEach((x) => (x.lanes = laneEnds.length))
    cluster = []
    laneEnds.length = 0
  }
  for (const sg of segs) {
    if (cluster.length && sg.top >= clusterEnd) flush()
    let lane = laneEnds.findIndex((end) => end <= sg.top)
    if (lane < 0) lane = laneEnds.length
    laneEnds[lane] = sg.top + sg.height
    sg.lane = lane
    cluster.push(sg)
    clusterEnd = Math.max(clusterEnd, sg.top + sg.height)
  }
  flush()
  return segs
}

export function BookingCalendar({ blocks, selectedId, onSelect, focusDate }: BookingCalendarProps) {
  const [weekStart, setWeekStart] = useState(() => mondayOf(focusDate ? new Date(focusDate) : new Date()))
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (focusDate) {
      const d = new Date(focusDate)
      if (!Number.isNaN(d.getTime())) setWeekStart(mondayOf(d))
    }
  }, [focusDate])

  const days = useMemo(() => Array.from({ length: 7 }, (_, i) => addDays(weekStart, i)), [weekStart])
  const todayKey = new Date().toDateString()

  // Scroll to the first block of the week (or 7am) on mount.
  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    let topPx = 7 * HOUR_PX
    const firsts = days.flatMap((d) => layoutDay(blocks, d).map((s) => s.top))
    if (firsts.length) topPx = Math.max(0, Math.min(...firsts) - HOUR_PX / 2)
    el.scrollTop = topPx
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 60000)
    return () => clearInterval(t)
  }, [])
  const nowD = new Date(now)
  const nowTop = ((nowD.getHours() * 60 + nowD.getMinutes()) / 60) * HOUR_PX

  const hours = Array.from({ length: 24 }, (_, h) => h)

  return (
    <section className="bcal" aria-label="Booking calendar">
      <header className="bcal-head">
        <h3 className="bcal-title" aria-live="polite">{weekTitle(weekStart)}</h3>
        <div className="bcal-nav">
          <button type="button" className="bcal-btn" aria-label="Previous week" onClick={() => setWeekStart(addDays(weekStart, -7))}>‹</button>
          <button type="button" className="bcal-btn" onClick={() => setWeekStart(mondayOf(new Date()))}>Today</button>
          <button type="button" className="bcal-btn" aria-label="Next week" onClick={() => setWeekStart(addDays(weekStart, 7))}>›</button>
        </div>
      </header>
      <div className="bcal-legend" aria-hidden="true">
        <span><i className="lg lg-request" />Request</span>
        <span><i className="lg lg-existing" />Existing</span>
        <span><i className="lg lg-approved" />Approved</span>
        <span><i className="lg lg-unavailable" />Unavailable</span>
        <span><i className="lg lg-conflict" />Conflict</span>
      </div>
      <div className="bcal-days" aria-hidden="true">
        <div className="bcal-gutter" />
        {days.map((d, i) => (
          <div key={i} className={`bcal-dayhead${d.toDateString() === todayKey ? ' is-today' : ''}`}>
            <span>{DAY_NAMES[i]}</span> <b>{d.getDate()}</b>
          </div>
        ))}
      </div>
      <div className="bcal-scroll" ref={scrollRef} tabIndex={0} aria-label="Scrollable week schedule">
        <div className="bcal-grid" role="group" aria-label={`Week of ${weekTitle(weekStart)}`} style={{ height: 24 * HOUR_PX }}>
          <div className="bcal-gutter" aria-hidden="true">
            {hours.map((h) => (
              <div key={h} className="bcal-hour" style={{ top: h * HOUR_PX }}>{h === 0 ? '' : `${pad(h)}:00`}</div>
            ))}
          </div>
          {days.map((d, i) => {
            const segs = layoutDay(blocks, d)
            return (
              <div
                key={i}
                className={`bcal-col${d.toDateString() === todayKey ? ' is-today' : ''}`}
                role="group"
                aria-label={d.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' })}
              >
                {hours.map((h) => (
                  <div key={h} className="bcal-line" style={{ top: h * HOUR_PX }} />
                ))}
                {d.toDateString() === todayKey && (
                  <div className="bcal-now" data-testid="now-line" style={{ top: nowTop }} aria-hidden="true" />
                )}
                {segs.map((sg) => {
                  const b = sg.block
                  const bs = new Date(b.start).getTime()
                  const be = new Date(b.end).getTime()
                  const multiDay = new Date(bs).toDateString() !== new Date(be).toDateString()
                  const short = (ms: number) =>
                    multiDay ? `${new Date(ms).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })} ${hhmm(ms)}` : hhmm(ms)
                  const range = `${short(bs)}–${short(be)}`
                  const contUp = bs < sg.s
                  const contDown = be > sg.e
                  const full = `${b.label}, occupied ${range}, event ${hhmm(new Date(b.eventStart).getTime())}–${hhmm(new Date(b.eventEnd).getTime())}${b.conflict ? ', conflict' : ''}${b.approved ? ', approved' : ''}`
                  const es = new Date(b.eventStart).getTime()
                  const ee = new Date(b.eventEnd).getTime()
                  const showBuffers = b.kind !== 'unavailable' && !Number.isNaN(es) && !Number.isNaN(ee)
                  const pxFor = (a: number, z: number) => (Math.max(0, z - a) / 60000 / 60) * HOUR_PX
                  const setupPx = showBuffers && es > bs ? pxFor(sg.s, Math.min(Math.max(es, sg.s), sg.e)) : 0
                  const turnPx = showBuffers && ee < be ? pxFor(Math.max(Math.min(ee, sg.e), sg.s), sg.e) : 0
                  const eventLine = showBuffers && (es !== bs || ee !== be) ? `Event ${short(es)}–${short(ee)}` : range
                  const w = 100 / sg.lanes
                  const cls = ['bcal-block', `k-${b.kind}`, b.conflict ? 'is-conflict' : '', b.approved ? 'is-approved' : '', selectedId === b.id ? 'is-selected' : '', contUp ? 'cont-up' : '', contDown ? 'cont-down' : '']
                    .filter(Boolean)
                    .join(' ')
                  return (
                    <button
                      key={b.id}
                      type="button"
                      className={cls}
                      aria-pressed={selectedId === b.id}
                      aria-label={full}
                      title={`${full} (${fmtRange(bs, be)})`}
                      style={{ top: sg.top, height: sg.height, left: `calc(${sg.lane * w}% + 1px)`, width: `calc(${w}% - 2px)` }}
                      onClick={() => onSelect(b.id)}
                    >
                      {setupPx > 0 && (
                        <span className="bcal-buffer buf-setup" data-testid="block-setup" style={{ height: setupPx }}>
                          {setupPx >= BUFFER_TEXT_PX ? 'Setup' : ''}
                        </span>
                      )}
                      {turnPx > 0 && (
                        <span className="bcal-buffer buf-turnaround" data-testid="block-turnaround" style={{ height: turnPx }}>
                          {turnPx >= BUFFER_TEXT_PX ? 'Turnaround' : ''}
                        </span>
                      )}
                      <span className="bcal-text" style={setupPx > 0 ? { marginTop: setupPx } : undefined}>
                        <span className="bcal-label">
                          {contUp ? '↳ ' : ''}{b.label}
                          {b.conflict && <span className="bcal-flag" aria-hidden="true">!</span>}
                        </span>
                        <span className="bcal-time">{eventLine}</span>
                      </span>
                    </button>
                  )
                })}
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}
