import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const { apiMocks } = vi.hoisted(() => ({ apiMocks: { institutions: vi.fn() } }))
vi.mock('../lib/api', () => ({ api: apiMocks }))

import { InstitutionsPage } from './InstitutionsPage'

describe('institution directory', () => {
  beforeEach(() => apiMocks.institutions.mockReset().mockResolvedValue({
    items: [{ id: 'institution-real-id', code: 'SYN-004', name: 'Synthetic Technical Institute', address: 'Synthetic District', active: true, data_origin: 'synthetic_demo', created_at: '2026-01-01T00:00:00Z', updated_at: '2026-02-01T00:00:00Z' }],
    total: 1, limit: 25, offset: 0,
  }))

  it('renders real directory results and filters them through the supported API parameters', async () => {
    render(<MemoryRouter><InstitutionsPage /></MemoryRouter>)
    expect(await screen.findByRole('link', { name: 'Synthetic Technical Institute' })).toHaveAttribute('href', '/institutions/institution-real-id')
    fireEvent.change(screen.getByRole('textbox', { name: 'Search institution name or code' }), { target: { value: 'SYN-004' } })
    expect(apiMocks.institutions).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'SYN-004', active: true, limit: 25, offset: 0 }))
  })
})
