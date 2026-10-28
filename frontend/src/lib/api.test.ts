import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'

describe('typed backend client', () => {
  beforeEach(() => { sessionStorage.clear(); vi.restoreAllMocks() })

  it('uses the documented API path and bearer token for dashboard reads', async () => {
    sessionStorage.setItem('fdr-sentinel-token', 'test-token')
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ total_active_instruments: 4 }) })
    vi.stubGlobal('fetch', fetchMock)
    await api.dashboard()
    expect(fetchMock).toHaveBeenCalledWith(expect.stringMatching(/\/api\/v1\/dashboard\/summary$/), expect.objectContaining({ headers: expect.any(Headers) }))
    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer test-token')
  })

  it('normalizes API failures and invalidates expired local sessions', async () => {
    sessionStorage.setItem('fdr-sentinel-token', 'expired')
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 401, json: async () => ({ detail: 'Authentication is required.' }) })
    vi.stubGlobal('fetch', fetchMock)
    const expired = vi.fn()
    window.addEventListener('fdr-auth-expired', expired)
    await expect(api.me()).rejects.toMatchObject({ status: 401, code: 'http_401', message: 'Authentication is required.' })
    expect(sessionStorage.getItem('fdr-sentinel-token')).toBeNull()
    expect(expired).toHaveBeenCalledOnce()
    window.removeEventListener('fdr-auth-expired', expired)
  })
})
