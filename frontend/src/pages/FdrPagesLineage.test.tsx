import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

const { apiMocks } = vi.hoisted(() => ({ apiMocks: { instrument: vi.fn(), history: vi.fn() } }))
vi.mock('../auth/AuthProvider', () => ({ useAuth: () => ({ user: { role: 'auditor' } }) }))
vi.mock('../lib/api', () => ({ api: apiMocks, ApiError: class ApiError extends Error {} }))

import { InstrumentDetailPage } from './FdrPages'

describe('instrument lineage navigation', () => {
  beforeEach(() => {
    apiMocks.instrument.mockReset().mockResolvedValue({
      id: 'chain-middle', institution_id: 'synthetic-institution', obligation_id: null, submitted_by_user_id: null,
      supersedes_instrument_id: 'chain-before', successor_instrument_id: 'chain-after', replacement_type: 'renewal',
      issuer_name: 'Synthetic Issuer', beneficiary: null, reference_original: 'SYN-MIDDLE', reference_normalized: 'SYNMIDDLE',
      amount: '1000.00', issue_date: '2026-01-01', maturity_date: '2027-01-01', lifecycle_status: 'approved',
      verification_status: 'reviewed', priority: 'normal', data_origin: 'synthetic_demo', notes: null,
      created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
    })
    apiMocks.history.mockReset().mockResolvedValue({ instrument_id: 'chain-middle', events: [] })
  })

  it('links to both the predecessor and successor from an intermediate record', async () => {
    render(<MemoryRouter initialEntries={['/fdrs/chain-middle']}><Routes><Route path="/fdrs/:id" element={<InstrumentDetailPage />} /></Routes></MemoryRouter>)
    expect(await screen.findByRole('link', { name: /open predecessor record/i })).toHaveAttribute('href', '/fdrs/chain-before')
    expect(screen.getByRole('link', { name: /open successor record/i })).toHaveAttribute('href', '/fdrs/chain-after')
  })
})
