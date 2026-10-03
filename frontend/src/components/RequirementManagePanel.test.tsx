/**
 * Component tests for Technical Support's one panel on a requirement.
 *
 * Traceability (see docs/test-cases-equipment-requirement-status.md):
 *   UR AC1  update the status of a requirement ("reserved", "unavailable"):
 *           mark it In review or Unavailable, or reserve real equipment for it
 *   UR AC2  update the quantity as changes appear
 *
 * One panel, one workflow: what the requirement is and how far it has got,
 * the status and quantity Technical Support may change, and the choice of
 * exact equipment with its availability and the reservation. The event, the
 * type and the date and time are known from the requirement, so none of them
 * is asked for again.
 *
 * What is tested here is what the panel asks and shows. The rules -- which
 * statuses may be set, the quantity floor, the stock and overlap checks, what
 * a reservation takes -- are the backend's and Ercong's reservation, covered
 * by backend/tests/test_equipment_requirement_fulfillment.py. The libs are
 * mocked.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../lib/api'
import { formatRange } from '../lib/events'
import { RequirementManagePanel } from './RequirementManagePanel'

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
  return { ...actual, reserveForRequirement: vi.fn(), updateSupportRequirement: vi.fn() }
})

import { listEquipment } from '../lib/equipment'
import type { EquipmentItem } from '../lib/equipment'
import { checkAvailability, listReservableEvents } from '../lib/equipmentReservations'
import type { EquipmentAvailability, ReservableEvent } from '../lib/equipmentReservations'
import { reserveForRequirement, updateSupportRequirement } from '../lib/equipmentRequirements'
import type { SupportRequirement } from '../lib/equipmentRequirements'

const mockCatalogue = vi.mocked(listEquipment)
const mockCheck = vi.mocked(checkAvailability)
const mockReservable = vi.mocked(listReservableEvents)
const mockReserve = vi.mocked(reserveForRequirement)
const mockUpdate = vi.mocked(updateSupportRequirement)

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
  technical_notes: 'Handheld wireless, for panel Q&A',
  status: 'requested',
  reserved_quantity: 0,
  reservations: [],
}

const PART_RESERVED: SupportRequirement = {
  ...REQUIREMENT,
  status: 'reviewing',
  reserved_quantity: 3,
  reservations: [{ equipment_id: 11, equipment_name: 'Shure BLX24', quantity: 3 }],
}

const FULLY_RESERVED: SupportRequirement = {
  ...REQUIREMENT,
  status: 'reserved',
  reserved_quantity: 5,
  reservations: [{ equipment_id: 11, equipment_name: 'Shure BLX24', quantity: 5 }],
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

function availability(overrides: Partial<EquipmentAvailability> = {}): EquipmentAvailability {
  return {
    equipment_id: 12,
    equipment_name: 'Yamaha PA',
    equipment_category: 'Audio',
    operational_status: 'available',
    total_quantity: 10,
    reserved_quantity: 0,
    available_quantity: 10,
    start_time: START,
    end_time: END,
    required_quantity: null,
    sufficient: null,
    ...overrides,
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

function renderPanel(props: Partial<{ requirement: SupportRequirement; event: typeof EVENT }> = {}) {
  const onChanged = vi.fn()
  const onClose = vi.fn()
  render(
    <RequirementManagePanel
      requirement={props.requirement ?? REQUIREMENT}
      event={props.event ?? EVENT}
      onChanged={onChanged}
      onClose={onClose}
    />,
  )
  return { onChanged, onClose }
}

const panel = () => within(screen.getByRole('region', { name: /manage audio requirement/i }))

async function choose(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.selectOptions(await screen.findByLabelText('Equipment'), name)
}

/** Choose an item and wait for its availability to arrive. */
async function chooseChecked(user: ReturnType<typeof userEvent.setup>, name: string) {
  await choose(user, name)
  await screen.findByRole('status', { name: 'Availability' })
}

beforeEach(() => {
  vi.clearAllMocks()
  mockCatalogue.mockResolvedValue({
    items: [item(11, 'Shure BLX24'), item(12, 'Yamaha PA')],
    types: ['Audio'],
  })
  mockReservable.mockResolvedValue([RESERVABLE])
  mockCheck.mockResolvedValue(availability())
})

