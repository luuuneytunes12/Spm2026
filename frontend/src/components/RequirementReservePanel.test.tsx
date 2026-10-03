/**
 * Component tests for reserving equipment from a requirement.
 *
 * Traceability (see docs/test-cases-equipment-requirements.md):
 *   UR AC1  update the status of a requirement ("reserved") -- by reserving
 *           real equipment for it, through the existing reservation
 *
 * The event, the type and the date and time are already known, so the panel
 * asks only for what is not: which item, and how many. Whether the stock is
 * there, whether it overlaps another event, and what a reservation takes are
 * Ercong's reservation rules, covered by his tests and by
 * backend/tests/test_equipment_requirement_fulfillment.py. Here
 * `lib/equipment`, `lib/equipmentReservations` and the requirement client
 * are mocked, and the tests cover what the panel asks and shows.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../lib/api'
import { RequirementReservePanel } from './RequirementReservePanel'

vi.mock('../lib/equipment', async () => {
  const actual = await vi.importActual<typeof import('../lib/equipment')>('../lib/equipment')
  return { ...actual, listEquipment: vi.fn() }
})
vi.mock('../lib/equipmentReservations', async () => {
  const actual = await vi.importActual<typeof import('../lib/equipmentReservations')>(
    '../lib/equipmentReservations',
  )
  return { ...actual, checkAvailability: vi.fn(), listReservableEvents: vi.fn() }
})
vi.mock('../lib/equipmentRequirements', async () => {
  const actual = await vi.importActual<typeof import('../lib/equipmentRequirements')>(
    '../lib/equipmentRequirements',
  )
  return { ...actual, reserveForRequirement: vi.fn() }
})

import { listEquipment } from '../lib/equipment'
import type { EquipmentItem } from '../lib/equipment'
import { checkAvailability, listReservableEvents } from '../lib/equipmentReservations'
import type { ReservableEvent } from '../lib/equipmentReservations'
import { reserveForRequirement } from '../lib/equipmentRequirements'
import type { SupportRequirement } from '../lib/equipmentRequirements'

const mockCatalogue = vi.mocked(listEquipment)
const mockCheck = vi.mocked(checkAvailability)
const mockReservable = vi.mocked(listReservableEvents)
const mockReserve = vi.mocked(reserveForRequirement)

const START = '2026-11-02T09:00:00Z'
const END = '2026-11-02T17:00:00Z'
const EVENT: { id: number; proposed_start: string | null; proposed_end: string | null } = {
  id: 7,
  proposed_start: START,
  proposed_end: END,
}

const REQUIREMENT: SupportRequirement = {
  id: 4,
  category: 'Audio',
  quantity_needed: 5,
  technical_notes: null,
  status: 'requested',
  reserved_quantity: 0,
  reservations: [],
}

function item(id: number, name: string): EquipmentItem {
  return {
    id,
    name,
    category: 'Audio',
    description: null,
    total_quantity: 10,
    location: null,
    operational_status: 'available',
    available_quantity: 10,
    technical_specs: null,
  }
}

/** The event as the existing reservations screen lists it: with what the
 *  Organiser asked for. */
const RESERVABLE: ReservableEvent = {
  id: 7,
  name: 'Conference',
  status: 'approved',
  proposed_start: START,
  proposed_end: END,
  equipment_items: [
    {
      equipment_id: 11,
      equipment_name: 'Shure BLX24',
      equipment_category: 'Audio',
      quantity_requested: 4,
      status: 'requested',
    },
  ],
}

function renderPanel(
  props: Partial<{ requirement: SupportRequirement; event: typeof EVENT }> = {},
) {
  const onReserved = vi.fn()
  const onClose = vi.fn()
  render(
    <RequirementReservePanel
      requirement={props.requirement ?? REQUIREMENT}
      event={props.event ?? EVENT}
      onReserved={onReserved}
      onClose={onClose}
    />,
  )
  return { onReserved, onClose }
}

async function choose(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.selectOptions(await screen.findByLabelText('Equipment'), name)
}

beforeEach(() => {
  vi.clearAllMocks()
  mockCatalogue.mockResolvedValue({
    items: [item(11, 'Shure BLX24'), item(12, 'Yamaha PA')],
    types: ['Audio'],
  })
  mockReservable.mockResolvedValue([RESERVABLE])
})

