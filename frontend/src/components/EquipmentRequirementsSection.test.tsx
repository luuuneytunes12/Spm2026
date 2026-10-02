/**
 * Component tests for the Coordinator's Equipment Requirements card.
 *
 * Traceability (see docs/test-cases-equipment-requirements.md):
 *   ER AC1  add equipment: type, quantity needed, technical notes
 *
 * These assert what a Coordinator experiences -- labels, visible text, what
 * is asked of the API -- never CSS class names. The rules themselves (who
 * may record, in which statuses, what is valid) live in the backend and are
 * covered by backend/tests/test_equipment_requirements.py; here
 * `lib/equipmentRequirements` and `lib/equipment` are mocked.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../lib/api'
import { EventStatus } from '../lib/events'
import type { EquipmentLine } from '../lib/events'
import { EquipmentRequirementsSection } from './EquipmentRequirementsSection'

vi.mock('../lib/equipmentRequirements', async () => {
  const actual = await vi.importActual<typeof import('../lib/equipmentRequirements')>(
    '../lib/equipmentRequirements',
  )
  return {
    ...actual, // keep the real window and labels
    listRequirements: vi.fn(),
    addRequirement: vi.fn(),
    updateRequirement: vi.fn(),
    deleteRequirement: vi.fn(),
  }
})
vi.mock('../lib/equipment', () => ({ listEquipment: vi.fn() }))

import { listEquipment } from '../lib/equipment'
import {
  addRequirement,
  deleteRequirement,
  listRequirements,
  updateRequirement,
} from '../lib/equipmentRequirements'
import type { EquipmentRequirement } from '../lib/equipmentRequirements'

const mockList = vi.mocked(listRequirements)
const mockAdd = vi.mocked(addRequirement)
const mockUpdate = vi.mocked(updateRequirement)
const mockDelete = vi.mocked(deleteRequirement)
const mockCatalogue = vi.mocked(listEquipment)

const AUDIO: EquipmentRequirement = {
  id: 1,
  event_id: 7,
  organiser_equipment_request_id: null,
  category: 'Audio',
  quantity_needed: 6,
  technical_notes: 'Handheld wireless, for panel Q&A',
  status: 'requested',
  created_at: '2026-10-01T00:00:00Z',
  updated_at: '2026-10-01T00:00:00Z',
}

const PROJECTION: EquipmentRequirement = {
  ...AUDIO,
  id: 2,
  category: 'Projection',
  quantity_needed: 2,
  technical_notes: null,
}

/** One of the Organiser's picks, as the event record carries it. */
const ORGANISER_PICK: EquipmentLine = {
  id: 31,
  equipment_id: 11,
  equipment_name: 'Shure BLX24 Handheld Microphone',
  equipment_category: 'Audio',
  quantity_requested: 4,
  technical_requirements: 'UHF only',
  status: 'requested',
}

function renderSection(
  props: Partial<{ eventStatus: EventStatus; organiserLines: EquipmentLine[] }> = {},
) {
  return render(
    <EquipmentRequirementsSection
      eventId={7}
      eventStatus={props.eventStatus ?? EventStatus.APPROVED}
      organiserLines={props.organiserLines ?? []}
    />,
  )
}

/** The recorded requirements only. The add form's dropdown also contains
 *  "Audio" as an <option>, so a page-wide text query would find two. */
async function recorded() {
  return within(await screen.findByRole('list', { name: 'Recorded equipment requirements' }))
}

beforeEach(() => {
  vi.clearAllMocks()
  mockList.mockResolvedValue([])
  mockCatalogue.mockResolvedValue({ items: [], types: ['Audio', 'Lighting', 'Projection'] })
})

describe('showing what has been recorded', () => {
  it('lists each requirement with its type, quantity, notes and status', async () => {
    mockList.mockResolvedValue([AUDIO, PROJECTION])
    renderSection()

    const list = await recorded()
    const row = list.getByText('Audio').closest('li')!
    expect(within(row).getByText(/6/)).toBeInTheDocument()
    expect(within(row).getByText('Handheld wireless, for panel Q&A')).toBeInTheDocument()
    expect(within(row).getByText('Requested')).toBeInTheDocument()
    expect(list.getByText('Projection')).toBeInTheDocument()
  })

  it('says so when nothing has been recorded, rather than showing a blank card', async () => {
    renderSection()

    expect(await screen.findByText('No equipment recorded yet.')).toBeInTheDocument()
  })

  it('says so when the requirements cannot be loaded', async () => {
    mockList.mockRejectedValue(new ApiError(500, 'Server error'))
    renderSection()

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load/i)
  })
})

