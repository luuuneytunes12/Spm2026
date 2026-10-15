import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { BookingCalendar, type CalendarBlock } from '../../components/BookingCalendar'
import { VENUE_QUEUE_CHANGED } from '../../components/Sidebar'
import { ApiError } from '../../lib/api'
import { formatRange, formatTimestamp } from '../../lib/events'
import {
  BOOKING_STATUS_LABELS,
  describeConflict,
  bookingPeriodParts,
  approveVenueBooking,
  holdVenueBooking,
  listApprovedBookings,
  listFlaggedBookings,
  listVenueBookingQueue,
  rejectVenueBooking,
} from '../../lib/venueBookings'
import { CONFLICT_FLAG_LABEL } from '../../lib/venueBookings'
import type { BookingConflict, VenueBooking } from '../../lib/venueBookings'
import { FlaggedResolution } from './FlaggedResolution'

/** Venue Staff's review queue: every pending booking request, each carrying
 *  what is needed to decide on it -- the venue, the event's date and time,
 *  expected attendance, layout, and accessibility or facility needs -- and
 *  the two decisions, Approve and Reject. A decided request leaves the
 *  queue. */
export function VenueBookingQueue() {
  const [bookings, setBookings] = useState<VenueBooking[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [decided, setDecided] = useState<VenueBooking | null>(null)
  const confirmation = useRef<HTMLParagraphElement>(null)
  const [view, setView] = useState<'calendar' | 'list'>('calendar')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [venueOverride, setVenueOverride] = useState<number | null>(null)
  const [focusDate, setFocusDate] = useState<string | undefined>(undefined)
  const [approved, setApproved] = useState<VenueBooking[] | null>(null)
  const [approvedError, setApprovedError] = useState<string | null>(null)
  const [flagged, setFlagged] = useState<VenueBooking[] | null>(null)
  const [flaggedError, setFlaggedError] = useState<string | null>(null)
  const [resolved, setResolved] = useState<{ booking: VenueBooking; cancelled: boolean } | null>(null)
  const [params] = useSearchParams()
  const [flaggedOpen] = useState(params.get('view') === 'flagged')

  useEffect(() => {
    let cancelled = false
    Promise.resolve(listApprovedBookings())
      .then((b) => !cancelled && setApproved(b ?? []))
      .catch((err: unknown) => {
        if (!cancelled)
          setApprovedError(err instanceof ApiError ? err.message : 'Could not load approved bookings.')
      })
    Promise.resolve(listFlaggedBookings())
      .then((b) => !cancelled && setFlagged(b ?? []))
      .catch((err: unknown) => {
        if (!cancelled)
          setFlaggedError(err instanceof ApiError ? err.message : 'Could not load flagged bookings.')
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    listVenueBookingQueue()
      .then((b) => !cancelled && setBookings(b))
      .catch((err: unknown) => {
        if (!cancelled)
          setError(err instanceof ApiError ? err.message : 'Could not load booking requests.')
      })
    return () => {
      cancelled = true
    }
  }, [])

  // The decided card is gone, and the keyboard focus with it: put it on the
  // confirmation rather than leaving it at the top of the document.
  useEffect(() => {
    if (decided || resolved) confirmation.current?.focus()
  }, [decided, resolved])

  function onDecided(result: VenueBooking) {
    setBookings((current) => current?.filter((b) => b.id !== result.id) ?? null)
    setResolved(null)
    setDecided(result)
    window.dispatchEvent(new Event(VENUE_QUEUE_CHANGED))
  }

  function onResolved(result: VenueBooking, cancelled: boolean) {
    setFlagged((current) => current?.filter((b) => b.id !== result.id) ?? null)
    setApproved((current) => current?.filter((b) => b.id !== result.id) ?? null)
    setDecided(null)
    setResolved({ booking: result, cancelled })
    setSelectedId(null)
    window.dispatchEvent(new Event(VENUE_QUEUE_CHANGED))
  }

  return (
    <div>
      <h1>Booking requests</h1>
      <p className="page-subtitle">Pending venue requests</p>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {decided && (
        <p className="notice" role="status" tabIndex={-1} ref={confirmation}>
          {decided.status === 'tentative_hold'
            ? `Tentative hold placed for ${decided.venue.name} until ${
                decided.expires_at ? formatTimestamp(decided.expires_at) : 'its expiry'
              }. The Coordinator has been notified.`
            : `${BOOKING_STATUS_LABELS[decided.status]}: ${decided.venue.name} for ${
                decided.event.name ?? 'an untitled event'
              }. ${decided.requested_by.name} can now see the decision.`}
        </p>
      )}
      {resolved && (
        <p className="notice" role="status" tabIndex={-1} ref={confirmation}>
          {resolved.cancelled ? 'Cancelled' : 'Kept'} {resolved.booking.venue.name} for{' '}
          {resolved.booking.event.name ?? 'an untitled event'}.{' '}
          {resolved.cancelled
            ? 'The flag is cleared and the Coordinator is told. The Event is not cancelled.'
            : 'The flag is cleared.'}
        </p>
      )}
      {!error && bookings === null && <p>Loading…</p>}
      {bookings?.length === 0 && <p>No pending booking requests.</p>}

      {bookings && bookings.length > 0 && (
        <div className="bq-toggle" role="group" aria-label="View">
          {(['calendar', 'list'] as const).map((v) => (
            <button
              key={v}
              type="button"
              className={view === v ? 'btn-primary' : 'btn-secondary'}
              aria-pressed={view === v}
              onClick={() => setView(v)}
            >
              {v === 'calendar' ? 'Calendar' : 'List'}
            </button>
          ))}
        </div>
      )}

      {bookings && bookings.length > 0 && view === 'list' &&
        groupByVenue(bookings).map(({ venue, items }) => (
          <section key={venue.id} className="venue-group" aria-label={`Requests for ${venue.name}`}>
            <h2 className="venue-group-heading">
              <Link to={`/venues/${venue.id}`}>{venue.name}</Link>
              <span className="badge">
                {items.length} {items.length === 1 ? 'request' : 'requests'}
              </span>
            </h2>
            <div className="booking-grid">
              {items.map((b) => (
                <BookingCard key={b.id} booking={b} onDecided={onDecided} />
              ))}
            </div>
          </section>
        ))}

      {bookings && (bookings.length > 0 || (approved?.length ?? 0) + (flagged?.length ?? 0) > 0) && view === 'calendar' && (
        <CalendarView
          bookings={bookings}
          approved={approved}
          approvedError={approvedError}
          flagged={flagged}
          flaggedError={flaggedError}
          flaggedOpen={flaggedOpen}
          onResolved={onResolved}
          selectedId={selectedId}
          venueOverride={venueOverride}
          focusDate={focusDate}
          onSelectRequest={(b) => {
            setSelectedId(`req-${b.id}`)
            setVenueOverride(b.venue.id)
            setFocusDate(b.occupied_start)
          }}
          onSelectOther={(b) => {
            setSelectedId(`ap-${b.id}`)
            setVenueOverride(b.venue.id)
            setFocusDate(b.occupied_start)
          }}
          onSelectId={setSelectedId}
          onVenue={(id) => {
            setVenueOverride(id)
            setSelectedId(null)
          }}
          onDecided={onDecided}
        />
      )}
    </div>
  )
}

/** Why Approve is unavailable, or null. The server refuses approval over an
 *  approved booking or a closure; it does not say which a conflict is, so
 *  any conflict not labelled as a hold is treated as blocking. */
function approveBlocker(b: VenueBooking): string | null {
  const hit = (b.conflicts ?? []).find((c) => c.kind === 'unavailability' || c.booking_id === null || conflictState(c) !== 'Hold')
  if (!hit) return null
  const d = describeConflict(hit)
  return d.unavailable ? `Venue unavailable: ${d.reason ?? 'no reason given'}` : `Conflicts with ${d.name}`
}

function conflictState(c: BookingConflict): string {
  const st = c.status
  return st === 'tentative_hold' ? 'Hold' : 'Approved'
}

function CalendarView({
  bookings,
  approved,
  approvedError,
  flagged,
  flaggedError,
  flaggedOpen,
  selectedId,
  venueOverride,
  focusDate,
  onSelectRequest,
  onSelectOther,
  onSelectId,
  onVenue,
  onDecided,
  onResolved,
}: {
  bookings: VenueBooking[]
  approved: VenueBooking[] | null
  approvedError: string | null
  flagged: VenueBooking[] | null
  flaggedError: string | null
  flaggedOpen: boolean
  selectedId: string | null
  venueOverride: number | null
  focusDate?: string
  onSelectRequest: (b: VenueBooking) => void
  onSelectOther: (b: VenueBooking) => void
  onSelectId: (id: string) => void
  onVenue: (venueId: number) => void
  onDecided: (result: VenueBooking) => void
  onResolved: (result: VenueBooking, cancelled: boolean) => void
}) {
  const flaggedIds = new Set((flagged ?? []).map((b) => b.id))
  const approvedOnly = (approved ?? []).filter((b) => !flaggedIds.has(b.id))
  const approvedAll = [...approvedOnly, ...(flagged ?? [])]
  const groups = groupByVenue([...bookings, ...approvedAll])
  const selectedReq = bookings.find((b) => `req-${b.id}` === selectedId)
  const selectedOther = approvedAll.find((b) => `ap-${b.id}` === selectedId)
  const first = bookings[0] ?? approvedAll[0]
  const venueId = groups.some((g) => g.venue.id === venueOverride)
    ? (venueOverride as number)
    : (selectedReq ?? selectedOther ?? first).venue.id
  const inVenue = bookings.filter((b) => b.venue.id === venueId)
  const detail = selectedReq && selectedReq.venue.id === venueId ? selectedReq : inVenue[0]
  const other = selectedOther && selectedOther.venue.id === venueId ? selectedOther : undefined
  const approvedInVenue = approvedAll.filter((b) => b.venue.id === venueId)
  const approvedIds = new Set(approvedInVenue.map((b) => b.id))

  const blocks: CalendarBlock[] = []
  const seen = new Set<string>()
  const pendingIds = new Set(inVenue.map((b) => b.id))
  const conflictOwners = new Map<string, VenueBooking[]>()
  for (const b of inVenue) {
    blocks.push({
      id: `req-${b.id}`,
      label: b.event.name ?? 'Untitled event',
      start: b.occupied_start,
      end: b.occupied_end,
      eventStart: b.start_time,
      eventEnd: b.end_time,
      kind: 'request',
      conflict: (b.conflicts?.length ?? 0) > 0,
    })
    for (const c of b.conflicts ?? []) {
      if (c.booking_id !== null && (pendingIds.has(c.booking_id) || approvedIds.has(c.booking_id))) continue
      const unavailable = c.kind === 'unavailability' || c.booking_id === null
      const id = unavailable
        ? `un-${c.occupied_start}-${c.occupied_end}`
        : `ex-${c.booking_id}`
      const owners = conflictOwners.get(id) ?? []
      if (!owners.includes(b)) conflictOwners.set(id, [...owners, b])
      if (seen.has(id)) continue
      seen.add(id)
      blocks.push({
        id,
        label: unavailable
          ? (c.reason ?? 'Venue unavailable')
          : `${c.event_name ?? 'Another event'} · ${conflictState(c)}`,
        start: c.occupied_start,
        end: c.occupied_end,
        eventStart: c.event_start,
        eventEnd: c.event_end,
        kind: unavailable ? 'unavailable' : 'existing',
        conflict: true,
        ...(!unavailable && conflictState(c) === 'Approved' ? { approved: true } : {}),
      })
    }
  }
  for (const b of approvedInVenue) {
    blocks.push({
      id: `ap-${b.id}`,
      label: b.event.name ?? 'Untitled event',
      start: b.occupied_start,
      end: b.occupied_end,
      eventStart: b.start_time,
      eventEnd: b.end_time,
      kind: 'existing',
      conflict: flaggedIds.has(b.id),
      approved: true,
    })
  }

  const selectedBlock =
    selectedId && !selectedId.startsWith('req-') && !selectedId.startsWith('ap-')
      ? blocks.find((x) => x.id === selectedId)
      : undefined
  const pendingCurrent = !selectedBlock && !other

  return (
    <div className="bq-layout">
      <aside className="bq-sidebar" aria-label="Requests">
        <SidebarSection title="Pending" count={bookings.length} defaultOpen>
          {bookings.length === 0 && <p className="bq-empty">None.</p>}
          {groupByVenue(bookings).map(({ venue, items }) => (
            <SidebarGroup
              key={venue.id}
              venue={venue}
              items={items}
              current={pendingCurrent ? detail?.id : undefined}
              onSelect={onSelectRequest}
              pill={(b) => ((b.conflicts?.length ?? 0) > 0 ? 'Conflict' : null)}
            />
          ))}
        </SidebarSection>
        <SidebarSection
          title="Approved"
          count={approvedError || approved === null ? undefined : approvedOnly.length}
          error={approvedError}
          loading={approved === null && !approvedError}
        >
          {approvedOnly.length === 0 && approved !== null && <p className="bq-empty">None.</p>}
          {groupByVenue(approvedOnly).map(({ venue, items }) => (
            <SidebarGroup
              key={venue.id}
              venue={venue}
              items={items}
              current={other?.id}
              onSelect={onSelectOther}
              pill={() => null}
            />
          ))}
        </SidebarSection>
        <SidebarSection
          title="Flagged"
          count={flaggedError || flagged === null ? undefined : flagged.length}
          danger
          defaultOpen={flaggedOpen}
          error={flaggedError}
          loading={flagged === null && !flaggedError}
        >
          {flagged?.length === 0 && <p className="bq-empty">None.</p>}
          {groupByVenue(flagged ?? []).map(({ venue, items }) => (
            <SidebarGroup
              key={venue.id}
              venue={venue}
              items={items}
              current={other?.id}
              onSelect={onSelectOther}
              pill={() => 'Flagged'}
            />
          ))}
        </SidebarSection>
      </aside>
      <div className="bq-main">
        <label className="field bq-venue-select">
          <span>Venue</span>
          <select value={venueId} onChange={(e) => onVenue(Number(e.target.value))}>
            {groups.map(({ venue }) => (
              <option key={venue.id} value={venue.id}>
                {venue.name}
              </option>
            ))}
          </select>
        </label>
        <BookingCalendar
          blocks={blocks}
          selectedId={
            selectedBlock ? selectedBlock.id : other ? `ap-${other.id}` : detail ? `req-${detail.id}` : null
          }
          focusDate={focusDate ?? other?.occupied_start ?? detail?.occupied_start}
          onSelect={(id) => {
            if (id.startsWith('req-')) {
              const b = inVenue.find((x) => `req-${x.id}` === id)
              if (b) onSelectRequest(b)
              return
            }
            if (id.startsWith('ap-')) {
              const b = approvedInVenue.find((x) => `ap-${x.id}` === id)
              if (b) onSelectOther(b)
              return
            }
            onSelectId(id)
          }}
        />
        {selectedBlock && (
          <BlockSummary
            block={selectedBlock}
            requests={conflictOwners.get(selectedBlock.id) ?? []}
            onSelectRequest={onSelectRequest}
          />
        )}
        {other && (
          <BookingPanel booking={other} flagged={flaggedIds.has(other.id)} onResolved={onResolved} />
        )}
        {pendingCurrent && detail && <BookingCard key={detail.id} booking={detail} onDecided={onDecided} />}
      </div>
    </div>
  )
}

function SidebarSection({
  title,
  count,
  danger,
  defaultOpen,
  error,
  loading,
  children,
}: {
  title: string
  count?: number
  danger?: boolean
  defaultOpen?: boolean
  error?: string | null
  loading?: boolean
  children: React.ReactNode
}) {
  return (
    <details className="bq-section" open={defaultOpen}>
      <summary>
        <span>{title}</span>
        {count !== undefined && (
          <span className={`bq-bubble${danger ? ' bq-bubble-danger' : ''}`}>{count}</span>
        )}
      </summary>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {loading && <p className="bq-empty">Loading…</p>}
      {!error && !loading && children}
    </details>
  )
}

function SidebarGroup({
  venue,
  items,
  current,
  onSelect,
  pill,
}: {
  venue: VenueBooking['venue']
  items: VenueBooking[]
  current?: number
  onSelect: (b: VenueBooking) => void
  pill: (b: VenueBooking) => string | null
}) {
  return (
    <div className="bq-sidebar-group">
      <h3>{venue.name}</h3>
      <ul>
        {items.map((b) => {
          const label = pill(b)
          return (
            <li key={b.id}>
              <button
                type="button"
                className="bq-row"
                aria-current={current === b.id ? 'true' : undefined}
                onClick={() => onSelect(b)}
              >
                <strong>{b.event.name ?? 'Untitled event'}</strong>
                <span className="bq-row-time">{shortRange(b.start_time, b.end_time)}</span>
                {label && <span className="badge bq-pill">{label}</span>}
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

/** Approved booking details: read-only, plus resolution actions when flagged. */
function BookingPanel({
  booking: b,
  flagged,
  onResolved,
}: {
  booking: VenueBooking
  flagged: boolean
  onResolved: (result: VenueBooking, cancelled: boolean) => void
}) {
  return (
    <section className="card" aria-label={`${flagged ? 'Flagged' : 'Approved'} booking for ${b.event.name ?? 'an event'}`}>
      <h2>{b.event.name ?? 'Untitled event'}</h2>
      {flagged && (
        <>
          <p className="notice" role="note">
            <span className="badge">Flagged</span> {CONFLICT_FLAG_LABEL}.
          </p>
          <ConflictBanners booking={b} />
        </>
      )}
      <BookingDetails booking={b} />
      {flagged && <FlaggedResolution key={b.id} booking={b} onResolved={onResolved} />}
    </section>
  )
}

/** `Dec 20 · 11:00–13:00`, or both dates when the window spans days. */
function windowText(startIso: string, endIso: string): string {
  const s = new Date(startIso)
  const e = new Date(endIso)
  return s.toDateString() === e.toDateString()
    ? `${md(s)} · ${hm(s)}–${hm(e)}`
    : `${md(s)} ${hm(s)} – ${md(e)} ${hm(e)}`
}

/** Read-only summary of another booking or an unavailable period. */
function BlockSummary({
  block: b,
  requests,
  onSelectRequest,
}: {
  block: CalendarBlock
  requests: VenueBooking[]
  onSelectRequest: (b: VenueBooking) => void
}) {
  const title = b.kind === 'unavailable' ? `Venue unavailable · ${b.label}` : b.label
  return (
    <section className="card" aria-label={title}>
      <h2>{title}</h2>
      <dl className="detail-list bq-details">
        <div className="detail-row">
          <dt>Occupied</dt>
          <dd>{windowText(b.start, b.end)}</dd>
        </div>
        {b.kind === 'existing' && (
          <div className="detail-row">
            <dt>Event time</dt>
            <dd>{windowText(b.eventStart, b.eventEnd)}</dd>
          </div>
        )}
        <div className="detail-row">
          <dt>Conflicts with</dt>
          <dd className="bq-conflict-list">
            {requests.map((r) => (
              <button key={r.id} type="button" className="btn-secondary bq-chip" onClick={() => onSelectRequest(r)}>
                {r.event.name ?? 'Untitled event'}
              </button>
            ))}
          </dd>
        </div>
      </dl>
    </section>
  )
}

/** Requests grouped by venue, in the order each venue first appears. */
function groupByVenue(bookings: VenueBooking[]) {
  const groups = new Map<number, { venue: VenueBooking['venue']; items: VenueBooking[] }>()
  for (const b of bookings) {
    const g = groups.get(b.venue.id) ?? { venue: b.venue, items: [] }
    g.items.push(b)
    groups.set(b.venue.id, g)
  }
  return [...groups.values()]
}

const hm = (d: Date) =>
  d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: false })
const md = (d: Date) => d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })

/** `Dec 20 · 11:00–13:00` */
function shortRange(startIso: string | null, endIso: string | null): string {
  if (!startIso) return 'No date yet'
  const s = new Date(startIso)
  return `${md(s)} · ${hm(s)}${endIso ? `–${hm(new Date(endIso))}` : ''}`
}

/** `10:40–12:40`, with dates only when the overlap is not on the request's day. */
function overlapText(c: BookingConflict, dayIso: string): string {
  const s = new Date(c.overlap_start)
  const e = new Date(c.overlap_end)
  const sameDay = s.toDateString() === e.toDateString() && s.toDateString() === new Date(dayIso).toDateString()
  if (sameDay) return `${hm(s)}–${hm(e)}`
  if (s.toDateString() === e.toDateString()) return `${md(s)} ${hm(s)}–${hm(e)}`
  return `${md(s)} ${hm(s)} – ${md(e)} ${hm(e)}`
}

/** One single-line alert per conflict, labelled in text (not colour alone). */
function ConflictBanners({ booking: b }: { booking: VenueBooking }) {
  return (
    <>
      {(b.conflicts ?? []).map((c) => {
        const d = describeConflict(c)
        const what = d.unavailable ? `Venue unavailable · ${d.reason ?? 'no reason given'}` : `Conflict · ${d.name}`
        return (
          <p
            key={c.booking_id ?? `unavailable-${c.occupied_start}-${c.occupied_end}`}
            className="bq-conflict"
            role="alert"
          >
            {what} · overlap {overlapText(c, b.start_time)}
          </p>
        )
      })}
    </>
  )
}

function BookingDetails({ booking: b }: { booking: VenueBooking }) {
  return (
    <dl className="detail-list bq-details">
      {(
        [
          [
            'Venue',
            <Link key="venue" to={`/venues/${b.venue.id}`}>
              {b.venue.name} — {b.venue.location}
            </Link>,
          ],
          ['Date and time', formatRange(b.start_time, b.end_time)],
          ['Effective occupied time', formatRange(b.occupied_start, b.occupied_end)],
          [
            'Time breakdown',
            <ul key="tb" className="bq-breakdown">
              {bookingPeriodParts(b).map((p) => (
                <li key={p.label}>
                  <strong>{p.label}</strong> {p.text}
                </li>
              ))}
            </ul>,
          ],
          ['Attendance', b.expected_attendance?.toString() ?? 'Not given'],
          ['Layout', b.room_layout_preference ?? 'None given'],
          ['Accessibility', b.accessibility_needs ?? 'None given'],
          ['Facilities', b.facilities_needs ?? b.venue_requirements ?? 'None given'],
          ['Requested by', `${b.requested_by.name} (${b.requested_by.email})`],
          ['Requested on', formatTimestamp(b.created_at) ?? ''],
        ] as [string, React.ReactNode][]
      ).map(([label, value]) => (
        <div key={label} className="detail-row">
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  )
}

function BookingCard({
  booking: b,
  onDecided,
}: {
  booking: VenueBooking
  onDecided: (result: VenueBooking) => void
}) {
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')
  const [alternative, setAlternative] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function decide(action: () => Promise<VenueBooking>) {
    setSaving(true)
    setError(null)
    try {
      onDecided(await action())
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not save the decision.')
      setSaving(false)
    }
  }

  const blocker = approveBlocker(b)

  return (
    <section className="card" aria-label={`Booking request for ${b.event.name ?? 'an event'}`}>
      <h2>{b.event.name ?? 'Untitled event'}</h2>
      {b.safety_recheck_reason && (
        <p className="notice" role="note">
          <span className="badge">Safety re-review</span> {b.safety_recheck_reason}
        </p>
      )}
      <ConflictBanners booking={b} />
      <BookingDetails booking={b} />

      {rejecting ? (
        <form
          className="status-actions decision-form"
          onSubmit={(e) => {
            e.preventDefault()
            void decide(() => rejectVenueBooking(b.id, { reason, suggested_alternative: alternative }))
          }}
        >
          <p className="page-subtitle">Give a reason, an alternative, or both. The Coordinator sees it.</p>
          <label className="field">
            <span>Reason</span>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              maxLength={2000}
              rows={3}
              disabled={saving}
              autoFocus
            />
          </label>
          <label className="field">
            <span>Suggested alternative</span>
            <textarea
              value={alternative}
              onChange={(e) => setAlternative(e.target.value)}
              maxLength={2000}
              rows={3}
              disabled={saving}
            />
          </label>
          <div className="form-actions">
            <button
              type="submit"
              className="btn-primary"
              disabled={saving || (!reason.trim() && !alternative.trim())}
            >
              {saving ? 'Saving…' : 'Confirm rejection'}
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => setRejecting(false)}
              disabled={saving}
            >
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <div className="status-actions">
          {blocker && (
            <p id={`bq-block-${b.id}`} className="bq-block-hint">
              {blocker}
            </p>
          )}
          <div className="form-actions">
            <button
              type="button"
              className="btn-primary"
              onClick={() => void decide(() => approveVenueBooking(b.id))}
              disabled={saving || !!blocker}
              title={blocker ?? undefined}
              aria-describedby={blocker ? `bq-block-${b.id}` : undefined}
            >
              {saving ? 'Saving…' : 'Approve'}
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => void decide(() => holdVenueBooking(b.id))}
              disabled={saving || b.status !== 'pending'}
            >
              Place 24-hour hold
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => setRejecting(true)}
              disabled={saving}
            >
              Reject
            </button>
          </div>
        </div>
      )}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </section>
  )
}
