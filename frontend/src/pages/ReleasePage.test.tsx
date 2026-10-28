import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const { apiMocks, authState } = vi.hoisted(() => ({
  apiMocks: {
    releaseReport: vi.fn(),
    releaseRequest: vi.fn(),
    evaluateRelease: vi.fn(),
    decideRelease: vi.fn(),
  },
  authState: { role: 'auditor' },
}))

vi.mock('../auth/AuthProvider', () => ({ useAuth: () => ({ user: { role: authState.role } }) }))
vi.mock('../lib/api', () => ({
  api: apiMocks,
  ApiError: class ApiError extends Error {},
}))

import { ReleasePage } from './ReleasePage'

describe('release page role controls', () => {
  beforeEach(() => {
    authState.role = 'auditor'
    apiMocks.releaseReport.mockReset().mockResolvedValue({
      items: [{ id: 'synthetic-request', instrument_id: 'synthetic-fdr', requested_amount: '1000.00', eligibility_status: 'blocked', status: 'pending', reason: 'Synthetic audit fixture', created_at: '2026-10-25T00:00:00Z', updated_at: '2026-10-25T00:00:00Z' }],
      total: 1,
      limit: 50,
      offset: 0,
    })
    apiMocks.releaseRequest.mockReset().mockResolvedValue({
      id: 'synthetic-request', instrument_id: 'synthetic-fdr', requested_by_user_id: 'synthetic-user', requested_amount: '1000.00',
      eligibility_status: 'blocked', eligibility_findings: {}, status: 'pending', reason: 'Synthetic audit fixture',
      created_at: '2026-10-25T00:00:00Z', updated_at: '2026-10-25T00:00:00Z',
    })
    apiMocks.evaluateRelease.mockReset()
    apiMocks.decideRelease.mockReset()
  })

  it('shows an auditor the request but no evaluation or decision controls', async () => {
    render(<MemoryRouter initialEntries={['/releases?request=synthetic-request']}><ReleasePage /></MemoryRouter>)

    expect(await screen.findByText('Selected release request')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Re-evaluate eligibility' })).not.toBeInTheDocument()
    expect(screen.queryByText('Authorized decision')).not.toBeInTheDocument()
    expect(apiMocks.evaluateRelease).not.toHaveBeenCalled()
    expect(apiMocks.decideRelease).not.toHaveBeenCalled()
  })
})
