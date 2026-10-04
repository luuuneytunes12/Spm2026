/**
 * Component tests for the Coordinator's Equipment Requirements card.
 *
 * Traceability (see docs/test-cases-equipment-requirements.md):
 *   ER AC1  add equipment: type, quantity needed, technical notes
 *   ER AC1  the Organiser's request is shown read-only as planning context,
 *           and a requirement may, or may not, be based on one of its lines
 *   UR AC3  the status and quantity Technical Support sets are visible here,
 *           with how much is reserved; and what is reserved is protected
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
  reserved_quantity: 0,
  reservations: [],
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
  props: Partial<{
    eventStatus: EventStatus
    organiserLines: EquipmentLine[]
    organiserNotes: string | null
  }> = {},
) {
  return render(
    <EquipmentRequirementsSection
      eventId={7}
      eventStatus={props.eventStatus ?? EventStatus.APPROVED}
      organiserLines={props.organiserLines ?? []}
      organiserNotes={props.organiserNotes ?? null}
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

    expect(await screen.findByText('No Coordinator equipment requirements recorded yet.')).toBeInTheDocument()
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
    await screen.findByText('No Coordinator equipment requirements recorded yet.')

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

describe('the Organiser’s request, shown as planning context', () => {
  it('shows what the Organiser asked for, read-only', async () => {
    renderSection({ organiserLines: [ORGANISER_PICK] })

    const context = within(await screen.findByRole('region', { name: 'Requested by the Organiser' }))
    expect(context.getByText('Shure BLX24 Handheld Microphone')).toBeInTheDocument()
    expect(context.getByText('Audio')).toBeInTheDocument()
    expect(context.getByText('UHF only')).toBeInTheDocument()
    expect(context.getByText('× 4')).toBeInTheDocument()
    // Context, not a form: nothing in it can be typed into, chosen or pressed.
    expect(context.queryByRole('textbox')).not.toBeInTheDocument()
    expect(context.queryByRole('combobox')).not.toBeInTheDocument()
    expect(context.queryByRole('button')).not.toBeInTheDocument()
  })

  it('shows the Organiser’s other equipment notes', async () => {
    renderSection({
      organiserLines: [ORGANISER_PICK],
      organiserNotes: 'Stage left, near the fire exit',
    })

    const context = within(await screen.findByRole('region', { name: 'Requested by the Organiser' }))
    expect(context.getByText('Other equipment notes')).toBeInTheDocument()
    expect(context.getByText('Stage left, near the fire exit')).toBeInTheDocument()
  })

  it('says so when the Organiser asked for no equipment', async () => {
    renderSection({ organiserLines: [] })

    const context = within(await screen.findByRole('region', { name: 'Requested by the Organiser' }))
    expect(context.getByText('No equipment requested.')).toBeInTheDocument()
  })

  it.each([null, '', '   '])('leaves the notes row out when the Organiser wrote %j', async (notes) => {
    renderSection({ organiserLines: [ORGANISER_PICK], organiserNotes: notes })

    const context = within(await screen.findByRole('region', { name: 'Requested by the Organiser' }))
    expect(context.queryByText('Other equipment notes')).not.toBeInTheDocument()
  })

  it('is still shown while nothing can be recorded', async () => {
    renderSection({
      eventStatus: EventStatus.UNDER_REVIEW,
      organiserLines: [ORGANISER_PICK],
      organiserNotes: 'Stage left',
    })

    const context = within(await screen.findByRole('region', { name: 'Requested by the Organiser' }))
    expect(context.getByText('Shure BLX24 Handheld Microphone')).toBeInTheDocument()
    expect(context.getByText('Stage left')).toBeInTheDocument()
  })

  it('says it is for reference and is not copied into the requirements', async () => {
    renderSection({ organiserLines: [ORGANISER_PICK] })

    expect(
      await screen.findByText('For reference. It is not copied into your requirements.'),
    ).toBeInTheDocument()
  })

  it('never copies the Organiser’s notes into a requirement’s technical notes', async () => {
    const user = userEvent.setup()
    mockAdd.mockResolvedValue({ ...AUDIO, id: 9, technical_notes: null })
    renderSection({ organiserLines: [], organiserNotes: 'Need a lectern microphone' })

    expect(await screen.findByLabelText('Technical notes')).toHaveValue('')
    await user.selectOptions(screen.getByLabelText('Equipment type'), 'Lighting')
    await user.click(screen.getByRole('button', { name: 'Add requirement' }))

    await waitFor(() =>
      expect(mockAdd).toHaveBeenCalledWith(
        7,
        expect.objectContaining({ category: 'Lighting', technical_notes: null }),
      ),
    )
  })
})

describe('basing a requirement on an Organiser equipment request (optional)', () => {
  const BASED_ON = 'Based on organiser equipment request (optional)'
  const PICK_OPTION = 'Shure BLX24 Handheld Microphone × 4'

  it('is not offered when the Organiser requested nothing', async () => {
    renderSection({ organiserLines: [] })
    await screen.findByLabelText('Equipment type')

    expect(screen.queryByLabelText(BASED_ON)).not.toBeInTheDocument()
  })

  it('offers the Organiser’s requests, with “Not based on an organiser request” as the empty choice', async () => {
    renderSection({ organiserLines: [ORGANISER_PICK] })

    const select = await screen.findByLabelText(BASED_ON)
    expect(within(select).getAllByRole('option').map((o) => o.textContent)).toEqual([
      'Not based on an organiser request',
      PICK_OPTION,
    ])
    expect(select).toHaveValue('')
  })

  it('fills in the equipment type and quantity from the request chosen', async () => {
    const user = userEvent.setup()
    renderSection({ organiserLines: [ORGANISER_PICK] })
    await waitFor(() => expect(mockCatalogue).toHaveBeenCalled())

    await user.selectOptions(await screen.findByLabelText(BASED_ON), PICK_OPTION)

    await waitFor(() => expect(screen.getByLabelText('Equipment type')).toHaveValue('Audio'))
    expect(screen.getByLabelText('Quantity needed')).toHaveValue(4)
  })

  it('does not fill in technical notes, which are the Coordinator’s own words', async () => {
    const user = userEvent.setup()
    renderSection({ organiserLines: [ORGANISER_PICK] })

    await user.selectOptions(await screen.findByLabelText(BASED_ON), PICK_OPTION)

    // The pick carries "UHF only"; that stays on the Organiser's side.
    expect(screen.getByLabelText('Technical notes')).toHaveValue('')
  })

  it('leaves notes already typed alone when a request is chosen', async () => {
    const user = userEvent.setup()
    renderSection({ organiserLines: [ORGANISER_PICK] })
    await user.type(await screen.findByLabelText('Technical notes'), 'Lapel clips please')

    await user.selectOptions(screen.getByLabelText(BASED_ON), PICK_OPTION)

    expect(screen.getByLabelText('Technical notes')).toHaveValue('Lapel clips please')
  })

  it('lets the filled-in values be changed before adding', async () => {
    const user = userEvent.setup()
    mockAdd.mockResolvedValue({ ...AUDIO, id: 9, quantity_needed: 8 })
    renderSection({ organiserLines: [ORGANISER_PICK] })
    await user.selectOptions(await screen.findByLabelText(BASED_ON), PICK_OPTION)

    await user.selectOptions(screen.getByLabelText('Equipment type'), 'Lighting')
    await user.clear(screen.getByLabelText('Quantity needed'))
    await user.type(screen.getByLabelText('Quantity needed'), '8')
    await user.click(screen.getByRole('button', { name: 'Add requirement' }))

    await waitFor(() =>
      expect(mockAdd).toHaveBeenCalledWith(
        7,
        expect.objectContaining({
          category: 'Lighting',
          quantity_needed: 8,
          organiser_equipment_request_id: 31,
        }),
      ),
    )
  })

  it('remembers which Organiser request it was based on', async () => {
    const user = userEvent.setup()
    mockAdd.mockResolvedValue({ ...AUDIO, id: 9, organiser_equipment_request_id: 31 })
    renderSection({ organiserLines: [ORGANISER_PICK] })

    await user.selectOptions(await screen.findByLabelText(BASED_ON), PICK_OPTION)
    await user.click(screen.getByRole('button', { name: 'Add requirement' }))

    await waitFor(() =>
      expect(mockAdd).toHaveBeenCalledWith(
        7,
        expect.objectContaining({ category: 'Audio', organiser_equipment_request_id: 31 }),
      ),
    )
  })

  it('can add an independent requirement even though the Organiser requested equipment', async () => {
    const user = userEvent.setup()
    mockAdd.mockResolvedValue({ ...AUDIO, id: 9, category: 'Lighting' })
    renderSection({ organiserLines: [ORGANISER_PICK] })

    await user.selectOptions(await screen.findByLabelText('Equipment type'), 'Lighting')
    await user.type(screen.getByLabelText('Technical notes'), 'Two warm wash lights')
    await user.click(screen.getByRole('button', { name: 'Add requirement' }))

    await waitFor(() =>
      expect(mockAdd).toHaveBeenCalledWith(7, {
        category: 'Lighting',
        quantity_needed: 1,
        technical_notes: 'Two warm wash lights',
        organiser_equipment_request_id: null,
      }),
    )
  })

  it('can go back to a requirement based on nothing', async () => {
    const user = userEvent.setup()
    mockAdd.mockResolvedValue({ ...AUDIO, id: 9 })
    renderSection({ organiserLines: [ORGANISER_PICK] })
    const based = await screen.findByLabelText(BASED_ON)
    await user.selectOptions(based, PICK_OPTION)

    await user.selectOptions(based, 'Not based on an organiser request')
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

describe('adding is immediate', () => {
  it('tells the Coordinator that Technical Support will see it', async () => {
    renderSection()

    expect(
      await screen.findByText('Once added, this requirement will be visible to Technical Support.'),
    ).toBeInTheDocument()
  })

  it('has no separate draft or submit step', async () => {
    const user = userEvent.setup()
    mockAdd.mockResolvedValue({ ...AUDIO, id: 9 })
    renderSection()
    await user.selectOptions(await screen.findByLabelText('Equipment type'), 'Audio')

    expect(screen.queryByRole('button', { name: /draft|submit/i })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Add requirement' }))

    // One click, one save, shown as requested.
    await waitFor(() => expect(mockAdd).toHaveBeenCalledTimes(1))
    expect((await recorded()).getByText('Requested')).toBeInTheDocument()
  })

  it('does not make the promise where nothing can be added', async () => {
    renderSection({ eventStatus: EventStatus.UNDER_REVIEW })
    await screen.findByText('Equipment can be recorded once the event is approved.')

    expect(
      screen.queryByText('Once added, this requirement will be visible to Technical Support.'),
    ).not.toBeInTheDocument()
  })
})

describe('where a requirement came from', () => {
  const LINKED: EquipmentRequirement = { ...AUDIO, id: 3, organiser_equipment_request_id: 31 }
  const ORIGIN = 'Based on organiser equipment request: Shure BLX24 Handheld Microphone × 4'

  it('names the Organiser request a requirement was based on', async () => {
    mockList.mockResolvedValue([LINKED])
    renderSection({ organiserLines: [ORGANISER_PICK] })

    const row = (await recorded()).getByText('Audio').closest('li')!
    expect(row).toHaveTextContent(ORIGIN)
    expect(row).not.toHaveTextContent('Coordinator-added requirement')
  })

  it('labels one with no Organiser request as a Coordinator-added requirement', async () => {
    mockList.mockResolvedValue([AUDIO])
    renderSection({ organiserLines: [ORGANISER_PICK] })

    const row = (await recorded()).getByText('Audio').closest('li')!
    expect(row).toHaveTextContent('Coordinator-added requirement')
    expect(row).not.toHaveTextContent('Based on organiser equipment request')
  })

  it('does not call a requirement Coordinator-added when its request is not among those on this page', async () => {
    // A page opened before an approved change replaced the Organiser's list
    // still holds the old link. It is a link, not an independent requirement.
    mockList.mockResolvedValue([{ ...AUDIO, organiser_equipment_request_id: 999 }])
    renderSection({ organiserLines: [ORGANISER_PICK] })

    const row = (await recorded()).getByText('Audio').closest('li')!
    expect(row).toHaveTextContent('Based on an organiser equipment request')
    expect(row).not.toHaveTextContent('Coordinator-added requirement')
  })

  it('shows the origin as soon as a based-on requirement is added', async () => {
    const user = userEvent.setup()
    mockAdd.mockResolvedValue({ ...AUDIO, id: 9, organiser_equipment_request_id: 31 })
    renderSection({ organiserLines: [ORGANISER_PICK] })

    await user.selectOptions(
      await screen.findByLabelText('Based on organiser equipment request (optional)'),
      'Shure BLX24 Handheld Microphone × 4',
    )
    await user.click(screen.getByRole('button', { name: 'Add requirement' }))

    expect((await recorded()).getByText('Audio').closest('li')).toHaveTextContent(ORIGIN)
  })

  it('shows an independent requirement as Coordinator-added as soon as it is added', async () => {
    const user = userEvent.setup()
    mockAdd.mockResolvedValue({ ...AUDIO, id: 9 })
    renderSection({ organiserLines: [ORGANISER_PICK] })

    await user.selectOptions(await screen.findByLabelText('Equipment type'), 'Audio')
    await user.click(screen.getByRole('button', { name: 'Add requirement' }))

    expect((await recorded()).getByText('Audio').closest('li')).toHaveTextContent(
      'Coordinator-added requirement',
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
    await user.click(within(editor).getByRole('button', { name: 'Save changes' }))

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
        name: 'Save changes',
      }),
    )

    expect(await screen.findByRole('alert')).toHaveTextContent('Quantity must be at least 1.')
    expect(screen.getByRole('group', { name: 'Edit Audio requirement' })).toBeInTheDocument()
  })

  it('keeps the add form distinguishable from an editor open at the same time', async () => {
    const user = userEvent.setup()
    mockList.mockResolvedValue([AUDIO])
    renderSection()
    await user.click(await screen.findByRole('button', { name: 'Edit Audio requirement' }))

    // Both forms carry "Equipment type", "Quantity needed" and "Technical
    // notes". Only the add form has a title, and the editor is its own group.
    expect(screen.getByRole('heading', { name: 'Add a requirement' })).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Edit Audio requirement' })).toBeInTheDocument()
  })

  it('is saved with “Save changes”, not just “Save”', async () => {
    const user = userEvent.setup()
    mockList.mockResolvedValue([AUDIO])
    renderSection()
    await user.click(await screen.findByRole('button', { name: 'Edit Audio requirement' }))

    const editor = within(screen.getByRole('group', { name: 'Edit Audio requirement' }))
    expect(editor.getByRole('button', { name: 'Save changes' })).toBeInTheDocument()
    expect(editor.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument()
  })

  it('shows the Organiser request it was based on, read-only', async () => {
    const user = userEvent.setup()
    mockList.mockResolvedValue([{ ...AUDIO, organiser_equipment_request_id: 31 }])
    renderSection({ organiserLines: [ORGANISER_PICK] })
    await user.click(await screen.findByRole('button', { name: 'Edit Audio requirement' }))

    const editor = screen.getByRole('group', { name: 'Edit Audio requirement' })
    expect(editor).toHaveTextContent(
      'Based on organiser equipment request: Shure BLX24 Handheld Microphone × 4',
    )
    // Text, not a control: only the type is a dropdown here, so the request
    // cannot be swapped for a different one.
    expect(within(editor).queryByLabelText(/based on organiser equipment request/i)).not.toBeInTheDocument()
    expect(within(editor).getAllByRole('combobox')).toHaveLength(1)
  })

  it('says Coordinator-added in the editor of an independent requirement', async () => {
    const user = userEvent.setup()
    mockList.mockResolvedValue([AUDIO])
    renderSection({ organiserLines: [ORGANISER_PICK] })
    await user.click(await screen.findByRole('button', { name: 'Edit Audio requirement' }))

    const editor = screen.getByRole('group', { name: 'Edit Audio requirement' })
    expect(editor).toHaveTextContent('Coordinator-added requirement')
    expect(within(editor).getAllByRole('combobox')).toHaveLength(1)
  })

  it('changes only type, quantity and notes, and keeps the link to the Organiser request', async () => {
    const user = userEvent.setup()
    const linked = { ...AUDIO, organiser_equipment_request_id: 31 }
    mockList.mockResolvedValue([linked])
    mockUpdate.mockResolvedValue({ ...linked, quantity_needed: 5 })
    renderSection({ organiserLines: [ORGANISER_PICK] })
    await user.click(await screen.findByRole('button', { name: 'Edit Audio requirement' }))

    const editor = within(screen.getByRole('group', { name: 'Edit Audio requirement' }))
    await user.clear(editor.getByLabelText('Quantity needed'))
    await user.type(editor.getByLabelText('Quantity needed'), '5')
    await user.click(editor.getByRole('button', { name: 'Save changes' }))

    // Exactly these three: no link in the request, so none can be retargeted.
    await waitFor(() =>
      expect(mockUpdate).toHaveBeenCalledWith(1, {
        category: 'Audio',
        quantity_needed: 5,
        technical_notes: 'Handheld wireless, for panel Q&A',
      }),
    )
    expect((await recorded()).getByText('Audio').closest('li')).toHaveTextContent(
      'Based on organiser equipment request: Shure BLX24 Handheld Microphone × 4',
    )
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

describe('once Technical Support has reserved equipment', () => {
  // The add form also has Quantity and Technical notes, so an open editor is
  // always looked at on its own.
  const editor = () => within(screen.getByRole('group', { name: 'Edit Audio requirement' }))

  const PART_RESERVED: EquipmentRequirement = {
    ...AUDIO,
    status: 'reviewing',
    reserved_quantity: 3,
    reservations: [{ equipment_id: 11, equipment_name: 'Shure BLX24', quantity: 3 }],
  }

  it('shows how far it has got, keeping what is needed distinct', async () => {
    mockList.mockResolvedValue([PART_RESERVED])
    renderSection()

    const row = (await recorded()).getByText('Audio').closest('li')!
    expect(within(row).getByText('In progress — 3 of 6 reserved')).toBeInTheDocument()
    expect(within(row).getByText(/× 6/)).toBeInTheDocument()
    expect(row).toHaveTextContent('3 × Shure BLX24')
  })

  it('reads Reserved when all of it is', async () => {
    mockList.mockResolvedValue([
      {
        ...PART_RESERVED,
        status: 'reserved',
        reserved_quantity: 6,
        reservations: [{ equipment_id: 11, equipment_name: 'Shure BLX24', quantity: 6 }],
      },
    ])
    renderSection()

    const row = (await recorded()).getByText('Audio').closest('li')!
    expect(within(row).getByText('Reserved — 6 of 6')).toBeInTheDocument()
  })

  it('shows Unavailable when Technical Support could not provide it', async () => {
    mockList.mockResolvedValue([{ ...AUDIO, status: 'rejected' }])
    renderSection()

    const row = (await recorded()).getByText('Audio').closest('li')!
    expect(within(row).getByText('Unavailable')).toBeInTheDocument()
  })

  it('takes away Remove from a requirement that has equipment reserved', async () => {
    mockList.mockResolvedValue([PART_RESERVED, PROJECTION])
    renderSection()
    await recorded()

    expect(screen.queryByRole('button', { name: 'Remove Audio requirement' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Remove Projection requirement' })).toBeInTheDocument()
  })

  it('still lets it be edited', async () => {
    mockList.mockResolvedValue([PART_RESERVED])
    renderSection()
    await recorded()

    expect(screen.getByRole('button', { name: 'Edit Audio requirement' })).toBeInTheDocument()
  })

  it('locks the equipment type in the editor, and says why', async () => {
    const user = userEvent.setup()
    mockList.mockResolvedValue([PART_RESERVED])
    renderSection()
    await recorded()

    await user.click(screen.getByRole('button', { name: 'Edit Audio requirement' }))

    expect(editor().getByLabelText('Equipment type')).toBeDisabled()
    expect(editor().getByText(/equipment is reserved for this requirement/i)).toBeInTheDocument()
  })

  it('keeps the quantity at or above what is reserved', async () => {
    const user = userEvent.setup()
    mockList.mockResolvedValue([PART_RESERVED])
    renderSection()
    await recorded()

    await user.click(screen.getByRole('button', { name: 'Edit Audio requirement' }))

    expect(editor().getByLabelText('Quantity needed')).toHaveAttribute('min', '3')
  })

  it('does not send a quantity below what is reserved', async () => {
    const user = userEvent.setup()
    mockList.mockResolvedValue([PART_RESERVED])
    renderSection()
    await recorded()
    await user.click(screen.getByRole('button', { name: 'Edit Audio requirement' }))

    await user.clear(editor().getByLabelText('Quantity needed'))
    await user.type(editor().getByLabelText('Quantity needed'), '2')
    await user.click(editor().getByRole('button', { name: 'Save changes' }))

    expect(await screen.findByText(/3 already reserved/i)).toBeInTheDocument()
    expect(mockUpdate).not.toHaveBeenCalled()
  })

  it('lets the notes change', async () => {
    const user = userEvent.setup()
    mockList.mockResolvedValue([PART_RESERVED])
    mockUpdate.mockResolvedValue({ ...PART_RESERVED, technical_notes: 'Lapel clips too' })
    renderSection()
    await recorded()
    await user.click(screen.getByRole('button', { name: 'Edit Audio requirement' }))

    await user.clear(editor().getByLabelText('Technical notes'))
    await user.type(editor().getByLabelText('Technical notes'), 'Lapel clips too')
    await user.click(editor().getByRole('button', { name: 'Save changes' }))

    await waitFor(() =>
      expect(mockUpdate).toHaveBeenCalledWith(
        1,
        expect.objectContaining({ technical_notes: 'Lapel clips too' }),
      ),
    )
  })

  it('shows the progress the server answers with after a save', async () => {
    const user = userEvent.setup()
    mockList.mockResolvedValue([PART_RESERVED])
    mockUpdate.mockResolvedValue({ ...PART_RESERVED, quantity_needed: 8 })
    renderSection()
    await recorded()
    await user.click(screen.getByRole('button', { name: 'Edit Audio requirement' }))

    await user.clear(editor().getByLabelText('Quantity needed'))
    await user.type(editor().getByLabelText('Quantity needed'), '8')
    await user.click(editor().getByRole('button', { name: 'Save changes' }))

    const row = (await recorded()).getByText('Audio').closest('li')!
    await waitFor(() =>
      expect(within(row).getByText('In progress — 3 of 8 reserved')).toBeInTheDocument(),
    )
  })

  it('shows the server’s reason when it refuses to remove one', async () => {
    const user = userEvent.setup()
    mockList.mockResolvedValue([AUDIO])
    mockDelete.mockRejectedValue(
      new ApiError(409, 'Equipment is already reserved for this requirement, so it cannot be removed.'),
    )
    renderSection()
    await recorded()

    await user.click(screen.getByRole('button', { name: 'Remove Audio requirement' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/already reserved/i)
    expect((await recorded()).getByText('Audio')).toBeInTheDocument()
  })
})
