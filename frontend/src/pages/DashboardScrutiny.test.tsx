import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const { apiMocks, authState } = vi.hoisted(() => ({
  apiMocks: { dashboard: vi.fn(), dashboardQueue: vi.fn(), pendingScrutiny: vi.fn(), integrityQueue: vi.fn() },
  authState: { user: { full_name: 'Synthetic Officer', role: 'scrutiny_officer', institution_id: null } },
}))
vi.mock('../auth/AuthProvider', () => ({ useAuth: () => authState }))
vi.mock('../lib/api', () => ({ api: apiMocks, ApiError: class ApiError extends Error {} }))

import { DashboardPage } from './DashboardPage'
import { PendingScrutinyPage } from './OperationsPages'

describe('pending scrutiny navigation and worklist', () => {
  afterEach(() => cleanup())

  beforeEach(() => {
    apiMocks.dashboard.mockReset().mockResolvedValue({ as_of: '2026-10-25', maturity_reminder_windows_days: [30, 15, 7], total_active_instruments: 0, approaching_maturity: 0, matured_requiring_action: 0, pending_scrutiny: 1, open_discrepancy_findings: 0, renewals_replacements_pending_review: 0, release_requests_pending_authorized_decision: 0, overdue_actions: 0, unresolved_cases: 0 })
    apiMocks.dashboardQueue.mockReset().mockResolvedValue({ items: [], total: 0, limit: 7, offset: 0 })
    apiMocks.pendingScrutiny.mockReset().mockResolvedValue({ items: [{ id: 'submitted-case', institution_id: 'synthetic-institution', reference_original: 'SYN-PENDING-1', issuer_name: 'Synthetic Issuer', amount: '100.00', maturity_date: '2027-01-01', lifecycle_status: 'submitted', priority: 'normal' }], total: 1, limit: 25, offset: 0 })
    apiMocks.integrityQueue.mockReset()
  })

  it('routes the pending-scrutiny metric to the submitted-case worklist', async () => {
    render(<MemoryRouter><DashboardPage /></MemoryRouter>)
    expect(await screen.findByRole('link', { name: /pending scrutiny/i })).toHaveAttribute('href', '/pending-scrutiny')
  })

  it('loads submitted instruments through the separate case endpoint, not the findings queue', async () => {
    render(<MemoryRouter><PendingScrutinyPage /></MemoryRouter>)
    expect(await screen.findByText('SYN-PENDING-1')).toBeInTheDocument()
    expect(apiMocks.pendingScrutiny).toHaveBeenCalled()
    expect(apiMocks.integrityQueue).not.toHaveBeenCalled()
  })

  it('passes worklist filters to the backend and keeps the list paginated', async () => {
    render(<MemoryRouter><PendingScrutinyPage /></MemoryRouter>)
    const institution = await screen.findByRole('textbox', { name: /filter by institution id/i })
    fireEvent.change(institution, { target: { value: 'institution-synthetic-2' } })
    await waitFor(() => expect(apiMocks.pendingScrutiny).toHaveBeenLastCalledWith(expect.objectContaining({ institution_id: 'institution-synthetic-2', limit: 25, offset: 0 })))
    expect(screen.getByRole('button', { name: /next/i })).toBeDisabled()
  })

  it('routes open findings to the integrity findings workspace', async () => {
    render(<MemoryRouter><DashboardPage /></MemoryRouter>)
    expect(await screen.findByRole('link', { name: /open findings/i })).toHaveAttribute('href', '/scrutiny?review_status=open')
  })
})