describe('ER AC1 - adding a requirement', () => {
  it('records the type, quantity and notes entered', async () => {
    const user = userEvent.setup()
    mockAdd.mockResolvedValue({ ...AUDIO, id: 9 })
    renderSection()
    await screen.findByText('No equipment recorded yet.')

    await user.selectOptions(await screen.findByLabelText('Equipment type'), 'Audio')
    await user.clear(screen.getByLabelText('Quantity needed'))
    await user.type(screen.getByLabelText('Quantity needed'), '6')
    await user.type(screen.getByLabelText('Technical notes'), 'Handheld wireless')
    await user.click(screen.getByRole('button', { name: 'Add requirement' }))

    await waitFor(() =>
      expect(mockAdd).toHaveBeenCalledWith(7, {
        category: 'Audio',
        quantity_needed: 6,
        technical_notes: 'Handheld wireless',
        organiser_equipment_request_id: null,
      }),
    )
  })

  it('shows the new requirement and clears the form for the next one', async () => {
    const user = userEvent.setup()
    mockAdd.mockResolvedValue({ ...AUDIO, id: 9 })
    renderSection()
    await user.selectOptions(await screen.findByLabelText('Equipment type'), 'Audio')
    await user.type(screen.getByLabelText('Technical notes'), 'Anything')

    await user.click(screen.getByRole('button', { name: 'Add requirement' }))

    expect((await recorded()).getByText('Handheld wireless, for panel Q&A')).toBeInTheDocument()
    expect(screen.getByLabelText('Equipment type')).toHaveValue('')
    expect(screen.getByLabelText('Technical notes')).toHaveValue('')
    expect(screen.getByLabelText('Quantity needed')).toHaveValue(1)
  })

  it('defaults the quantity to one', async () => {
    renderSection()

    expect(await screen.findByLabelText('Quantity needed')).toHaveValue(1)
  })

  it('offers the catalogue’s own equipment types, and no others', async () => {
    renderSection()

    const select = await screen.findByLabelText('Equipment type')
    await waitFor(() =>
      expect(within(select).getAllByRole('option').map((o) => o.textContent)).toEqual([
        'Choose a type',
        'Audio',
        'Lighting',
        'Projection',
      ]),
    )
  })

  it('sends notes as nothing at all when they are left empty', async () => {
    const user = userEvent.setup()
    mockAdd.mockResolvedValue({ ...AUDIO, id: 9, technical_notes: null })
    renderSection()

    await user.selectOptions(await screen.findByLabelText('Equipment type'), 'Lighting')
    await user.click(screen.getByRole('button', { name: 'Add requirement' }))

    await waitFor(() =>
      expect(mockAdd).toHaveBeenCalledWith(
        7,
        expect.objectContaining({ category: 'Lighting', technical_notes: null }),
      ),
    )
  })

  it('asks for a type rather than sending a request without one', async () => {
    const user = userEvent.setup()
    renderSection()

    await user.click(await screen.findByRole('button', { name: 'Add requirement' }))

    expect(await screen.findByText('Choose an equipment type.')).toBeInTheDocument()
    expect(mockAdd).not.toHaveBeenCalled()
  })

  it('shows the server’s reason when it refuses, and keeps what was typed', async () => {
    const user = userEvent.setup()
    mockAdd.mockRejectedValue(
      new ApiError(409, "Equipment can only be recorded once the event is approved; it is 'cancelled'."),
    )
    renderSection()

    await user.selectOptions(await screen.findByLabelText('Equipment type'), 'Audio')
    await user.type(screen.getByLabelText('Technical notes'), 'Keep me')
    await user.click(screen.getByRole('button', { name: 'Add requirement' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/can only be recorded once/)
    expect(screen.getByLabelText('Technical notes')).toHaveValue('Keep me')
  })

  it('still lets you record equipment if the type list cannot be loaded', async () => {
    mockCatalogue.mockRejectedValue(new ApiError(500, 'Server error'))
    renderSection()

    expect(await screen.findByText(/could not load the equipment types/i)).toBeInTheDocument()
  })
})

describe('basing a requirement on the Organiser’s request', () => {
  it('offers the Organiser’s picks, and nothing when they picked nothing', async () => {
    renderSection({ organiserLines: [] })
    await screen.findByLabelText('Equipment type')

    expect(screen.queryByLabelText('Based on the Organiser’s request')).not.toBeInTheDocument()
  })

  it('fills in the form from the pick chosen', async () => {
    const user = userEvent.setup()
    renderSection({ organiserLines: [ORGANISER_PICK] })

    await user.selectOptions(
      await screen.findByLabelText('Based on the Organiser’s request'),
      'Shure BLX24 Handheld Microphone × 4',
    )

    expect(screen.getByLabelText('Equipment type')).toHaveValue('Audio')
    expect(screen.getByLabelText('Quantity needed')).toHaveValue(4)
    expect(screen.getByLabelText('Technical notes')).toHaveValue('UHF only')
  })

  it('remembers which pick it came from', async () => {
    const user = userEvent.setup()
    mockAdd.mockResolvedValue({ ...AUDIO, id: 9, organiser_equipment_request_id: 31 })
    renderSection({ organiserLines: [ORGANISER_PICK] })

    await user.selectOptions(
      await screen.findByLabelText('Based on the Organiser’s request'),
      'Shure BLX24 Handheld Microphone × 4',
    )
    await user.click(screen.getByRole('button', { name: 'Add requirement' }))

    await waitFor(() =>
      expect(mockAdd).toHaveBeenCalledWith(
        7,
        expect.objectContaining({ category: 'Audio', organiser_equipment_request_id: 31 }),
      ),
    )
  })

  it('lets the filled-in values be changed before adding', async () => {
    const user = userEvent.setup()
    mockAdd.mockResolvedValue({ ...AUDIO, id: 9 })
    renderSection({ organiserLines: [ORGANISER_PICK] })
    await user.selectOptions(
      await screen.findByLabelText('Based on the Organiser’s request'),
      'Shure BLX24 Handheld Microphone × 4',
    )

    await user.clear(screen.getByLabelText('Quantity needed'))
    await user.type(screen.getByLabelText('Quantity needed'), '8')
    await user.click(screen.getByRole('button', { name: 'Add requirement' }))

    await waitFor(() =>
      expect(mockAdd).toHaveBeenCalledWith(
        7,
        expect.objectContaining({ quantity_needed: 8, organiser_equipment_request_id: 31 }),
      ),
    )
  })

  it('can go back to a requirement based on nothing', async () => {
    const user = userEvent.setup()
    mockAdd.mockResolvedValue({ ...AUDIO, id: 9 })
    renderSection({ organiserLines: [ORGANISER_PICK] })
    const based = await screen.findByLabelText('Based on the Organiser’s request')
    await user.selectOptions(based, 'Shure BLX24 Handheld Microphone × 4')

    await user.selectOptions(based, 'Not based on a request')
    await user.selectOptions(screen.getByLabelText('Equipment type'), 'Lighting')
    await user.click(screen.getByRole('button', { name: 'Add requirement' }))

    await waitFor(() =>
      expect(mockAdd).toHaveBeenCalledWith(
        7,
        expect.objectContaining({ category: 'Lighting', organiser_equipment_request_id: null }),
      ),
    )
  })
})

describe('editing and removing', () => {
  it('opens a requirement for editing with its values filled in', async () => {
    const user = userEvent.setup()
    mockList.mockResolvedValue([AUDIO])
    renderSection()

    await user.click(await screen.findByRole('button', { name: 'Edit Audio requirement' }))

    const editor = screen.getByRole('group', { name: 'Edit Audio requirement' })
    expect(within(editor).getByLabelText('Equipment type')).toHaveValue('Audio')
    expect(within(editor).getByLabelText('Quantity needed')).toHaveValue(6)
    expect(within(editor).getByLabelText('Technical notes')).toHaveValue(
      'Handheld wireless, for panel Q&A',
    )
  })

  it('saves what was changed', async () => {
    const user = userEvent.setup()
    mockList.mockResolvedValue([AUDIO])
    mockUpdate.mockResolvedValue({ ...AUDIO, quantity_needed: 8 })
    renderSection()
    await user.click(await screen.findByRole('button', { name: 'Edit Audio requirement' }))

    const editor = screen.getByRole('group', { name: 'Edit Audio requirement' })
    await user.clear(within(editor).getByLabelText('Quantity needed'))
    await user.type(within(editor).getByLabelText('Quantity needed'), '8')
    await user.click(within(editor).getByRole('button', { name: 'Save' }))

    await waitFor(() =>
      expect(mockUpdate).toHaveBeenCalledWith(1, {
        category: 'Audio',
        quantity_needed: 8,
        technical_notes: 'Handheld wireless, for panel Q&A',
      }),
    )
    expect((await recorded()).getByText(/8/)).toBeInTheDocument()
    expect(screen.queryByRole('group', { name: 'Edit Audio requirement' })).not.toBeInTheDocument()
  })

  it('leaves everything as it was when the edit is cancelled', async () => {
    const user = userEvent.setup()
    mockList.mockResolvedValue([AUDIO])
    renderSection()
    await user.click(await screen.findByRole('button', { name: 'Edit Audio requirement' }))
    const editor = screen.getByRole('group', { name: 'Edit Audio requirement' })
    await user.clear(within(editor).getByLabelText('Quantity needed'))
    await user.type(within(editor).getByLabelText('Quantity needed'), '99')

    await user.click(within(editor).getByRole('button', { name: 'Cancel' }))

    expect(mockUpdate).not.toHaveBeenCalled()
    expect(screen.queryByRole('group', { name: 'Edit Audio requirement' })).not.toBeInTheDocument()
    expect((await recorded()).getByText('Audio').closest('li')).toHaveTextContent('6')
  })

  it('shows the server’s reason when an edit is refused, and keeps the editor open', async () => {
    const user = userEvent.setup()
    mockList.mockResolvedValue([AUDIO])
    mockUpdate.mockRejectedValue(new ApiError(422, 'Quantity must be at least 1.', ['quantity_needed']))
    renderSection()
    await user.click(await screen.findByRole('button', { name: 'Edit Audio requirement' }))

    await user.click(
      within(screen.getByRole('group', { name: 'Edit Audio requirement' })).getByRole('button', {
        name: 'Save',
      }),
    )

    expect(await screen.findByRole('alert')).toHaveTextContent('Quantity must be at least 1.')
    expect(screen.getByRole('group', { name: 'Edit Audio requirement' })).toBeInTheDocument()
  })

  it('removes a requirement', async () => {
    const user = userEvent.setup()
    mockList.mockResolvedValue([AUDIO, PROJECTION])
    mockDelete.mockResolvedValue(undefined)
    renderSection()

    await user.click(await screen.findByRole('button', { name: 'Remove Audio requirement' }))

    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith(1))
    await waitFor(async () =>
      expect((await recorded()).queryByText('Audio')).not.toBeInTheDocument(),
    )
    expect((await recorded()).getByText('Projection')).toBeInTheDocument()
  })

  it('keeps the requirement and says why when a removal is refused', async () => {
    const user = userEvent.setup()
    mockList.mockResolvedValue([AUDIO])
    mockDelete.mockRejectedValue(new ApiError(409, 'Equipment can only be recorded once…'))
    renderSection()

    await user.click(await screen.findByRole('button', { name: 'Remove Audio requirement' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/can only be recorded/)
    expect((await recorded()).getByText('Audio')).toBeInTheDocument()
  })
})

describe('the status window', () => {
  it.each([EventStatus.APPROVED, EventStatus.PLANNING, EventStatus.CONFIRMED])(
    'lets equipment be recorded while the event is %s',
    async (eventStatus) => {
      mockList.mockResolvedValue([AUDIO])
      renderSection({ eventStatus })

      expect(await screen.findByRole('button', { name: 'Add requirement' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Edit Audio requirement' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Remove Audio requirement' })).toBeInTheDocument()
    },
  )

  it('explains, rather than offering a form, while the event is still under review', async () => {
    renderSection({ eventStatus: EventStatus.UNDER_REVIEW })

    expect(
      await screen.findByText('Equipment can be recorded once the event is approved.'),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add requirement' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Equipment type')).not.toBeInTheDocument()
  })

  it.each([
    EventStatus.DRAFT,
    EventStatus.SUBMITTED,
    EventStatus.UNDER_REVIEW,
    EventStatus.CHANGES_REQUESTED,
    EventStatus.REJECTED,
    EventStatus.COMPLETED,
    EventStatus.CANCELLED,
  ])('offers no way to change anything while the event is %s', async (eventStatus) => {
    mockList.mockResolvedValue([AUDIO])
    renderSection({ eventStatus })

    expect((await recorded()).getByText('Audio')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add requirement' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Edit/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Remove/ })).not.toBeInTheDocument()
  })

  it('still shows what was recorded after the event has finished', async () => {
    mockList.mockResolvedValue([AUDIO])
    renderSection({ eventStatus: EventStatus.COMPLETED })

    expect((await recorded()).getByText('Handheld wireless, for panel Q&A')).toBeInTheDocument()
  })
})
