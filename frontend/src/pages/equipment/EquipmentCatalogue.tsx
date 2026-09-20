import { useEffect, useState } from 'react'
import { ApiError } from '../../lib/api'
import {
  OPERATIONAL_STATUS_LABELS,
  OperationalStatus,
  formatAvailability,
  listEquipment,
} from '../../lib/equipment'
import type { EquipmentItem } from '../../lib/equipment'

/** How long to wait after the last keystroke before searching. Long enough
 *  that typing a word is one request rather than ten, short enough that the
 *  list still feels like it reacts to typing. */
const SEARCH_DEBOUNCE_MS = 250

/** The equipment catalogue, for Technical Support Staff.
 *
 *  Read-only on purpose: this story is "see what equipment exists and in
 *  what quantity". Adding, editing and retiring items is EQUIPMENT_MANAGE
 *  and a separate story, which is why there is no "New item" button here.
 *
 *  Lives at /equipment rather than under /tech-support/ because unlike
 *  "my event requests" or "my assigned events" it is not scoped to the
 *  person looking at it -- it is one shared reference list, and the
 *  Coordinator's equipment-request story will read the same page.
 */
export function EquipmentCatalogue() {
  const [type, setType] = useState('')
  // What is in the search box, and what has actually been searched for.
  // They differ for as long as the debounce is pending.
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState('')

  const [items, setItems] = useState<EquipmentItem[]>([])
  const [types, setTypes] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  // Which filter combination the current `items` belong to. Deriving
  // loading from this rather than setting a flag at the top of the effect
  // keeps the effect free of synchronous setState, and means a filter
  // change cannot briefly show the previous filter's rows as if they
  // matched the new one.
  const [loadedKey, setLoadedKey] = useState<string | null>(null)
  // JSON rather than joining on a separator character: a plain
  // `${type} ${search}` would make type "Video Conferencing" collide with
  // type "Video" plus search "Conferencing", and the page would then think
  // it had already loaded results it had not.
  const key = JSON.stringify([type, search])
  const loading = loadedKey !== key

  const filtered = type !== '' || search !== ''

  // Each keystroke restarts the timer, so only a pause in typing reaches
  // the API. Without this, "microphone" would be ten requests, and the
  // replies could arrive out of order.
  useEffect(() => {
    const timer = setTimeout(() => setSearch(query), SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [query])

  useEffect(() => {
    let cancelled = false
    listEquipment({ type, q: search })
      .then((catalogue) => {
        if (cancelled) return
        setItems(catalogue.items)
        // Every type in the whole catalogue, never just the ones in
        // `items` -- so the dropdown still offers the other types (and the
        // way back to "All types") while a filter is applied.
        setTypes(catalogue.types)
        setError(null)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setItems([])
        setError(
          err instanceof ApiError
            ? err.message
            : 'Could not reach the server. Is the backend running?',
        )
      })
      .finally(() => {
        if (!cancelled) setLoadedKey(key)
      })
    return () => {
      cancelled = true
    }
  }, [type, search, key])

  function clearFilters() {
    setType('')
    setQuery('')
    setSearch('')
  }

  return (
    <div className="stack">
      <header className="page-header">
        <h1>Equipment catalogue</h1>
        <p className="page-subtitle">
          Everything ConnectSphere holds, including items that are not currently usable.
        </p>
      </header>

      {/* Deliberately outside the loading swap below: the filters are how
          you get out of an unhelpful result, so they must never disappear
          while a search is in flight. */}
      <div className="card form-row">
        <div className="field">
          <label htmlFor="equipment-search">Search equipment</label>
          <input
            id="equipment-search"
            type="search"
            placeholder="Name or description"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="equipment-type">Equipment type</label>
          <select id="equipment-type" value={type} onChange={(e) => setType(e.target.value)}>
            <option value="">All types</option>
            {types.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </div>
      </div>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      {loading ? null : (
        <>
          <p className="page-subtitle" aria-live="polite">
            {items.length} {items.length === 1 ? 'item' : 'items'}
            {filtered && ' match this filter'}
          </p>

          {items.length === 0 ? (
            <div className="card notice-empty">
              {filtered ? (
                <>
                  <p>No equipment matches this filter.</p>
                  <p className="page-subtitle">
                    <button type="button" className="btn-link-muted" onClick={clearFilters}>
                      Clear filters
                    </button>{' '}
                    to see the whole catalogue.
                  </p>
                </>
              ) : (
                <>
                  <p>No equipment recorded yet.</p>
                  <p className="page-subtitle">
                    Items appear here once they are added to the ConnectSphere inventory.
                  </p>
                </>
              )}
            </div>
          ) : (
            <ul className="request-list">
              {items.map((item) => (
                <li key={item.id} className="card request equipment-row">
                  <div className="request-main">
                    <span className="request-title">{item.name}</span>
                    <span className="request-meta">
                      {item.category ?? 'Uncategorised'} ·{' '}
                      {item.location ?? 'Location not recorded'}
                    </span>
                    <p className="equipment-description">
                      {item.description ?? (
                        <em className="text-muted">No description recorded.</em>
                      )}
                    </p>
                  </div>
                  <div className="request-side">
                    <span
                      className={
                        item.operational_status === OperationalStatus.AVAILABLE
                          ? 'badge badge-accent'
                          : 'badge badge-muted'
                      }
                    >
                      {OPERATIONAL_STATUS_LABELS[item.operational_status] ??
                        item.operational_status}
                    </span>
                    <span className="request-meta">{formatAvailability(item)}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  )
}
