import type {
  Dashboard, Document, Institution, InstitutionDetail, Instrument, InstrumentHistory, IntegrityFinding,
  IntegrityQueueItem, Notification, Page, PendingVerification, ReleaseEligibility, ReleaseRequest,
  ReportInstrument, ReleaseReportRow, TokenResponse, UpcomingMaturity, User, QueueItem, CreateInstrumentRequest,
  ScrutinyRequest, ScrutinyResult, FinalDecisionRequest, SuccessorInstrumentRequest,
  ReleaseRequestCreated, ReleaseRequestCreateRequest, ReleaseDecisionResponse,
  FieldReviewRequest, FieldReviewResponse, Obligation,
  UpdateInstrumentRequest, AuditFeedItem,
} from '../types/api'

// Match the backend's documented Uvicorn bind address. On some local systems
// `localhost` resolves to IPv6 (::1), while Uvicorn is bound to IPv4 only.
const configuredBase = import.meta.env.VITE_API_BASE_URL?.trim() || 'http://127.0.0.1:8000'
export const apiBaseUrl = configuredBase.replace(/\/$/, '')
const apiPrefix = `${apiBaseUrl}/api/v1`

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: unknown) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  const token = sessionStorage.getItem('fdr-sentinel-token')
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  let response: Response
  try {
    response = await fetch(`${apiPrefix}${path}`, { ...init, headers })
  } catch {
    throw new ApiError(0, 'network_error', 'Cannot reach the FDR Sentinel API. Check that the backend is running.')
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { error?: { code?: string; message?: string; details?: unknown }; detail?: string }
    expireIfUnauthorized(response.status)
    throw new ApiError(response.status, body.error?.code || `http_${response.status}`, body.error?.message || body.detail || `Request failed (${response.status}).`, body.error?.details)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

function expireIfUnauthorized(status: number) {
  if (status === 401) {
    sessionStorage.removeItem('fdr-sentinel-token')
    window.dispatchEvent(new Event('fdr-auth-expired'))
  }
}

async function requestBlob(path: string, fallbackMessage: string): Promise<Blob> {
  const token = sessionStorage.getItem('fdr-sentinel-token')
  let response: Response
  try { response = await fetch(`${apiPrefix}${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} }) }
  catch { throw new ApiError(0, 'network_error', 'Cannot reach the FDR Sentinel API. Check that the backend is running.') }
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { error?: { code?: string; message?: string; details?: unknown }; detail?: string }
    expireIfUnauthorized(response.status)
    throw new ApiError(response.status, body.error?.code || `http_${response.status}`, body.error?.message || body.detail || fallbackMessage, body.error?.details)
  }
  return response.blob()
}

const query = (values: Record<string, string | number | boolean | undefined | null>) => {
  const params = new URLSearchParams()
  Object.entries(values).forEach(([key, value]) => { if (value !== undefined && value !== null && value !== '') params.set(key, String(value)) })
  const encoded = params.toString()
  return encoded ? `?${encoded}` : ''
}
const json = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) })

export const api = {
  login: (email: string, password: string) => request<TokenResponse>('/auth/login', json({ email, password })),
  me: () => request<User>('/auth/me'),
  logout: () => request<void>('/auth/logout', { method: 'POST' }),
  dashboard: (filters: Record<string, string | undefined> = {}) => request<Dashboard>(`/dashboard/summary${query(filters)}`),
  dashboardQueue: (filters: Record<string, string | number | undefined> = {}) => request<Page<QueueItem>>(`/dashboard/queue${query(filters)}`),
  pendingScrutiny: (filters: Record<string, string | number | undefined> = {}) => request<Page<Instrument>>(`/dashboard/pending-scrutiny${query(filters)}`),
  institutions: (filters: { search?: string; active?: boolean; limit?: number; offset?: number } = {}) => request<Page<Institution>>(`/institutions${query(filters as Record<string, string | number | boolean | undefined>)}`),
  institution: (id: string) => request<InstitutionDetail>(`/institutions/${id}`),
  obligations: (id: string, limit = 100) => request<Page<Obligation>>(`/institutions/${id}/obligations${query({ limit })}`),
  instruments: (filters: { institution_id?: string; search?: string; lifecycle_status?: string; verification_status?: string; maturity_before?: string; limit?: number; offset?: number } = {}) => request<Page<Instrument>>(`/fdrs${query(filters as Record<string, string | number | undefined>)}`),
  instrument: (id: string) => request<Instrument>(`/fdrs/${id}`),
  createInstrument: (body: CreateInstrumentRequest) => request<Instrument>('/fdrs', { ...json(body), method: 'POST' }),
  updateInstrument: (id: string, body: UpdateInstrumentRequest) => request<Instrument>(`/fdrs/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  history: (id: string) => request<InstrumentHistory>(`/fdrs/${id}/history`),
  auditEvents: (filters: { institution_id?: string; entity_type?: string; action?: string; date_from?: string; date_to?: string; limit?: number; offset?: number } = {}) => request<Page<AuditFeedItem>>(`/audit/events${query(filters as Record<string, string | number | undefined>)}`),
  submit: (id: string) => request<Instrument>(`/fdrs/${id}/submit`, { method: 'POST' }),
  scrutiny: (id: string, body: ScrutinyRequest) => request<ScrutinyResult>(`/fdrs/${id}/scrutiny`, json(body)),
  respondClarification: (id: string, eventId: string, response: string) => request<unknown>(`/fdrs/${id}/clarifications/${eventId}/respond`, json({ response })),
  decideInstrument: (id: string, decision: FinalDecisionRequest['decision'], rationale: string) => request<Instrument>(`/fdrs/${id}/decision`, json({ decision, rationale } satisfies FinalDecisionRequest)),
  successor: (id: string, body: SuccessorInstrumentRequest) => request<Instrument>(`/fdrs/${id}/successors`, { ...json(body), method: 'POST' }),
  documents: (id: string) => request<Document[]>(`/fdrs/${id}/documents`),
  uploadDocument: (id: string, file: File) => { const form = new FormData(); form.append('file', file); return request<Document>(`/fdrs/${id}/documents`, { method: 'POST', body: form }) },
  downloadDocument: (id: string) => requestBlob(`/documents/${id}/download`, 'The original document could not be retrieved.'),
  reviewField: (documentId: string, field: string, body: FieldReviewRequest) => request<FieldReviewResponse>(`/documents/${documentId}/fields/${encodeURIComponent(field)}/review`, json(body)),
  integrityQueue: (filters: { review_status?: string; limit?: number; offset?: number } = {}) => request<Page<IntegrityQueueItem>>(`/integrity/queue${query(filters as Record<string, string | number | undefined>)}`),
  integrityFindings: (filters: { review_status?: string; instrument_id?: string; limit?: number; offset?: number } = {}) => request<Page<IntegrityFinding>>(`/integrity/findings${query(filters as Record<string, string | number | undefined>)}`),
  reviewFinding: (id: string, decision: 'reviewed' | 'dismissed', resolution_notes: string) => request<IntegrityFinding>(`/integrity/findings/${id}/review`, json({ decision, resolution_notes })),
  scanIntegrity: () => request<unknown>('/integrity/scan', { method: 'POST' }),
  notifications: (unread_only = false) => request<Page<Notification>>(`/notifications${query({ unread_only, limit: 100 })}`),
  markNotificationRead: (id: string) => request<{ notification: Notification }>(`/notifications/${id}/read`, { method: 'POST' }),
  releaseReport: (filters: Record<string, string | undefined> = {}) => request<Page<ReleaseReportRow>>(`/reports/release-requests${query({ ...filters, limit: 100 })}`),
  releaseRequest: (id: string) => request<ReleaseRequest>(`/release-requests/${id}`),
  createReleaseRequest: (id: string, requested_amount: string, reason: string) => request<ReleaseRequestCreated>(`/fdrs/${id}/release-requests`, json({ requested_amount, reason } satisfies ReleaseRequestCreateRequest)),
  evaluateRelease: (id: string) => request<{ request: ReleaseRequest; eligibility: ReleaseEligibility }>(`/release-requests/${id}/evaluate`, { method: 'POST' }),
  decideRelease: (id: string, decision: 'approved' | 'rejected' | 'returned', rationale: string, disposition: string) => request<ReleaseDecisionResponse>(`/release-requests/${id}/decision`, json({ decision, rationale, disposition })),
  reportInstruments: (filters: Record<string, string | undefined> = {}) => request<Page<ReportInstrument>>(`/reports/instruments${query({ ...filters, limit: 100 })}`),
  reportMaturities: (filters: Record<string, string | undefined> = {}) => request<Page<UpcomingMaturity>>(`/reports/upcoming-maturities${query({ ...filters, limit: 100 })}`),
  reportVerification: (filters: Record<string, string | undefined> = {}) => request<Page<PendingVerification>>(`/reports/pending-verification${query({ ...filters, limit: 100 })}`),
  downloadReport: async (report: 'instruments' | 'upcoming-maturities' | 'pending-verification' | 'release-requests', filters: Record<string, string | undefined> = {}) => {
    return requestBlob(`/reports/${report}.csv${query(filters)}`, 'The CSV report could not be generated.')
  },
}
