/**
 * Component tests for the equipment catalogue.
 *
 * Traceability (see docs/test-cases-tech-support-equipment-catalogue.md):
 *   TC-S4-1c, TC-S4-1d            -- AC1 "see every equipment item"
 *   TC-S4-2e, TC-S4-2f, TC-S4-2g  -- AC2 "each item shows ... six fields"
 *   TC-S4-3e, TC-S4-3f, TC-S4-3g, TC-S4-3h -- AC3 "search or filter by type"
 *
 * These assert what a user experiences (labels, visible text, option lists),
 * never CSS class names -- so restyling cannot turn them red.
 *
 * `lib/equipment` is mocked: this layer is about rendering and wiring. What
 * the API actually returns, and how availability is computed, is covered by
 * backend/tests/test_equipment.py.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { EquipmentCatalogue } from './EquipmentCatalogue'

vi.mock('../../lib/equipment', async () => {
  const actual = await vi.importActual<typeof import('../../lib/equipment')>('../../lib/equipment')
  return { ...actual, listEquipment: vi.fn() } // keep the real labels and formatter
})

import { listEquipment } from '../../lib/equipment'
import type { EquipmentCatalogue as Catalogue, EquipmentItem } from '../../lib/equipment'

const mockList = vi.mocked(listEquipment)

const MICROPHONE: EquipmentItem = {
  id: 1,
  name: 'Shure BLX24 Handheld Microphone',
  category: 'Audio',
  description: 'Wireless handheld microphone for presenters and panel sessions.',
  total_quantity: 16,
  location: 'Marina Bay Facility - AV Store 2',
  operational_status: 'available',
  available_quantity: 14,
  technical_specs: 'UHF wireless, 300ft range',
}

const BROKEN_MIXER: EquipmentItem = {
  id: 2,
  name: 'Behringer X32 Mixing Console',
  category: 'Audio',
  description: 'Digital mixing desk for multi-microphone conference sessions.',
  total_quantity: 2,
  location: 'Marina Bay Facility - AV Store 2',
  operational_status: 'damaged',
  available_quantity: 0,
  technical_specs: 'Channel 7 fader unresponsive',
}

const PROJECTOR: EquipmentItem = {
  ...MICROPHONE,
  id: 3,
  name: 'Epson EB-L200SW Projector',
  category: 'Projection',
  description: 'Short-throw laser projector for main halls.',
  total_quantity: 6,
  available_quantity: 6,
}

const ALL_TYPES = ['Audio', 'Projection', 'Staging']

function catalogue(items: EquipmentItem[], types = ALL_TYPES): Catalogue {
  return { items, types }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockList.mockResolvedValue(catalogue([]))
})

describe('AC1 - every item held by ConnectSphere is visible', () => {
  it('TC-S4-1c: renders one row per item the API returns', async () => {
    mockList.mockResolvedValue(catalogue([MICROPHONE, BROKEN_MIXER, PROJECTOR]))
    render(<EquipmentCatalogue />)

    await waitFor(() => expect(screen.getAllByRole('listitem')).toHaveLength(3))
    expect(screen.getByText('Shure BLX24 Handheld Microphone')).toBeInTheDocument()
    expect(screen.getByText('Epson EB-L200SW Projector')).toBeInTheDocument()
  })

  it('TC-S4-1c: shows items that cannot be used rather than hiding them', async () => {
    mockList.mockResolvedValue(catalogue([BROKEN_MIXER]))
    render(<EquipmentCatalogue />)

    // The row a naive "only show usable kit" filter would drop.
    expect(await screen.findByText('Behringer X32 Mixing Console')).toBeInTheDocument()
    expect(screen.getByText('Damaged')).toBeInTheDocument()
  })

  it('TC-S4-1d: says the catalogue is empty rather than rendering a blank page', async () => {
    render(<EquipmentCatalogue />)

    expect(await screen.findByText('No equipment recorded yet.')).toBeInTheDocument()
  })
})

describe('AC2 - each item shows all six fields', () => {
  it('TC-S4-2e: type, description, total quantity, location, availability and status', async () => {
    mockList.mockResolvedValue(catalogue([MICROPHONE]))
    render(<EquipmentCatalogue />)

    const row = await screen.findByRole('listitem')

    expect(within(row).getByText(/Audio/)).toBeInTheDocument()
    expect(
      within(row).getByText('Wireless handheld microphone for presenters and panel sessions.'),
    ).toBeInTheDocument()
    expect(within(row).getByText(/Marina Bay Facility - AV Store 2/)).toBeInTheDocument()
    // Availability and total quantity are shown together: "0 available"
    // alone would read as if the item did not exist.
    expect(within(row).getByText('14 of 16 available')).toBeInTheDocument()
    expect(within(row).getByText('Available')).toBeInTheDocument()
  })

  it('TC-S4-2g: renders the status as a label, not the raw database value', async () => {
    mockList.mockResolvedValue(catalogue([BROKEN_MIXER]))
    render(<EquipmentCatalogue />)

    await screen.findByRole('listitem')
    expect(screen.getByText('Damaged')).toBeInTheDocument()
    expect(screen.queryByText('damaged')).not.toBeInTheDocument()
  })

  it('a damaged item reports no stock available, not its total', async () => {
    mockList.mockResolvedValue(catalogue([BROKEN_MIXER]))
    render(<EquipmentCatalogue />)

    const row = await screen.findByRole('listitem')
    expect(within(row).getByText('None of 2 available')).toBeInTheDocument()
  })

  it('TC-S4-2f: a missing description or location reads as such, not as a blank', async () => {
    mockList.mockResolvedValue(
      catalogue([{ ...MICROPHONE, description: null, location: null, category: null }]),
    )
    render(<EquipmentCatalogue />)

    const row = await screen.findByRole('listitem')
    expect(within(row).getByText('No description recorded.')).toBeInTheDocument()
    expect(within(row).getByText(/Location not recorded/)).toBeInTheDocument()
    expect(within(row).getByText(/Uncategorised/)).toBeInTheDocument()
  })
})

describe('AC3 - the catalogue can be searched and filtered by type', () => {
  it('TC-S4-3f: choosing a type asks the API for that type', async () => {
    const user = userEvent.setup()
    mockList.mockResolvedValue(catalogue([MICROPHONE, PROJECTOR]))
    render(<EquipmentCatalogue />)
    await screen.findAllByRole('listitem')

    mockList.mockResolvedValue(catalogue([PROJECTOR]))
    await user.selectOptions(screen.getByLabelText('Equipment type'), 'Projection')

    await waitFor(() =>
      expect(mockList).toHaveBeenLastCalledWith(expect.objectContaining({ type: 'Projection' })),
    )
    expect(await screen.findByText('Epson EB-L200SW Projector')).toBeInTheDocument()
    expect(screen.queryByText('Shure BLX24 Handheld Microphone')).not.toBeInTheDocument()
  })

  it('TC-S4-3e: the type dropdown still lists every type while a filter is applied', async () => {
    const user = userEvent.setup()
    mockList.mockResolvedValue(catalogue([MICROPHONE, PROJECTOR]))
    render(<EquipmentCatalogue />)
    await screen.findAllByRole('listitem')

    // Only Projection items come back, but `types` still covers the whole
    // catalogue -- otherwise the dropdown would collapse to the one type
    // already chosen and there would be no way back.
    mockList.mockResolvedValue(catalogue([PROJECTOR], ALL_TYPES))
    await user.selectOptions(screen.getByLabelText('Equipment type'), 'Projection')
    await waitFor(() => expect(mockList).toHaveBeenCalledTimes(2))

    const options = within(screen.getByLabelText('Equipment type')).getAllByRole('option')
    expect(options.map((o) => o.textContent)).toEqual([
      'All types',
      'Audio',
      'Projection',
      'Staging',
    ])
  })

  it('TC-S4-3g: typing in the search box asks the API for that text', async () => {
    const user = userEvent.setup()
    mockList.mockResolvedValue(catalogue([MICROPHONE, PROJECTOR]))
    render(<EquipmentCatalogue />)
    await screen.findAllByRole('listitem')

    mockList.mockResolvedValue(catalogue([MICROPHONE]))
    await user.type(screen.getByLabelText('Search equipment'), 'shure')

    await waitFor(() =>
      expect(mockList).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'shure' })),
    )
  })

  it('debounces typing into a single request rather than one per keystroke', async () => {
    const user = userEvent.setup()
    mockList.mockResolvedValue(catalogue([MICROPHONE]))
    render(<EquipmentCatalogue />)
    await screen.findAllByRole('listitem')
    const callsAfterFirstLoad = mockList.mock.calls.length

    await user.type(screen.getByLabelText('Search equipment'), 'microphone')
    await waitFor(() =>
      expect(mockList).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'microphone' })),
    )

    // Ten characters typed, but nothing like ten requests.
    expect(mockList.mock.calls.length - callsAfterFirstLoad).toBeLessThan(4)
  })

  it('TC-S4-3h: no matches reads differently from an empty catalogue, and can be undone', async () => {
    const user = userEvent.setup()
    mockList.mockResolvedValue(catalogue([MICROPHONE, PROJECTOR]))
    render(<EquipmentCatalogue />)
    await screen.findAllByRole('listitem')

    mockList.mockResolvedValue(catalogue([]))
    await user.selectOptions(screen.getByLabelText('Equipment type'), 'Staging')

    expect(await screen.findByText('No equipment matches this filter.')).toBeInTheDocument()
    expect(screen.queryByText('No equipment recorded yet.')).not.toBeInTheDocument()

    mockList.mockResolvedValue(catalogue([MICROPHONE, PROJECTOR]))
    await user.click(screen.getByRole('button', { name: 'Clear filters' }))

    await waitFor(() => expect(screen.getAllByRole('listitem')).toHaveLength(2))
    expect(screen.getByLabelText('Equipment type')).toHaveValue('')
  })
})