describe('what is already known', () => {
  it('offers only equipment of the requirement’s type', async () => {
    renderPanel()

    await screen.findByLabelText('Equipment')
    expect(mockCatalogue).toHaveBeenCalledWith({ type: 'Audio' })
  })

  it('lists those items to choose from', async () => {
    renderPanel()

    const select = await screen.findByLabelText('Equipment')
    expect(Array.from(select.querySelectorAll('option')).map((o) => o.textContent)).toEqual([
      'Select equipment…',
      'Shure BLX24 (the Organiser asked for 4)',
      'Yamaha PA',
    ])
  })

  it('says how much is still needed', async () => {
    renderPanel({
      requirement: {
        ...REQUIREMENT,
        status: 'reviewing',
        reserved_quantity: 3,
        reservations: [{ equipment_id: 11, equipment_name: 'Shure BLX24', quantity: 3 }],
      },
    })

    expect(await screen.findByText(/2 still to reserve/i)).toBeInTheDocument()
  })

  it('says the reservation is held for the event’s own date and time', async () => {
    renderPanel()

    expect(await screen.findByText(/held for the event’s date and time/i)).toBeInTheDocument()
  })

  it('does not ask for the event, the type or the dates', async () => {
    renderPanel()
    await screen.findByLabelText('Equipment')

    expect(screen.queryByLabelText('Event')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Equipment type')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Start')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('End')).not.toBeInTheDocument()
  })
})

describe('the quantity', () => {
  it('starts at what is still needed', async () => {
    const user = userEvent.setup()
    renderPanel({
      requirement: {
        ...REQUIREMENT,
        status: 'reviewing',
        reserved_quantity: 3,
        reservations: [{ equipment_id: 11, equipment_name: 'Shure BLX24', quantity: 3 }],
      },
    })

    await choose(user, 'Yamaha PA')

    expect(screen.getByLabelText('Quantity to reserve')).toHaveValue(2)
  })

  it('is the Organiser’s own when they asked for that item: it is reserved whole', async () => {
    const user = userEvent.setup()
    renderPanel()

    await choose(user, 'Shure BLX24 (the Organiser asked for 4)')

    expect(screen.queryByLabelText('Quantity to reserve')).not.toBeInTheDocument()
    expect(screen.getByText(/the organiser asked for 4; that quantity will be reserved/i)).toBeInTheDocument()
  })

  it('is the panel’s to choose again once the Organiser’s line is already reserved', async () => {
    const user = userEvent.setup()
    mockReservable.mockResolvedValue([
      {
        ...RESERVABLE,
        equipment_items: [{ ...RESERVABLE.equipment_items[0], status: 'reserved' }],
      },
    ])
    renderPanel()

    await choose(user, 'Shure BLX24')

    expect(screen.getByLabelText('Quantity to reserve')).toBeInTheDocument()
  })
})

