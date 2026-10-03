/**
 * Component tests for Technical Support's status and quantity editor.
 *
 * Traceability (see docs/test-cases-equipment-requirements.md):
 *   UR AC1  update the status of a requirement ("reserved", "unavailable")
 *   UR AC2  update the quantity as changes appear
 *
 * Which statuses may be set, and that the quantity cannot go below what is
 * reserved, are the backend's rules (backend/tests/
 * test_equipment_requirement_fulfillment.py). The editor mirrors them so the
 * person is never offered something the server will refuse, and shows the
 * server's own reason when it does.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../lib/api'
import { RequirementStatusEditor } from './RequirementStatusEditor'

vi.mock('../lib/equipmentRequirements', async () => {
  const actual = await vi.importActual<typeof import('../lib/equipmentRequirements')>(
    '../lib/equipmentRequirements',
  )
  return { ...actual, updateSupportRequirement: vi.fn() }
})

import { updateSupportRequirement } from '../lib/equipmentRequirements'
import type { SupportRequirement } from '../lib/equipmentRequirements'

const mockUpdate = vi.mocked(updateSupportRequirement)

const AUDIO: SupportRequirement = {
  id: 4,
  category: 'Audio',
  quantity_needed: 5,
  technical_notes: null,
  status: 'requested',
  reserved_quantity: 0,
  reservations: [],
}

const PART_RESERVED: SupportRequirement = {
  ...AUDIO,
  status: 'reviewing',
  reserved_quantity: 3,
  reservations: [{ equipment_id: 11, equipment_name: 'Shure BLX24', quantity: 3 }],
}

function renderEditor(requirement = AUDIO) {
  const onSaved = vi.fn()
  const onCancel = vi.fn()
  render(<RequirementStatusEditor requirement={requirement} onSaved={onSaved} onCancel={onCancel} />)
  return { onSaved, onCancel }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('the status control', () => {
  it('offers Requested, Reviewing and Unavailable, with the current one chosen', () => {
    renderEditor({ ...AUDIO, status: 'reviewing' })

    const select = screen.getByLabelText('Status')
    expect(select).toHaveValue('reviewing')
    expect(Array.from(select.querySelectorAll('option')).map((o) => o.textContent)).toEqual([
      'Requested',
      'Reviewing',
      'Unavailable',
    ])
  })

  it('never offers Reserved: it has to be backed by a real reservation', () => {
    renderEditor()

    expect(screen.queryByRole('option', { name: 'Reserved' })).not.toBeInTheDocument()
  })

  it('shows an Unavailable requirement as such', () => {
    renderEditor({ ...AUDIO, status: 'rejected' })

    expect(screen.getByLabelText('Status')).toHaveValue('rejected')
  })

  it('is replaced by an explanation once something is reserved', () => {
    renderEditor(PART_RESERVED)

    expect(screen.queryByLabelText('Status')).not.toBeInTheDocument()
    expect(screen.getByText(/status follows the reservations/i)).toBeInTheDocument()
  })
})

describe('the quantity control', () => {
  it('starts at the quantity needed', () => {
    renderEditor()

    expect(screen.getByLabelText('Quantity needed')).toHaveValue(5)
  })

  it('cannot go below what is already reserved, and says why', () => {
    renderEditor(PART_RESERVED)

    expect(screen.getByLabelText('Quantity needed')).toHaveAttribute('min', '3')
    expect(screen.getByText(/3 already reserved/i)).toBeInTheDocument()
  })
})

describe('saving', () => {
  it('sends only what was changed', async () => {
    const user = userEvent.setup()
    mockUpdate.mockResolvedValue({ ...AUDIO, quantity_needed: 8 })
    renderEditor()

    await user.clear(screen.getByLabelText('Quantity needed'))
    await user.type(screen.getByLabelText('Quantity needed'), '8')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(mockUpdate).toHaveBeenCalledWith(4, { quantity_needed: 8 }))
  })

  it('can mark a requirement Unavailable', async () => {
    const user = userEvent.setup()
    mockUpdate.mockResolvedValue({ ...AUDIO, status: 'rejected' })
    renderEditor()

    await user.selectOptions(screen.getByLabelText('Status'), 'Unavailable')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(mockUpdate).toHaveBeenCalledWith(4, { status: 'rejected' }))
  })

  it('hands the server’s answer back, so the row shows exactly what was stored', async () => {
    const user = userEvent.setup()
    const saved = { ...AUDIO, status: 'reviewing' }
    mockUpdate.mockResolvedValue(saved)
    const { onSaved } = renderEditor()

    await user.selectOptions(screen.getByLabelText('Status'), 'Reviewing')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(saved))
  })

  it('has nothing to save until something is changed', () => {
    renderEditor()

    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled()
  })

  it('does not send a quantity below one', async () => {
    const user = userEvent.setup()
    renderEditor()

    await user.clear(screen.getByLabelText('Quantity needed'))
    await user.type(screen.getByLabelText('Quantity needed'), '0')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    expect(await screen.findByText('Quantity must be at least 1.')).toBeInTheDocument()
    expect(mockUpdate).not.toHaveBeenCalled()
  })

  it('does not send a quantity below what is reserved', async () => {
    const user = userEvent.setup()
    renderEditor(PART_RESERVED)

    await user.clear(screen.getByLabelText('Quantity needed'))
    await user.type(screen.getByLabelText('Quantity needed'), '2')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/3 already reserved/i)
    expect(mockUpdate).not.toHaveBeenCalled()
  })

  it('shows the server’s reason and stays open when it refuses', async () => {
    const user = userEvent.setup()
    mockUpdate.mockRejectedValue(
      new ApiError(409, '3 already reserved; the quantity needed cannot be less than that.'),
    )
    const { onSaved } = renderEditor()

    await user.clear(screen.getByLabelText('Quantity needed'))
    await user.type(screen.getByLabelText('Quantity needed'), '2')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('3 already reserved')
    expect(onSaved).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeInTheDocument()
  })

  it('says something useful when the server cannot be reached', async () => {
    const user = userEvent.setup()
    mockUpdate.mockRejectedValue(new Error('network down'))
    renderEditor()

    await user.selectOptions(screen.getByLabelText('Status'), 'Reviewing')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not/i)
  })
})

describe('cancelling', () => {
  it('closes the editor and changes nothing', async () => {
    const user = userEvent.setup()
    const { onCancel } = renderEditor()

    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(onCancel).toHaveBeenCalled()
    expect(mockUpdate).not.toHaveBeenCalled()
  })
})
