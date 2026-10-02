import { useEffect, useMemo, useState } from 'react'
import { ApiError } from '../../lib/api'
import { listEquipment } from '../../lib/equipment'
import type { EquipmentItem } from '../../lib/equipment'
import {
  checkAvailability,
  listEventReservations,
  listReservableEvents,
  reserveEquipment,
} from '../../lib/equipmentReservations'
import type {
  EquipmentAvailability,
  EquipmentReservation,
  ReservableEvent,
} from '../../lib/equipmentReservations'
import { formatRange, formatTimestamp, fromDateTimeLocal, toDateTimeLocal } from '../../lib/events'

function message(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback
}

/** Check equipment availability for an event's date and time, and reserve
 *  it (Technical Support Staff).
 *
 *  The window starts as the event's own date and time and can be changed
 *  for the check. A reservation always holds the event's own window -- the
 *  server takes it from the event -- and is freed at the event's end time.
 */
export function EquipmentReservations() {
  const [events, setEvents] = useState<ReservableEvent[]>([])
  const [items, setItems] = useState<EquipmentItem[]>([])
  const [types, setTypes] = useState<string[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)

  const [eventId, setEventId] = useState('')
  const [type, setType] = useState('')
  const [equipmentId, setEquipmentId] = useState('')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')

  const [availability, setAvailability] = useState<EquipmentAvailability | null>(null)
  const [checking, setChecking] = useState(false)
  const [checkError, setCheckError] = useState<string | null>(null)

  const [reservations, setReservations] = useState<EquipmentReservation[]>([])
  const [quantity, setQuantity] = useState('')
  const [reserving, setReserving] = useState(false)
  const [reserveError, setReserveError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    Promise.all([listReservableEvents(), listEquipment()])
      .then(([reservable, catalogue]) => {
        if (cancelled) return
        setEvents(reservable)
        setItems(catalogue.items)
        setTypes(catalogue.types)
      })
      .catch((err: unknown) => !cancelled && setLoadError(message(err, 'Could not load events and equipment.')))
    return () => {
      cancelled = true
    }
  }, [])

  const event = events.find((e) => String(e.id) === eventId) ?? null
  const item = items.find((i) => String(i.id) === equipmentId) ?? null
  const requested = event?.equipment_items.find((line) => String(line.equipment_id) === equipmentId) ?? null
  const shownItems = useMemo(
    () => (type ? items.filter((i) => i.category === type) : items),
    [items, type],
  )

  useEffect(() => {
    if (!eventId) return
    let cancelled = false
    listEventReservations(Number(eventId))
      .then((r) => !cancelled && setReservations(r))
      .catch(() => !cancelled && setReservations([]))
    return () => {
      cancelled = true
    }
  }, [eventId])

  function chooseEvent(id: string) {
    setEventId(id)
    const chosen = events.find((e) => String(e.id) === id)
    setStart(toDateTimeLocal(chosen?.proposed_start ?? null))
    setEnd(toDateTimeLocal(chosen?.proposed_end ?? null))
    setReservations([])
    resetResult()
  }

  function resetResult() {
    setAvailability(null)
    setCheckError(null)
    setReserveError(null)
  }

  async function check(e: React.FormEvent) {
    e.preventDefault()
    resetResult()
    const startIso = fromDateTimeLocal(start)
    const endIso = fromDateTimeLocal(end)
    if (!item || !startIso || !endIso) {
      setCheckError('Select equipment and a start and end date and time.')
      return
    }
    setChecking(true)
    try {
      setAvailability(await checkAvailability(item.id, startIso, endIso, event?.id))
    } catch (err) {
      setCheckError(message(err, 'Could not check availability.'))
    } finally {
      setChecking(false)
    }
  }

  async function reserve() {
    if (!event || !item) return
    setReserving(true)
    setReserveError(null)
    try {
      await reserveEquipment(event.id, item.id, requested ? undefined : Number(quantity) || undefined)
      const [reservable, reserved] = await Promise.all([
        listReservableEvents(),
        listEventReservations(event.id),
      ])
      setEvents(reservable)
      setReservations(reserved)
      setQuantity('')
      setAvailability(null)
    } catch (err) {
      setReserveError(message(err, 'Could not reserve the equipment.'))
    } finally {
      setReserving(false)
    }
  }

  const alreadyReserved = reservations.some((r) => String(r.equipment_id) === equipmentId)

  return (
    <div className="stack">
      <header className="page-header">
        <h1>Equipment reservations</h1>
        <p className="page-subtitle">
          Check whether enough equipment is free for an event's date and time, then reserve it.
        </p>
      </header>

      {loadError && (
        <p className="form-error" role="alert">
          {loadError}
        </p>
      )}

      <form className="card stack" onSubmit={(e) => void check(e)} noValidate>
        <div className="field">
          <label htmlFor="reservation-event">Event</label>
          <select id="reservation-event" value={eventId} onChange={(e) => chooseEvent(e.target.value)}>
            <option value="">Select an event…</option>
            {events.map((ev) => (
              <option key={ev.id} value={ev.id}>
                {ev.name ?? `Event #${ev.id}`} — {formatRange(ev.proposed_start, ev.proposed_end)}
              </option>
            ))}
          </select>
        </div>

        <div className="form-row">
          <div className="field">
            <label htmlFor="reservation-type">Equipment type</label>
            <select
              id="reservation-type"
              value={type}
              onChange={(e) => {
                setType(e.target.value)
                setEquipmentId('')
                resetResult()
              }}
            >
              <option value="">All types</option>
              {types.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="reservation-equipment">Equipment</label>
            <select
              id="reservation-equipment"
              value={equipmentId}
              onChange={(e) => {
                setEquipmentId(e.target.value)
                resetResult()
              }}
            >
              <option value="">Select equipment…</option>
              {shownItems.map((i) => {
                const line = event?.equipment_items.find((l) => l.equipment_id === i.id)
                return (
                  <option key={i.id} value={i.id}>
                    {i.name}
                    {line ? ` (event requires ${line.quantity_requested})` : ''}
                  </option>
                )
              })}
            </select>
          </div>
        </div>

        <div className="form-row">
          <div className="field">
            <label htmlFor="reservation-start">Start</label>
            <input
              id="reservation-start"
              type="datetime-local"
              value={start}
              onChange={(e) => {
                setStart(e.target.value)
                resetResult()
              }}
            />
          </div>
          <div className="field">
            <label htmlFor="reservation-end">End</label>
            <input
              id="reservation-end"
              type="datetime-local"
              value={end}
              onChange={(e) => {
                setEnd(e.target.value)
                resetResult()
              }}
            />
          </div>
        </div>

        <div>
          <button type="submit" className="btn-primary" disabled={checking}>
            {checking ? 'Checking…' : 'Check availability'}
          </button>
        </div>

        {checkError && (
          <p className="form-error" role="alert">
            {checkError}
          </p>
        )}

        {availability && (
          <div role="status" className="stack-tight">
            <p>
              <strong>
                {availability.available_quantity} of {availability.total_quantity}
              </strong>{' '}
              {availability.equipment_name} available for{' '}
              {formatRange(availability.start_time, availability.end_time)}
              {availability.reserved_quantity > 0 &&
                ` (${availability.reserved_quantity} reserved for overlapping events)`}
              .
            </p>
            {availability.sufficient === false && (
              <p className="form-error">
                Insufficient stock: this event requires {availability.required_quantity}, only{' '}
                {availability.available_quantity} available.
              </p>
            )}
            {availability.sufficient === true && (
              <p>Enough stock for the {availability.required_quantity} this event requires.</p>
            )}
          </div>
        )}
      </form>

      {event && item && (
        <section className="card stack" aria-labelledby="reserve-heading">
          <h2 id="reserve-heading">Reserve {item.name}</h2>
          <p className="page-subtitle">
            Held for the event's date and time, {formatRange(event.proposed_start, event.proposed_end)},
            and freed when it ends.
          </p>
          {alreadyReserved ? (
            <p>{item.name} is already reserved for this event.</p>
          ) : requested ? (
            <p>This event requested {requested.quantity_requested}; that quantity will be reserved.</p>
          ) : (
            <div className="field">
              <label htmlFor="reservation-quantity">Quantity</label>
              <input
                id="reservation-quantity"
                type="number"
                min={1}
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
              />
              <p className="field-hint">This event did not request {item.name}; it will be added.</p>
            </div>
          )}
          {!alreadyReserved && (
            <div>
              <button type="button" className="btn-primary" disabled={reserving} onClick={() => void reserve()}>
                {reserving ? 'Reserving…' : 'Reserve'}
              </button>
            </div>
          )}
          {reserveError && (
            <p className="form-error" role="alert">
              {reserveError}
            </p>
          )}
        </section>
      )}

      {event && (
        <section className="card" aria-labelledby="reserved-heading">
          <h2 id="reserved-heading">Reserved for {event.name ?? 'this event'}</h2>
          {reservations.length === 0 ? (
            <p className="text-muted">Nothing reserved yet.</p>
          ) : (
            <ul>
              {reservations.map((r) => (
                <li key={r.id}>
                  {r.quantity} × {r.equipment_name}
                  {r.equipment_category ? ` (${r.equipment_category})` : ''} ·{' '}
                  {formatRange(r.start_time, r.end_time)} · reserved by {r.reserved_by.name} on{' '}
                  {formatTimestamp(r.reserved_at)}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  )
}
