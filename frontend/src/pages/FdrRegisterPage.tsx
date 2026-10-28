import { useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowDown, ArrowUp, ArrowUpDown, ArrowUpRight, CirclePlus, Search, X } from 'lucide-react'
import { useAuth } from '../auth/AuthProvider'
import { useRemote } from '../hooks/useRemote'
import { api, ApiError } from '../lib/api'
import type { Instrument, LifecycleStatus, VerificationStatus } from '../types/api'
import { formatDate, formatMoney, titleCase } from '../lib/utils'
import { Button, Card, DataTable, EmptyState, ErrorState, FormField, Input, LifecycleStatusBadge, LoadingState, PageHeader, PriorityBadge, Select, VerificationStatusBadge } from '../components/ui'

type SortKey = 'reference' | 'institution' | 'issuer' | 'amount' | 'issue_date' | 'maturity_date' | 'lifecycle_status' | 'verification_status' | 'priority'
const lifecycleOptions: LifecycleStatus[] = ['draft', 'submitted', 'under_scrutiny', 'clarification_required', 'approved', 'rejected', 'release_pending', 'released', 'matured', 'superseded']
const verificationOptions: VerificationStatus[] = ['not_checked', 'pending_review', 'discrepancy_flagged', 'reviewed']
const pageSize = 25

function SortHeading({ label, column, active, direction, onSort, align = 'left' }: { label: string; column: SortKey; active: boolean; direction: 'asc' | 'desc'; onSort: (key: SortKey) => void; align?: 'left' | 'right' }) {
  const Icon = active ? direction === 'asc' ? ArrowUp : ArrowDown : ArrowUpDown
  return <th scope="col" aria-sort={active ? direction === 'asc' ? 'ascending' : 'descending' : 'none'} className={`whitespace-nowrap px-3 py-2.5 text-[10px] font-semibold uppercase tracking-[.06em] text-slate-600 ${align === 'right' ? 'text-right' : 'text-left'}`}><button type="button" className="inline-flex items-center gap-1.5 rounded-sm hover:text-teal-800 focus-visible:ring-2 focus-visible:ring-teal-700" onClick={() => onSort(column)}>{label}<Icon className="h-3 w-3 text-slate-400" aria-hidden="true" /></button></th>
}