// ---------------------------------------------------------------------------
// One workflow
// ---------------------------------------------------------------------------

describe('one panel for the whole requirement', () => {
  it('is a single region named for the requirement it manages', async () => {
    renderPanel()

    expect(
      await screen.findByRole('region', { name: 'Manage Audio requirement' }),
    ).toBeInTheDocument()
  })

  it('holds the requirement, its status and its reservation together', async () => {
    renderPanel()
    await screen.findByLabelText('Equipment')

    expect(panel().getByRole('heading', { name: 'Requirement' })).toBeInTheDocument()
    expect(panel().getByRole('heading', { name: 'Reserve equipment' })).toBeInTheDocument()
  })

  it('does not split the work into separate Update and Reserve equipment buttons', async () => {
    renderPanel()
    await screen.findByLabelText('Equipment')

    expect(screen.queryByRole('button', { name: /^update/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /reserve equipment/i })).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// What is already known
// ---------------------------------------------------------------------------

describe('what the requirement is, and how far it has got', () => {
  it('shows its type', async () => {
    renderPanel()
    await screen.findByLabelText('Equipment')

    expect(panel().getByText('Equipment type').parentElement).toHaveTextContent('Audio')
  })

  it('keeps what is needed, what is reserved and what remains as three separate figures', async () => {
    renderPanel({ requirement: PART_RESERVED })
    await screen.findByLabelText('Equipment')

    expect(panel().getByText('Quantity').parentElement).toHaveTextContent(
      '5 needed · 3 reserved · 2 remaining',
    )
  })

  it('says so plainly when nothing is reserved yet', async () => {
    renderPanel()
    await screen.findByLabelText('Equipment')

    expect(panel().getByText('Quantity').parentElement).toHaveTextContent(
      '5 needed · 0 reserved · 5 remaining',
    )
  })

  it('shows the status it has, from the reservations', async () => {
    renderPanel({ requirement: PART_RESERVED })
    await screen.findByLabelText('Equipment')

    expect(panel().getByText('Status', { selector: 'dt' }).parentElement).toHaveTextContent(
      'In progress — 3 of 5 reserved',
    )
  })

  it('shows the Coordinator’s technical notes, so the choice can be made against them', async () => {
    renderPanel()
    await screen.findByLabelText('Equipment')

    expect(panel().getByText('Technical notes').parentElement).toHaveTextContent(
      'Handheld wireless, for panel Q&A',
    )
  })

  it('says when there are none', async () => {
    renderPanel({ requirement: { ...REQUIREMENT, technical_notes: null } })
    await screen.findByLabelText('Equipment')

    expect(panel().getByText('Technical notes').parentElement).toHaveTextContent('None')
  })

  it('shows the event’s date and time, which is what is checked and held', async () => {
    renderPanel()
    await screen.findByLabelText('Equipment')

    expect(panel().getByText('Event date and time').parentElement).toHaveTextContent(
      formatRange(START, END),
    )
  })

  it('does not ask for the event, the equipment type or the dates again', async () => {
    renderPanel()
    await screen.findByLabelText('Equipment')

    for (const label of ['Event', 'Equipment type', 'Start', 'End']) {
      expect(screen.queryByLabelText(label)).not.toBeInTheDocument()
    }
  })
})

// ---------------------------------------------------------------------------
// Request management: the status and quantity Technical Support owns
// ---------------------------------------------------------------------------

describe('the status', () => {
  it('can be Requested, In review or Unavailable, with the current one chosen', async () => {
    renderPanel({ requirement: { ...REQUIREMENT, status: 'reviewing' } })

    const select = await panel().findByLabelText('Status')
    expect(select).toHaveValue('reviewing')
    expect(Array.from(select.querySelectorAll('option')).map((o) => o.textContent)).toEqual([
      'Requested',
      'In review',
      'Unavailable',
    ])
  })

  it('never offers Reserved: that has to be backed by a real reservation', async () => {
    renderPanel()
    await screen.findByLabelText('Equipment')

    expect(screen.queryByRole('option', { name: /reserved/i })).not.toBeInTheDocument()
  })

  it('shows an Unavailable requirement as such', async () => {
    renderPanel({ requirement: { ...REQUIREMENT, status: 'rejected' } })

    expect(await panel().findByLabelText('Status')).toHaveValue('rejected')
  })

  it('is not a choice once something is reserved: it follows the reservations', async () => {
    renderPanel({ requirement: PART_RESERVED })
    await screen.findByLabelText('Equipment')

    expect(panel().queryByLabelText('Status')).not.toBeInTheDocument()
    expect(panel().getByText(/status follows the reservations/i)).toBeInTheDocument()
  })
})

describe('the quantity needed', () => {
  it('starts at what is needed', async () => {
    renderPanel()

    expect(await panel().findByLabelText('Quantity needed')).toHaveValue(5)
  })

  it('cannot go below what is reserved, and says why', async () => {
    renderPanel({ requirement: PART_RESERVED })

    const input = await panel().findByLabelText('Quantity needed')
    expect(input).toHaveAttribute('min', '3')
    expect(panel().getByText(/cannot go below the 3 reserved/i)).toBeInTheDocument()
  })
})

describe('saving the status and quantity', () => {
  it('has nothing to save until something is changed', async () => {
    renderPanel()

    expect(await panel().findByRole('button', { name: 'Save changes' })).toBeDisabled()
  })

  it('sends only the quantity when only that changed', async () => {
    const user = userEvent.setup()
    mockUpdate.mockResolvedValue({ ...REQUIREMENT, quantity_needed: 8 })
    renderPanel()

    const quantity = await panel().findByLabelText('Quantity needed')
    await user.clear(quantity)
    await user.type(quantity, '8')
    await user.click(panel().getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(mockUpdate).toHaveBeenCalledWith(4, { quantity_needed: 8 }))
  })

  it('can mark the requirement Unavailable', async () => {
    const user = userEvent.setup()
    mockUpdate.mockResolvedValue({ ...REQUIREMENT, status: 'rejected' })
    renderPanel()

    await user.selectOptions(await panel().findByLabelText('Status'), 'Unavailable')
    await user.click(panel().getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(mockUpdate).toHaveBeenCalledWith(4, { status: 'rejected' }))
  })

  it('can mark it In review', async () => {
    const user = userEvent.setup()
    mockUpdate.mockResolvedValue({ ...REQUIREMENT, status: 'reviewing' })
    renderPanel()

    await user.selectOptions(await panel().findByLabelText('Status'), 'In review')
    await user.click(panel().getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(mockUpdate).toHaveBeenCalledWith(4, { status: 'reviewing' }))
  })

  it('hands the server’s answer back and stays open, so the work can go on', async () => {
    const user = userEvent.setup()
    const saved = { ...REQUIREMENT, status: 'reviewing' }
    mockUpdate.mockResolvedValue(saved)
    const { onChanged, onClose } = renderPanel()

    await user.selectOptions(await panel().findByLabelText('Status'), 'In review')
    await user.click(panel().getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(saved))
    expect(await screen.findByRole('status', { name: 'Result' })).toHaveTextContent('Changes saved.')
    expect(onClose).not.toHaveBeenCalled()
  })

  it('does not send a quantity below one', async () => {
    const user = userEvent.setup()
    renderPanel()

    const quantity = await panel().findByLabelText('Quantity needed')
    await user.clear(quantity)
    await user.type(quantity, '0')
    await user.click(panel().getByRole('button', { name: 'Save changes' }))

    expect(await screen.findByText('Quantity must be at least 1.')).toBeInTheDocument()
    expect(mockUpdate).not.toHaveBeenCalled()
  })

  it('does not send a quantity below what is reserved', async () => {
    const user = userEvent.setup()
    renderPanel({ requirement: PART_RESERVED })

    const quantity = await panel().findByLabelText('Quantity needed')
    await user.clear(quantity)
    await user.type(quantity, '2')
    await user.click(panel().getByRole('button', { name: 'Save changes' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/3 already reserved/i)
    expect(mockUpdate).not.toHaveBeenCalled()
  })

  it('shows the server’s reason and changes nothing when it refuses', async () => {
    const user = userEvent.setup()
    mockUpdate.mockRejectedValue(
      new ApiError(409, '3 already reserved; the quantity needed cannot be less than that.'),
    )
    const { onChanged } = renderPanel()

    const quantity = await panel().findByLabelText('Quantity needed')
    await user.clear(quantity)
    await user.type(quantity, '2')
    await user.click(panel().getByRole('button', { name: 'Save changes' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('3 already reserved')
    expect(onChanged).not.toHaveBeenCalled()
  })

  it('says something useful when the server cannot be reached', async () => {
    const user = userEvent.setup()
    mockUpdate.mockRejectedValue(new Error('network down'))
    renderPanel()

    await user.selectOptions(await panel().findByLabelText('Status'), 'In review')
    await user.click(panel().getByRole('button', { name: 'Save changes' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not save/i)
  })
})

// ---------------------------------------------------------------------------
// Choosing the exact equipment
// ---------------------------------------------------------------------------

describe('choosing the equipment', () => {
  it('offers only equipment of the requirement’s type', async () => {
    renderPanel()

    await screen.findByLabelText('Equipment')
    expect(mockCatalogue).toHaveBeenCalledWith({ type: 'Audio' })
  })

  it('lists those items, marking one the Organiser asked for', async () => {
    renderPanel()

    const select = await screen.findByLabelText('Equipment')
    expect(Array.from(select.querySelectorAll('option')).map((o) => o.textContent)).toEqual([
      'Select equipment…',
      'Shure BLX24 (the Organiser asked for 4)',
      'Yamaha PA',
    ])
  })

  it('says the reservation is held for the event’s date and time', async () => {
    renderPanel()

    expect(await screen.findByText(/held for the event’s date and time/i)).toBeInTheDocument()
  })

  it('says when the equipment cannot be loaded', async () => {
    mockCatalogue.mockRejectedValue(new Error('boom'))
    renderPanel()

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load/i)
  })
})

describe('availability, checked as soon as an item is chosen', () => {
  it('asks the existing check for that item, this event and its own window, without being pressed', async () => {
    const user = userEvent.setup()
    renderPanel()

    await choose(user, 'Yamaha PA')

    await waitFor(() => expect(mockCheck).toHaveBeenCalledWith(12, START, END, 7))
  })

  it('has no Check availability button: there is nothing to press', async () => {
    renderPanel()
    await screen.findByLabelText('Equipment')

    expect(screen.queryByRole('button', { name: /check availability/i })).not.toBeInTheDocument()
  })

  it('does not check before anything is chosen', async () => {
    renderPanel()
    await screen.findByLabelText('Equipment')

    expect(mockCheck).not.toHaveBeenCalled()
  })

  it('shows the result inline', async () => {
    const user = userEvent.setup()
    mockCheck.mockResolvedValue(availability({ reserved_quantity: 4, available_quantity: 6 }))
    renderPanel()

    await chooseChecked(user, 'Yamaha PA')

    const result = screen.getByRole('status', { name: 'Availability' })
    expect(result).toHaveTextContent('6 of 10 Yamaha PA available')
    expect(result).toHaveTextContent('4 reserved for overlapping events')
  })

  it('says it is enough when it is', async () => {
    const user = userEvent.setup()
    renderPanel()

    await chooseChecked(user, 'Yamaha PA') // 5 to reserve, 10 free

    expect(screen.getByRole('status', { name: 'Availability' })).toHaveTextContent(
      /enough for the 5 to reserve/i,
    )
  })

  it('says how many are free when it is not enough, and that another item can be chosen', async () => {
    const user = userEvent.setup()
    mockCheck.mockResolvedValue(availability({ reserved_quantity: 8, available_quantity: 2 }))
    renderPanel()

    await chooseChecked(user, 'Yamaha PA')

    const result = screen.getByRole('status', { name: 'Availability' })
    expect(result).toHaveTextContent(/only 2 available; 5 to reserve/i)
    expect(result).toHaveTextContent(/another audio item/i)
  })

  it('checks again for the next item chosen, and shows that one', async () => {
    const user = userEvent.setup()
    mockCheck
      .mockResolvedValueOnce(availability({ equipment_name: 'Yamaha PA', available_quantity: 2 }))
      .mockResolvedValueOnce(
        availability({ equipment_id: 11, equipment_name: 'Shure BLX24', available_quantity: 9 }),
      )
    renderPanel()

    await chooseChecked(user, 'Yamaha PA')
    await user.selectOptions(screen.getByLabelText('Equipment'), 'Shure BLX24 (the Organiser asked for 4)')

    await waitFor(() =>
      expect(screen.getByRole('status', { name: 'Availability' })).toHaveTextContent(
        '9 of 10 Shure BLX24 available',
      ),
    )
    expect(mockCheck).toHaveBeenCalledTimes(2)
  })

  it('says it is checking while it waits', async () => {
    const user = userEvent.setup()
    mockCheck.mockReturnValue(new Promise(() => {})) // never answers
    renderPanel()

    await choose(user, 'Yamaha PA')

    expect(await screen.findByText(/checking availability/i)).toBeInTheDocument()
  })

  it('shows the server’s reason when the check fails', async () => {
    const user = userEvent.setup()
    mockCheck.mockRejectedValue(new ApiError(404, 'Equipment not found'))
    renderPanel()

    await choose(user, 'Yamaha PA')

    expect(await screen.findByRole('alert')).toHaveTextContent('Equipment not found')
  })
})

describe('an item with nothing free', () => {
  async function chooseEmptyItem() {
    const user = userEvent.setup()
    mockCheck.mockResolvedValue(
      availability({ reserved_quantity: 10, available_quantity: 0 }),
    )
    renderPanel()
    await chooseChecked(user, 'Yamaha PA')
    return user
  }

  it('says none are free, and suggests another item of the same type', async () => {
    await chooseEmptyItem()

    const result = screen.getByRole('status', { name: 'Availability' })
    expect(result).toHaveTextContent('0 of 10 Yamaha PA available')
    expect(result).toHaveTextContent(/another audio item/i)
  })

  it('does not mark the requirement Unavailable by itself: another item may do', async () => {
    await chooseEmptyItem()

    expect(mockUpdate).not.toHaveBeenCalled()
    expect(panel().getByLabelText('Status')).toHaveValue('requested')
  })

  it('leaves the other items there to choose', async () => {
    const user = await chooseEmptyItem()

    await user.selectOptions(screen.getByLabelText('Equipment'), 'Shure BLX24 (the Organiser asked for 4)')

    expect(screen.getByLabelText('Equipment')).toHaveValue('11')
  })
})

// ---------------------------------------------------------------------------
// The quantity to reserve
// ---------------------------------------------------------------------------

describe('the quantity to reserve', () => {
  it('starts at what is still needed', async () => {
    const user = userEvent.setup()
    renderPanel({ requirement: PART_RESERVED })

    await chooseChecked(user, 'Yamaha PA')

    expect(screen.getByLabelText('Quantity to reserve')).toHaveValue(2)
  })

  it('is the Organiser’s own when they asked for that item: it is reserved whole', async () => {
    const user = userEvent.setup()
    renderPanel()

    await chooseChecked(user, 'Shure BLX24 (the Organiser asked for 4)')

    expect(screen.queryByLabelText('Quantity to reserve')).not.toBeInTheDocument()
    expect(
      screen.getByText(/the organiser asked for 4; that quantity will be reserved/i),
    ).toBeInTheDocument()
  })

  it('is the panel’s to choose again once the Organiser’s line is already reserved', async () => {
    const user = userEvent.setup()
    mockReservable.mockResolvedValue([
      { ...RESERVABLE, equipment_items: [{ ...RESERVABLE.equipment_items[0], status: 'reserved' }] },
    ])
    renderPanel()

    await chooseChecked(user, 'Shure BLX24')

    expect(screen.getByLabelText('Quantity to reserve')).toBeInTheDocument()
  })

  it('is compared with what is free for that item, not with a different quantity', async () => {
    const user = userEvent.setup()
    mockCheck.mockResolvedValue(availability({ available_quantity: 3 }))
    renderPanel()

    await chooseChecked(user, 'Yamaha PA') // 5 still needed, 3 free
    const quantity = screen.getByLabelText('Quantity to reserve')
    await user.clear(quantity)
    await user.type(quantity, '3')

    expect(screen.getByRole('status', { name: 'Availability' })).toHaveTextContent(
      /enough for the 3 to reserve/i,
    )
  })
})

// ---------------------------------------------------------------------------
// When Reserve is available
// ---------------------------------------------------------------------------

describe('when Reserve is available', () => {
  const reserveButton = () => screen.getByRole('button', { name: 'Reserve' })

  it('is not before an item is chosen', async () => {
    renderPanel()
    await screen.findByLabelText('Equipment')

    expect(reserveButton()).toBeDisabled()
  })

  it('waits for the availability to arrive', async () => {
    const user = userEvent.setup()
    mockCheck.mockReturnValue(new Promise(() => {}))
    renderPanel()

    await choose(user, 'Yamaha PA')

    expect(reserveButton()).toBeDisabled()
  })

  it('is once the item has enough free', async () => {
    const user = userEvent.setup()
    renderPanel()

    await chooseChecked(user, 'Yamaha PA')

    expect(reserveButton()).toBeEnabled()
  })

  it('is not when fewer are free than would be reserved', async () => {
    const user = userEvent.setup()
    mockCheck.mockResolvedValue(availability({ available_quantity: 2 }))
    renderPanel()

    await chooseChecked(user, 'Yamaha PA') // 5 to reserve

    expect(reserveButton()).toBeDisabled()
  })

  it('is not when none are free', async () => {
    const user = userEvent.setup()
    mockCheck.mockResolvedValue(availability({ available_quantity: 0 }))
    renderPanel()

    await chooseChecked(user, 'Yamaha PA')

    expect(reserveButton()).toBeDisabled()
  })

  it('is again if a smaller quantity fits what is free', async () => {
    const user = userEvent.setup()
    mockCheck.mockResolvedValue(availability({ available_quantity: 2 }))
    renderPanel()
    await chooseChecked(user, 'Yamaha PA')

    const quantity = screen.getByLabelText('Quantity to reserve')
    await user.clear(quantity)
    await user.type(quantity, '2')

    expect(reserveButton()).toBeEnabled()
  })

  it('is not for more than the requirement still needs, and says so', async () => {
    const user = userEvent.setup()
    renderPanel({ requirement: PART_RESERVED })
    await chooseChecked(user, 'Yamaha PA')

    const quantity = screen.getByLabelText('Quantity to reserve')
    await user.clear(quantity)
    await user.type(quantity, '4') // only 2 more are needed

    expect(reserveButton()).toBeDisabled()
    expect(screen.getByText(/needs only 2 more/i)).toBeInTheDocument()
  })

  it('is not for a quantity below one', async () => {
    const user = userEvent.setup()
    renderPanel()
    await chooseChecked(user, 'Yamaha PA')

    const quantity = screen.getByLabelText('Quantity to reserve')
    await user.clear(quantity)
    await user.type(quantity, '0')

    expect(reserveButton()).toBeDisabled()
  })

  it('is not when the Organiser’s whole quantity would be more than the requirement needs, and says so', async () => {
    const user = userEvent.setup()
    renderPanel({ requirement: { ...REQUIREMENT, quantity_needed: 2 } }) // the Organiser asked for 4

    await chooseChecked(user, 'Shure BLX24 (the Organiser asked for 4)')

    expect(reserveButton()).toBeDisabled()
    expect(screen.getByText(/takes that whole quantity; this requirement needs only 2 more/i)).toBeInTheDocument()
  })

  it('is left to the server when the check itself failed', async () => {
    const user = userEvent.setup()
    mockCheck.mockRejectedValue(new Error('boom'))
    renderPanel()

    await choose(user, 'Yamaha PA')
    await screen.findByRole('alert')

    expect(reserveButton()).toBeEnabled()
  })
})

// ---------------------------------------------------------------------------
// Reserving
// ---------------------------------------------------------------------------

describe('reserving', () => {
  it('reserves the item for this requirement with the quantity chosen', async () => {
    const user = userEvent.setup()
    const updated = {
      ...REQUIREMENT,
      status: 'reviewing',
      reserved_quantity: 3,
      reservations: [{ equipment_id: 12, equipment_name: 'Yamaha PA', quantity: 3 }],
    }
    mockReserve.mockResolvedValue(updated)
    const { onChanged } = renderPanel()

    await chooseChecked(user, 'Yamaha PA')
    const quantity = screen.getByLabelText('Quantity to reserve')
    await user.clear(quantity)
    await user.type(quantity, '3')
    await user.click(screen.getByRole('button', { name: 'Reserve' }))

    await waitFor(() => expect(mockReserve).toHaveBeenCalledWith(4, 12, 3))
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(updated))
  })

  it('leaves the quantity out for an item the Organiser asked for', async () => {
    const user = userEvent.setup()
    mockReserve.mockResolvedValue({ ...REQUIREMENT, reserved_quantity: 4 })
    renderPanel()

    await chooseChecked(user, 'Shure BLX24 (the Organiser asked for 4)')
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

    await chooseChecked(user, 'Yamaha PA')
    await user.click(screen.getByRole('button', { name: 'Reserve' }))

    expect(await screen.findByRole('status', { name: 'Result' })).toHaveTextContent(
      'Reserved 5 × Yamaha PA',
    )
    expect(screen.getByLabelText('Equipment')).toHaveValue('')
    expect(screen.queryByRole('status', { name: 'Availability' })).not.toBeInTheDocument()
  })

  it('shows the reservation’s own refusal, in its own words, and changes nothing', async () => {
    const user = userEvent.setup()
    mockReserve.mockRejectedValue(
      new ApiError(409, "Only 3 Yamaha PA available for this event's date and time; 5 requested."),
    )
    const { onChanged } = renderPanel()

    await chooseChecked(user, 'Yamaha PA')
    await user.click(screen.getByRole('button', { name: 'Reserve' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Only 3 Yamaha PA available')
    expect(onChanged).not.toHaveBeenCalled()
  })

  it('says something useful when the server cannot be reached', async () => {
    const user = userEvent.setup()
    mockReserve.mockRejectedValue(new Error('network down'))
    renderPanel()

    await chooseChecked(user, 'Yamaha PA')
    await user.click(screen.getByRole('button', { name: 'Reserve' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not reserve/i)
  })

  it('offers no way to release or undo a reservation: nothing can', async () => {
    renderPanel({ requirement: PART_RESERVED })
    await screen.findByLabelText('Equipment')

    expect(
      screen.queryByRole('button', { name: /release|unreserve|cancel reservation|undo/i }),
    ).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// When there is nothing to reserve
// ---------------------------------------------------------------------------

describe('when equipment cannot be reserved yet', () => {
  it('says so for an event with no date and time, and offers no equipment to choose', async () => {
    renderPanel({ event: { id: 7, proposed_start: null, proposed_end: null } })

    expect(await screen.findByText(/no date and time/i)).toBeInTheDocument()
    expect(screen.queryByLabelText('Equipment')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reserve' })).not.toBeInTheDocument()
  })

  it('still lets the status and quantity be managed without a date', async () => {
    const user = userEvent.setup()
    mockUpdate.mockResolvedValue({ ...REQUIREMENT, status: 'rejected' })
    renderPanel({ event: { id: 7, proposed_start: null, proposed_end: null } })

    await user.selectOptions(await panel().findByLabelText('Status'), 'Unavailable')
    await user.click(panel().getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(mockUpdate).toHaveBeenCalledWith(4, { status: 'rejected' }))
  })

  it('says so for a requirement that is already fully reserved', async () => {
    renderPanel({ requirement: FULLY_RESERVED })

    expect(await screen.findByText(/fully reserved/i)).toBeInTheDocument()
    expect(screen.queryByLabelText('Equipment')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reserve' })).not.toBeInTheDocument()
  })

  it('still lets the quantity needed be raised once it is fully reserved', async () => {
    renderPanel({ requirement: FULLY_RESERVED })

    expect(await panel().findByLabelText('Quantity needed')).toHaveAttribute('min', '5')
  })
})

describe('closing', () => {
  it('closes the panel and changes nothing', async () => {
    const user = userEvent.setup()
    const { onClose } = renderPanel()
    await screen.findByLabelText('Equipment')

    await user.click(screen.getByRole('button', { name: 'Close' }))

    expect(onClose).toHaveBeenCalled()
    expect(mockReserve).not.toHaveBeenCalled()
    expect(mockUpdate).not.toHaveBeenCalled()
  })
})
