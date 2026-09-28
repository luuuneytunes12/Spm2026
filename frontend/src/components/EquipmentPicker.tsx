import { useEffect, useId, useRef, useState } from 'react'
import { listEquipmentOptions } from '../lib/equipment'
import type { EquipmentOption } from '../lib/equipment'
import type { EquipmentLineInput } from '../lib/events'

interface EquipmentPickerProps {
  lines: EquipmentLineInput[]
  onChange: (lines: EquipmentLineInput[]) => void
}

/**
 * Repeatable equipment rows for an event request: pick an item, say how many.
 *
 * Replaces a free-text box. "2 projectors, 6 radio mics" cannot be counted,
 * checked against the catalogue, or read by the availability logic; these
 * rows become real `equipment_requests` records that all of that can use.
 *
 * Written from scratch because nothing here does it already: there is no UI
 * library in this project (react, react-dom and react-router are the only
 * dependencies) and no other screen lets the user add and remove inputs.
 *
 * `<datalist>` is the established searchable-input pattern elsewhere in this
 * form, but it cannot be used here. It hands back only the string the user
 * typed, never the id of what they picked -- and an equipment line needs the
 * id. So this is a real combobox: a text input that filters a listbox.
 */
export function EquipmentPicker({ lines, onChange }: EquipmentPickerProps) {
  const [options, setOptions] = useState<EquipmentOption[]>([])
  const [loadError, setLoadError] = useState(false)

  // Fetched once rather than searched server-side per keystroke. The
  // catalogue is small (tens of items, not thousands), so filtering locally
  // is instant, needs no debounce, and cannot render results for a query the
  // user has already moved on from.
  useEffect(() => {
    let cancelled = false
    listEquipmentOptions()
      .then((items) => {
        if (!cancelled) setOptions(items)
      })
      .catch(() => {
        if (!cancelled) setLoadError(true)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const chosenIds = new Set(lines.map((line) => line.equipment_id))

  function update(index: number, patch: Partial<EquipmentLineInput>) {
    onChange(lines.map((line, i) => (i === index ? { ...line, ...patch } : line)))
  }

  function remove(index: number) {
    onChange(lines.filter((_, i) => i !== index))
  }

  function add() {
    // equipment_id 0 means "row added, nothing picked yet". A draft may be
    // saved in this state, so toPayload drops these rather than sending an
    // id the server would reject.
    onChange([...lines, { equipment_id: 0, quantity_requested: 1 }])
  }

  if (loadError) {
    return (
      <p className="form-error" role="alert">
        Could not load the equipment list. You can still save this request and add equipment
        later.
      </p>
    )
  }

  return (
    <div className="stack-tight">
      {lines.length === 0 ? (
        <p className="field-hint">No equipment requested yet.</p>
      ) : (
        <ul className="equipment-lines">
          {lines.map((line, index) => (
            <li key={index} className="equipment-line">
              <EquipmentCombobox
                value={line.equipment_id}
                // Items already on another row are not offered again:
                // quantity is how you ask for more of one thing, so a second
                // row for it is always a mistake. The API rejects it too.
                options={options.filter(
                  (o) => o.id === line.equipment_id || !chosenIds.has(o.id),
                )}
                onSelect={(id) => update(index, { equipment_id: id })}
                label={`Equipment ${index + 1}`}
              />
              <input
                type="number"
                min={1}
                // Deliberately NOT `required`: the form must stay saveable
                // as an incomplete draft, which a required field would
                // block in the browser before any handler ran.
                aria-label={`Quantity for equipment ${index + 1}`}
                // 0 renders as an empty box so the field can be cleared and
                // retyped. Clamping on every keystroke instead would snap an
                // emptied field back to 1, and typing "6" over it would
                // leave 16.
                value={line.quantity_requested === 0 ? '' : line.quantity_requested}
                onChange={(e) =>
                  update(index, { quantity_requested: Number(e.target.value) || 0 })
                }
                // Clamped when the field is left, not while it is being
                // edited: "" and 0 are states you pass through on the way to
                // a real number, but neither is a quantity to save.
                onBlur={() => {
                  if (line.quantity_requested < 1) update(index, { quantity_requested: 1 })
                }}
              />
              <button
                type="button"
                className="btn-link-muted"
                onClick={() => remove(index)}
                aria-label={`Remove equipment ${index + 1}`}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="form-actions">
        <button type="button" className="btn-secondary" onClick={add}>
          Add equipment
        </button>
      </div>
    </div>
  )
}

interface ComboboxProps {
  value: number
  options: EquipmentOption[]
  onSelect: (id: number) => void
  label: string
}

/** A text input that filters a listbox. See the note on EquipmentPicker for
 *  why this is not a `<datalist>` or a `<select>`. */
function EquipmentCombobox({ value, options, onSelect, label }: ComboboxProps) {
  const listId = useId()
  const optionId = (id: number) => `${listId}-option-${id}`

  const selected = options.find((o) => o.id === value) ?? null
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const wrapper = useRef<HTMLDivElement>(null)

  // What the input shows: the chosen item's name when closed, whatever is
  // being typed when open. Keeping these separate means opening the list to
  // browse does not wipe an existing choice.
  const text = open ? query : (selected?.name ?? '')

  const matches = options.filter((o) =>
    `${o.name} ${o.category ?? ''}`.toLowerCase().includes(query.trim().toLowerCase()),
  )

  useEffect(() => {
    if (!open) return
    function onPointerDown(event: MouseEvent) {
      if (!wrapper.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    return () => document.removeEventListener('mousedown', onPointerDown)
  }, [open])

  function choose(option: EquipmentOption) {
    onSelect(option.id)
    setOpen(false)
    setQuery('')
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      if (!open) {
        setOpen(true)
        setActive(0)
        return
      }
      const step = event.key === 'ArrowDown' ? 1 : -1
      setActive((current) => {
        if (matches.length === 0) return 0
        return (current + step + matches.length) % matches.length
      })
    } else if (event.key === 'Enter' && open) {
      event.preventDefault()
      const option = matches[active]
      if (option) choose(option)
    } else if (event.key === 'Escape') {
      setOpen(false)
      setQuery('')
    }
  }

  return (
    <div className="combobox" ref={wrapper}>
      <input
        type="text"
        role="combobox"
        aria-label={label}
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && matches[active] ? optionId(matches[active].id) : undefined}
        placeholder="Search equipment"
        value={text}
        onChange={(e) => {
          setQuery(e.target.value)
          setActive(0)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
      />
      {open && (
        <ul className="combobox-list" id={listId} role="listbox" aria-label={label}>
          {matches.length === 0 ? (
            <li className="combobox-empty">No equipment matches that.</li>
          ) : (
            matches.map((option, index) => (
              <li
                key={option.id}
                id={optionId(option.id)}
                role="option"
                aria-selected={option.id === value}
                className={index === active ? 'combobox-option combobox-option-active' : 'combobox-option'}
                // onMouseDown, not onClick: the input's blur would close the
                // list before a click ever landed.
                onMouseDown={(e) => {
                  e.preventDefault()
                  choose(option)
                }}
                onMouseEnter={() => setActive(index)}
              >
                <span className="combobox-name">{option.name}</span>
                {option.category && <span className="combobox-meta">{option.category}</span>}
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  )
}