export function FdrRegisterPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [searchDraft, setSearchDraft] = useState(searchParams.get('search') || '')
  const [search, setSearch] = useState(searchParams.get('search') || '')
  const [institutionFilter, setInstitutionFilter] = useState(searchParams.get('institution_id') || '')
  const [status, setStatus] = useState(searchParams.get('lifecycle_status') || '')
  const [verification, setVerification] = useState(searchParams.get('verification_status') || '')
  const [maturityBefore, setMaturityBefore] = useState(searchParams.get('maturity_before') || '')
  const [offset, setOffset] = useState(0)
  const [sortKey, setSortKey] = useState<SortKey | null>(null)
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc')
  const [createOpen, setCreateOpen] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({ issuer_name: '', beneficiary: '', reference_original: '', amount: '', issue_date: new Date().toISOString().slice(0, 10), maturity_date: '', notes: '' })
  const institutionId = user?.role === 'institution_user' ? user.institution_id || undefined : institutionFilter || undefined
  const params = useMemo(() => ({ search: search || undefined, lifecycle_status: status || undefined, verification_status: verification || undefined, maturity_before: maturityBefore || undefined, limit: pageSize, offset, institution_id: institutionId }), [search, status, verification, maturityBefore, offset, institutionId])
  const records = useRemote(() => api.instruments(params), [JSON.stringify(params)])
  const institutions = useRemote(() => api.institutions({ limit: 100 }), [])
  const institutionNames = new Map((institutions.data?.items || []).map(row => [row.id, row]))
  const rows = records.data?.items || []
  const sortedRows = useMemo(() => {
    if (!sortKey) return rows
    const value = (row: Instrument): string | number => {
      switch (sortKey) {
        case 'reference': return row.reference_original.toLocaleLowerCase()
        case 'institution': return (institutionNames.get(row.institution_id)?.name || row.institution_id).toLocaleLowerCase()
        case 'issuer': return row.issuer_name.toLocaleLowerCase()
        case 'amount': return Number(row.amount)
        case 'issue_date': return row.issue_date
        case 'maturity_date': return row.maturity_date
        case 'lifecycle_status': return row.lifecycle_status
        case 'verification_status': return row.verification_status
        case 'priority': return row.priority
      }
    }
    return [...rows].sort((a, b) => {
      const left = value(a); const right = value(b)
      const compared = typeof left === 'number' && typeof right === 'number' ? left - right : String(left).localeCompare(String(right))
      return (sortDirection === 'asc' ? compared : -compared) || a.reference_original.localeCompare(b.reference_original)
    })
  }, [rows, sortKey, sortDirection, institutionNames])

  function sortBy(key: SortKey) {
    if (sortKey === key) setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDirection('asc') }
  }
  function applyFilters() {
    setOffset(0)
    setSearch(searchDraft.trim())
    setSearchParams({ ...(searchDraft.trim() ? { search: searchDraft.trim() } : {}), ...(institutionFilter ? { institution_id: institutionFilter } : {}), ...(status ? { lifecycle_status: status } : {}), ...(verification ? { verification_status: verification } : {}), ...(maturityBefore ? { maturity_before: maturityBefore } : {}) }, { replace: true })
  }
  function clearFilters() {
    setSearchDraft(''); setSearch(''); setInstitutionFilter(''); setStatus(''); setVerification(''); setMaturityBefore(''); setOffset(0); setSearchParams({}, { replace: true })
  }
  async function create(event: FormEvent) {
    event.preventDefault(); setSaving(true); setFormError(null)
    try {
      const created = await api.createInstrument({ ...form, institution_id: user?.institution_id || '', amount: form.amount })
      navigate(`/fdrs/${created.id}`)
    } catch (error) { setFormError(error instanceof ApiError ? error.message : 'Instrument could not be created.') }
    finally { setSaving(false) }
  }

  const sortProps = { direction: sortDirection, onSort: sortBy }
  return <>
    <PageHeader eyebrow="Registry · Financial instruments" title="FDR Register" description="Institution-submitted fixed deposit records and their current review state." action={user?.role === 'institution_user' ? <Button onClick={() => setCreateOpen(!createOpen)}><CirclePlus className="h-4 w-4" /> New instrument</Button> : undefined} />

    {createOpen && <Card className="mb-4 p-4"><div className="mb-3 flex items-start justify-between"><div><h2 className="text-sm font-semibold text-ink-900">New instrument draft</h2><p className="mt-1 text-[11px] text-slate-600">The draft is saved to your institution and can be submitted for scrutiny from its record page.</p></div><Button variant="ghost" size="icon" aria-label="Close new instrument form" onClick={() => setCreateOpen(false)}><X className="h-4 w-4" /></Button></div><form onSubmit={create} className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><FormField label="FDR reference"><Input required value={form.reference_original} onChange={event => setForm({ ...form, reference_original: event.target.value })} /></FormField><FormField label="Issuing bank"><Input required minLength={2} value={form.issuer_name} onChange={event => setForm({ ...form, issuer_name: event.target.value })} /></FormField><FormField label="Amount (INR)"><Input required type="number" min="0.01" step="0.01" value={form.amount} onChange={event => setForm({ ...form, amount: event.target.value })} /></FormField><FormField label="Beneficiary"><Input value={form.beneficiary} onChange={event => setForm({ ...form, beneficiary: event.target.value })} /></FormField><FormField label="Issue date"><Input required type="date" value={form.issue_date} onChange={event => setForm({ ...form, issue_date: event.target.value })} /></FormField><FormField label="Maturity date"><Input required type="date" value={form.maturity_date} onChange={event => setForm({ ...form, maturity_date: event.target.value })} /></FormField><FormField label="Institution notes"><Input value={form.notes} onChange={event => setForm({ ...form, notes: event.target.value })} /></FormField><div className="flex items-end"><Button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save draft'}</Button></div>{formError && <div className="sm:col-span-2 xl:col-span-4"><ErrorState message={formError} /></div>}</form></Card>}

    <Card className="mb-4 p-3"><div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-[minmax(220px,1.4fr)_minmax(180px,1fr)_minmax(150px,.9fr)_minmax(150px,.9fr)_minmax(145px,.8fr)_auto]"><label className="relative"><span className="sr-only">Search reference or issuing bank</span><Search className="absolute left-2.5 top-2.5 h-4 w-4 text-slate-400" aria-hidden="true" /><Input aria-label="Search reference or issuing bank" className="pl-8" placeholder="Reference or issuing bank" value={searchDraft} onChange={event => setSearchDraft(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') applyFilters() }} /></label>
      {user?.role !== 'institution_user' && <Select aria-label="Filter institution" value={institutionFilter} onChange={event => setInstitutionFilter(event.target.value)}><option value="">All institutions</option>{(institutions.data?.items || []).map(item => <option key={item.id} value={item.id}>{item.code} · {item.name}</option>)}</Select>}
      <Select aria-label="Filter lifecycle status" value={status} onChange={event => setStatus(event.target.value)}><option value="">All lifecycle statuses</option>{lifecycleOptions.map(item => <option key={item} value={item}>{titleCase(item)}</option>)}</Select>
      <Select aria-label="Filter verification status" value={verification} onChange={event => setVerification(event.target.value)}><option value="">All verification states</option>{verificationOptions.map(item => <option key={item} value={item}>{titleCase(item)}</option>)}</Select>
      <label><span className="sr-only">Matures on or before</span><Input aria-label="Matures on or before" type="date" title="Matures on or before" value={maturityBefore} onChange={event => setMaturityBefore(event.target.value)} /></label>
      <Button variant="secondary" onClick={applyFilters}><Search className="h-3.5 w-3.5" /> Apply</Button></div>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 border-t border-line pt-2 text-[10px] text-slate-500"><span>API search covers reference and issuing bank. The API has no priority filter or server-side sort; column sorting applies to this page only.</span><button type="button" className="font-semibold text-teal-800 underline underline-offset-2 hover:text-teal-900" onClick={clearFilters}>Clear filters</button></div>
    </Card>

    {records.loading ? <Card><LoadingState label="Loading the FDR register…" /></Card> : records.error ? <ErrorState message={records.error} onRetry={() => void records.refresh()} /> : <Card className="overflow-hidden">
      <div className="flex items-center justify-between border-b border-line px-4 py-2.5"><div><h2 className="text-[13px] font-semibold text-ink-900">Registered instruments</h2><p className="mt-0.5 text-[10px] text-slate-500">Updated most recently first by the API; select a heading to sort this page.</p></div><span className="font-mono text-[10px] text-slate-500">{records.data?.total ?? 0} records</span></div>
      {sortedRows.length ? <><DataTable caption="FDR register results" minWidth="1120px"><thead className="border-b border-line bg-slate-50"><tr>
        <SortHeading label="Instrument reference" column="reference" active={sortKey === 'reference'} {...sortProps} />
        <SortHeading label="Institution" column="institution" active={sortKey === 'institution'} {...sortProps} />
        <SortHeading label="Issuing bank" column="issuer" active={sortKey === 'issuer'} {...sortProps} />
        <SortHeading label="Amount" column="amount" align="right" active={sortKey === 'amount'} {...sortProps} />
        <SortHeading label="Issue date" column="issue_date" active={sortKey === 'issue_date'} {...sortProps} />
        <SortHeading label="Maturity date" column="maturity_date" active={sortKey === 'maturity_date'} {...sortProps} />
        <SortHeading label="Lifecycle" column="lifecycle_status" active={sortKey === 'lifecycle_status'} {...sortProps} />
        <SortHeading label="Verification" column="verification_status" active={sortKey === 'verification_status'} {...sortProps} />
        <SortHeading label="Priority" column="priority" active={sortKey === 'priority'} {...sortProps} />
        <th scope="col" className="px-3 py-2.5 text-right text-[10px] font-semibold uppercase tracking-[.06em] text-slate-600">Record</th>
      </tr></thead><tbody className="divide-y divide-line">{sortedRows.map(row => {
        const institution = institutionNames.get(row.institution_id)
        return <tr key={row.id} className="hover:bg-slate-50/80 focus-within:bg-slate-50/80">
          <td className="whitespace-nowrap px-3 py-2.5"><Link to={`/fdrs/${row.id}`} className="font-mono text-[11px] font-semibold text-teal-800 underline-offset-2 hover:underline">{row.reference_original}</Link><div className="mt-0.5 font-mono text-[9px] text-slate-400">{row.id.slice(0, 8)}</div></td>
          <td className="max-w-[200px] px-3 py-2.5">{institution ? <Link to={`/institutions/${institution.id}`} className="block truncate text-[11px] font-medium text-ink-800 hover:text-teal-800 hover:underline">{institution.name}</Link> : <span className="text-[11px] text-slate-500">Institution name unavailable</span>}<div className="mt-0.5 text-[9px] text-slate-400">{institution?.code || row.institution_id.slice(0, 8)}</div></td>
          <td className="max-w-[180px] truncate px-3 py-2.5 text-[11px] text-ink-800" title={row.issuer_name}>{row.issuer_name}</td>
          <td className="whitespace-nowrap px-3 py-2.5 text-right font-mono text-[11px] font-medium tabular-nums text-ink-900">{formatMoney(row.amount)}</td>
          <td className="whitespace-nowrap px-3 py-2.5 text-[11px] tabular-nums text-slate-700">{formatDate(row.issue_date)}</td>
          <td className="whitespace-nowrap px-3 py-2.5 text-[11px] tabular-nums text-slate-700">{formatDate(row.maturity_date)}</td>
          <td className="px-3 py-2.5"><LifecycleStatusBadge status={row.lifecycle_status} /></td>
          <td className="px-3 py-2.5"><VerificationStatusBadge status={row.verification_status} /></td>
          <td className="px-3 py-2.5"><PriorityBadge status={row.priority} /></td>
          <td className="whitespace-nowrap px-3 py-2.5 text-right"><Link to={`/fdrs/${row.id}`} aria-label={`Open instrument ${row.reference_original}`} className="inline-flex items-center gap-1 rounded-sm px-2 py-1 text-[10px] font-semibold text-teal-800 hover:bg-teal-50 focus-visible:ring-2 focus-visible:ring-teal-700">Open <ArrowUpRight className="h-3 w-3" aria-hidden="true" /></Link></td>
        </tr>
      })}</tbody></DataTable><div className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-4 py-2.5"><p className="text-[10px] text-slate-600">Showing {offset + 1}–{offset + rows.length} of {records.data?.total ?? 0}</p><div className="flex items-center gap-2"><Button size="sm" variant="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - pageSize))}>Previous</Button><span className="min-w-16 text-center font-mono text-[10px] text-slate-500">Page {Math.floor(offset / pageSize) + 1}</span><Button size="sm" variant="secondary" disabled={offset + pageSize >= (records.data?.total || 0)} onClick={() => setOffset(offset + pageSize)}>Next</Button></div></div></> : <EmptyState title="No FDR records found" description="No instruments match these filters. Clear the filters or create a draft using an institution account." />}
    </Card>}
  </>
}
