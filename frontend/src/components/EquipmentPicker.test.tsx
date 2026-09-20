/**
 * Component tests for the equipment row editor.
 *
 * Traceability (see docs/test-cases-organiser-event-equipment.md):
 *   TC-E-1a .. TC-E-1e  -- picking equipment and quantities
 *   TC-E-2a, TC-E-2b    -- one row per item
 *   TC-E-3a             -- a draft stays saveable
 *
 * These assert what a person experiences -- roles, accessible names, visible
 * text -- never CSS class names, so restyling cannot turn them red. What the
 * API does with the rows is covered by backend/tests/test_event_equipment.py.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { EquipmentPicker } from './EquipmentPicker'
import type { EquipmentLineInput } from '../lib/events'

vi.mock('../lib/equipment', () => ({ listEquipmentOptions: vi.fn() }))

import { listEquipmentOptions } from '../lib/equipment'

const mockOptions = vi.mocked(listEquipmentOptions)

const CATALOGUE = [
  { id: 11, name: 'Shure BLX24 Handheld Microphone', category: 'Audio' },
  { id: 12, name: 'Sennheiser XSW-D Lapel Microphone', category: 'Audio' },
  { id: 13, name: 'Epson EB-L200SW Projector', category: 'Projection' },
]

/** The picker is controlled, so tests drive it through a tiny host that
 *  owns the state -- the same way EventForm does. */
function Host({ initial = [] as EquipmentLineInput[] }) {
  const [lines, setLines] = useState<EquipmentLineInput[]>(initial)
  return <EquipmentPicker lines={lines} onChange={setLines} />
}

beforeEach(() => {
  vi.clearAllMocks()
  mockOptions.mockResolvedValue(CATALOGUE)
})

describe('picking equipment', () => {
  it('TC-E-1a: starts empty and says so, rather than showing a blank row', async () => {
    render(<Host />)

    expect(await screen.findByText('No equipment requested yet.')).toBeInTheDocument()
  })

  it('TC-E-1b: adding a row offers the whole catalogue', async () => {
    const user = userEvent.setup()
    render(<Host />)

    await user.click(screen.getByRole('button', { name: 'Add equipment' }))
    await user.click(screen.getByRole('combobox', { name: 'Equipment 1' }))

    const list = await screen.findByRole('listbox', { name: 'Equipment 1' })
    expect(within(list).getAllByRole('option')).toHaveLength(3)
  })

  it('TC-E-1c: typing narrows the list to matching items', async () => {
    const user = userEvent.setup()
    render(<Host />)
    await user.click(screen.getByRole('button', { name: 'Add equipment' }))

    await user.type(screen.getByRole('combobox', { name: 'Equipment 1' }), 'lapel')

    const list = await screen.findByRole('listbox', { name: 'Equipment 1' })
    expect(within(list).getAllByRole('option').map((o) => o.textContent)).toEqual([
      'Sennheiser XSW-D Lapel MicrophoneAudio',
    ])
  })

  it('can be searched by equipment type as well as by name', async () => {
    const user = userEvent.setup()
    render(<Host />)
    await user.click(screen.getByRole('button', { name: 'Add equipment' }))

    await user.type(screen.getByRole('combobox', { name: 'Equipment 1' }), 'projection')

    const list = await screen.findByRole('listbox', { name: 'Equipment 1' })
    expect(within(list).getAllByRole('option')).toHaveLength(1)
  })

  it('TC-E-1d: choosing an item shows it in the row', async () => {
    const user = userEvent.setup()
    render(<Host />)
    await user.click(screen.getByRole('button', { name: 'Add equipment' }))
    await user.click(screen.getByRole('combobox', { name: 'Equipment 1' }))

    await user.click(await screen.findByRole('option', { name: /Epson EB-L200SW/ }))

    await waitFor(() =>
      expect(screen.getByRole('combobox', { name: 'Equipment 1' })).toHaveValue(
        'Epson EB-L200SW Projector',
      ),
    )
  })

  it('TC-E-1e: quantity defaults to one and can be changed', async () => {
    const user = userEvent.setup()
    render(<Host />)
    await user.click(screen.getByRole('button', { name: 'Add equipment' }))

    const qty = screen.getByRole('spinbutton', { name: 'Quantity for equipment 1' })
    expect(qty).toHaveValue(1)

    await user.clear(qty)
    await user.type(qty, '6')

    expect(qty).toHaveValue(6)
  })

  it('can be driven entirely from the keyboard', async () => {
    const user = userEvent.setup()
    render(<Host />)
    await user.click(screen.getByRole('button', { name: 'Add equipment' }))

    const box = screen.getByRole('combobox', { name: 'Equipment 1' })
    box.focus() // focusing opens the list, highlighting the first option
    await user.keyboard('{ArrowDown}{Enter}')

    await waitFor(() => expect(box).toHaveValue('Sennheiser XSW-D Lapel Microphone'))
  })

  it('Escape closes the list without changing the choice', async () => {
    const user = userEvent.setup()
    render(<Host initial={[{ equipment_id: 11, quantity_requested: 6 }]} />)
    const box = await screen.findByRole('combobox', { name: 'Equipment 1' })

    await user.click(box)
    await user.keyboard('{Escape}')

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    expect(box).toHaveValue('Shure BLX24 Handheld Microphone')
  })

  it('an emptied quantity box can be retyped rather than snapping back', async () => {
    const user = userEvent.setup()
    render(<Host initial={[{ equipment_id: 11, quantity_requested: 1 }]} />)
    const qty = await screen.findByRole('spinbutton', { name: 'Quantity for equipment 1' })

    await user.clear(qty)
    await user.type(qty, '6')

    // Clamping on every keystroke would leave 16 here.
    expect(qty).toHaveValue(6)
  })

  it('a quantity left empty becomes one when the field is left', async () => {
    const user = userEvent.setup()
    render(<Host initial={[{ equipment_id: 11, quantity_requested: 4 }]} />)
    const qty = await screen.findByRole('spinbutton', { name: 'Quantity for equipment 1' })

    await user.clear(qty)
    await user.tab()

    expect(qty).toHaveValue(1)
  })

  it('removing a row drops it', async () => {
    const user = userEvent.setup()
    render(<Host initial={[{ equipment_id: 11, quantity_requested: 6 }]} />)
    await screen.findByRole('combobox', { name: 'Equipment 1' })

    await user.click(screen.getByRole('button', { name: 'Remove equipment 1' }))

    expect(await screen.findByText('No equipment requested yet.')).toBeInTheDocument()
  })
})