describe('checking availability', () => {
  it('asks the existing check for this item, this event and its own window', async () => {
    const user = userEvent.setup()
    mockCheck.mockResolvedValue({
      equipment_id: 12, equipment_name: 'Yamaha PA', equipment_category: 'Audio',
      operational_status: 'available', total_quantity: 10, reserved_quantity: 4,
      available_quantity: 6, start_time: START, end_time: END,
      required_quantity: null, sufficient: null,
    })
    renderPanel()

    await choose(user, 'Yamaha PA')
    await user.click(screen.getByRole('button', { name: 'Check availability' }))

    await waitFor(() => expect(mockCheck).toHaveBeenCalledWith(12, START, END, 7))
    expect(await screen.findByRole('status')).toHaveTextContent('6 of 10 Yamaha PA available')
  })

  it('says whether what is free covers what would be reserved', async () => {
    const user = userEvent.setup()
    mockCheck.mockResolvedValue({
      equipment_id: 12, equipment_name: 'Yamaha PA', equipment_category: 'Audio',
      operational_status: 'available', total_quantity: 10, reserved_quantity: 8,
      available_quantity: 2, start_time: START, end_time: END,
      required_quantity: null, sufficient: null,
    })
    renderPanel()

    await choose(user, 'Yamaha PA') // 5 still to reserve
    await user.click(screen.getByRole('button', { name: 'Check availability' }))

    expect(await screen.findByRole('status')).toHaveTextContent(/only 2 available/i)
  })

  it('says it is enough when it is', async () => {
    const user = userEvent.setup()
    mockCheck.mockResolvedValue({
      equipment_id: 12, equipment_name: 'Yamaha PA', equipment_category: 'Audio',
      operational_status: 'available', total_quantity: 10, reserved_quantity: 0,
      available_quantity: 10, start_time: START, end_time: END,
      required_quantity: null, sufficient: null,
    })
    renderPanel()

    await choose(user, 'Yamaha PA')
    await user.click(screen.getByRole('button', { name: 'Check availability' }))

    expect(await screen.findByRole('status')).toHaveTextContent(/enough for the 5/i)
  })

  it('needs an item chosen first', async () => {
    const user = userEvent.setup()
    renderPanel()
    await screen.findByLabelText('Equipment')

    await user.click(screen.getByRole('button', { name: 'Check availability' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/select equipment/i)
    expect(mockCheck).not.toHaveBeenCalled()
  })

  it('shows the server’s reason when the check fails', async () => {
    const user = userEvent.setup()
    mockCheck.mockRejectedValue(new ApiError(404, 'Equipment not found'))
    renderPanel()

    await choose(user, 'Yamaha PA')
    await user.click(screen.getByRole('button', { name: 'Check availability' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Equipment not found')
  })
})

describe('reserving', () => {
  it('reserves the item for this requirement, with the quantity chosen', async () => {
    const user = userEvent.setup()
    const updated = {
      ...REQUIREMENT,
      status: 'reviewing',
      reserved_quantity: 3,
      reservations: [{ equipment_id: 12, equipment_name: 'Yamaha PA', quantity: 3 }],
    }
    mockReserve.mockResolvedValue(updated)
    const { onReserved } = renderPanel()

    await choose(user, 'Yamaha PA')
    await user.clear(screen.getByLabelText('Quantity to reserve'))
    await user.type(screen.getByLabelText('Quantity to reserve'), '3')
    await user.click(screen.getByRole('button', { name: 'Reserve' }))

    await waitFor(() => expect(mockReserve).toHaveBeenCalledWith(4, 12, 3))
    await waitFor(() => expect(onReserved).toHaveBeenCalledWith(updated))
  })

  it('leaves the quantity out for an item the Organiser asked for', async () => {
    const user = userEvent.setup()
    mockReserve.mockResolvedValue({ ...REQUIREMENT, reserved_quantity: 4 })
    renderPanel()

    await choose(user, 'Shure BLX24 (the Organiser asked for 4)')
    await user.click(screen.getByRole('button', { name: 'Reserve' }))

    await waitFor(() => expect(mockReserve).toHaveBeenCalledWith(4, 11, undefined))
  })

  it('confirms what was reserved, and is ready for the next item', async () => {
    const user = userEvent.setup()
    mockReserve.mockResolvedValue({
      ...REQUIREMENT,
      status: 'reviewing',
      reserved_quantity: 5,
      reservations: [{ equipment_id: 12, equipment_name: 'Yamaha PA', quantity: 5 }],
    })
    renderPanel()

    await choose(user, 'Yamaha PA')
    await user.click(screen.getByRole('button', { name: 'Reserve' }))

    expect(await screen.findByRole('status')).toHaveTextContent('Reserved 5 × Yamaha PA')
    expect(screen.getByLabelText('Equipment')).toHaveValue('')
  })

  it('is not possible until equipment is chosen', async () => {
    renderPanel()
    await screen.findByLabelText('Equipment')

    expect(screen.getByRole('button', { name: 'Reserve' })).toBeDisabled()
  })

  it('shows the reservation’s own refusal, in its own words, and changes nothing', async () => {
    const user = userEvent.setup()
    mockReserve.mockRejectedValue(
      new ApiError(409, 'Only 3 Yamaha PA available for this event\'s date and time; 5 requested.'),
    )
    const { onReserved } = renderPanel()

    await choose(user, 'Yamaha PA')
    await user.click(screen.getByRole('button', { name: 'Reserve' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Only 3 Yamaha PA available')
    expect(onReserved).not.toHaveBeenCalled()
  })

  it('says something useful when the server cannot be reached', async () => {
    const user = userEvent.setup()
    mockReserve.mockRejectedValue(new Error('network down'))
    renderPanel()

    await choose(user, 'Yamaha PA')
    await user.click(screen.getByRole('button', { name: 'Reserve' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not/i)
  })

  it('offers no way to release or undo a reservation: nothing can', async () => {
    renderPanel({
      requirement: {
        ...REQUIREMENT,
        reserved_quantity: 3,
        reservations: [{ equipment_id: 11, equipment_name: 'Shure BLX24', quantity: 3 }],
      },
    })
    await screen.findByLabelText('Equipment')

    expect(screen.queryByRole('button', { name: /release|unreserve|cancel reservation|undo/i })).not.toBeInTheDocument()
  })
})

describe('when equipment cannot be reserved yet', () => {
  it('says so for an event with no date and time, and offers nothing to press', async () => {
    renderPanel({ event: { id: 7, proposed_start: null, proposed_end: null } })

    expect(await screen.findByText(/no date and time/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reserve' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Check availability' })).not.toBeInTheDocument()
  })

  it('says so for a requirement that is already fully reserved', async () => {
    renderPanel({
      requirement: {
        ...REQUIREMENT,
        status: 'reserved',
        reserved_quantity: 5,
        reservations: [{ equipment_id: 11, equipment_name: 'Shure BLX24', quantity: 5 }],
      },
    })

    expect(await screen.findByText(/fully reserved/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reserve' })).not.toBeInTheDocument()
  })

  it('says so when the equipment cannot be loaded', async () => {
    mockCatalogue.mockRejectedValue(new Error('boom'))
    renderPanel()

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load/i)
  })
})

describe('closing', () => {
  it('closes the panel and reserves nothing', async () => {
    const user = userEvent.setup()
    const { onClose } = renderPanel()
    await screen.findByLabelText('Equipment')

    await user.click(screen.getByRole('button', { name: 'Close' }))

    expect(onClose).toHaveBeenCalled()
    expect(mockReserve).not.toHaveBeenCalled()
  })
})