describe('one row per item', () => {
  it('TC-E-2a: an item already picked is not offered on another row', async () => {
    const user = userEvent.setup()
    render(<Host initial={[{ equipment_id: 11, quantity_requested: 6 }]} />)
    await screen.findByRole('combobox', { name: 'Equipment 1' })

    await user.click(screen.getByRole('button', { name: 'Add equipment' }))
    await user.click(screen.getByRole('combobox', { name: 'Equipment 2' }))

    const list = await screen.findByRole('listbox', { name: 'Equipment 2' })
    const names = within(list)
      .getAllByRole('option')
      .map((o) => o.textContent)
    expect(names).toHaveLength(2)
    expect(names.join(' ')).not.toContain('Shure BLX24')
  })

  it("TC-E-2b: a row still offers its own current choice, so it can be re-opened", async () => {
    const user = userEvent.setup()
    render(<Host initial={[{ equipment_id: 11, quantity_requested: 6 }]} />)

    await user.click(await screen.findByRole('combobox', { name: 'Equipment 1' }))

    const list = await screen.findByRole('listbox', { name: 'Equipment 1' })
    expect(within(list).getByRole('option', { name: /Shure BLX24/ })).toBeInTheDocument()
  })
})

describe('the draft must stay saveable', () => {
  it('TC-E-3a: no control is marked required', async () => {
    const user = userEvent.setup()
    const { container } = render(<Host />)
    await user.click(screen.getByRole('button', { name: 'Add equipment' }))

    // A `required` quantity would let the browser block submission before
    // any handler ran, which would silently break saving an incomplete
    // draft -- the whole point of the draft story.
    expect(container.querySelectorAll('[required]')).toHaveLength(0)
  })

  it('a row with nothing picked yet is allowed to exist', async () => {
    const user = userEvent.setup()
    render(<Host />)

    await user.click(screen.getByRole('button', { name: 'Add equipment' }))

    expect(screen.getByRole('combobox', { name: 'Equipment 1' })).toHaveValue('')
  })
})

describe('when the catalogue cannot be loaded', () => {
  it('says so without blocking the rest of the request', async () => {
    mockOptions.mockRejectedValue(new Error('offline'))
    render(<Host />)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /Could not load the equipment list/i,
    )
  })
})
