import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Landmark, LockKeyhole, ShieldCheck } from 'lucide-react'
import { useAuth } from '../auth/AuthProvider'
import { ApiError } from '../lib/api'
import { Button, Input } from '../components/ui'

export function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(null)
    try { await login(email, password); navigate('/', { replace: true }) }
    catch (e) { setError(e instanceof ApiError ? e.message : 'Sign in could not be completed.') }
    finally { setBusy(false) }
  }
  return <div className="grid min-h-screen bg-white lg:grid-cols-[1.05fr_.95fr]">
    <section className="relative hidden overflow-hidden bg-ink-950 px-12 py-12 text-white lg:flex lg:flex-col lg:justify-between xl:px-20">
      <div className="absolute -right-44 -top-32 h-[570px] w-[570px] rounded-full border border-white/10" /><div className="absolute -right-20 -top-8 h-[330px] w-[330px] rounded-full border border-white/10" /><div className="absolute bottom-0 left-0 h-1/2 w-full bg-gradient-to-t from-teal-900/30 to-transparent" />
      <div className="relative flex items-center gap-3"><div className="flex h-10 w-10 items-center justify-center rounded-xl bg-teal-600"><Landmark className="h-5 w-5" /></div><div><div className="text-sm font-bold">FDR Sentinel</div><div className="text-[9px] uppercase tracking-[.18em] text-teal-200">AICTE oversight portal</div></div></div>
      <div className="relative max-w-xl"><div className="mb-5 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[.16em] text-teal-200"><ShieldCheck className="h-3.5 w-3.5" /> Secure institution workspace</div><h1 className="text-4xl font-semibold leading-tight tracking-tight xl:text-[48px]">Every deposit.<br /><span className="text-teal-300">Accounted for.</span></h1><p className="mt-5 max-w-md text-sm leading-7 text-slate-300">A single review workspace for institution submissions, scrutiny decisions, maturity obligations and release approvals.</p><div className="mt-9 grid max-w-md grid-cols-3 gap-5 border-t border-white/10 pt-6"><div><div className="text-lg font-semibold">01</div><div className="mt-1 text-[10px] text-slate-400">Submit & track</div></div><div><div className="text-lg font-semibold">02</div><div className="mt-1 text-[10px] text-slate-400">Review evidence</div></div><div><div className="text-lg font-semibold">03</div><div className="mt-1 text-[10px] text-slate-400">Decide & record</div></div></div></div>
      <div className="relative text-[10px] text-slate-500">Local development prototype · Synthetic demo data only</div>
    </section>
    <section className="flex items-center justify-center px-5 py-12 sm:px-10"><div className="w-full max-w-[390px]"><div className="mb-10 flex items-center gap-3 lg:hidden"><div className="flex h-9 w-9 items-center justify-center rounded-lg bg-ink-900 text-white"><Landmark className="h-4 w-4" /></div><div><div className="text-sm font-bold">FDR Sentinel</div><div className="text-[9px] uppercase tracking-widest text-teal-700">AICTE portal</div></div></div><div className="mb-8"><p className="text-xs font-semibold uppercase tracking-[.15em] text-teal-700">Welcome back</p><h2 className="mt-2 text-[28px] font-semibold tracking-tight text-ink-950">Sign in to your workspace</h2><p className="mt-2 text-sm text-slate-500">Use your local demo account to continue.</p></div>
      <form onSubmit={submit} className="space-y-5"><label className="block"><span className="mb-2 block text-xs font-semibold text-ink-700">Email address</span><Input type="email" autoComplete="username" required value={email} onChange={e => setEmail(e.target.value)} placeholder="name@institution.edu.in" /></label><label className="block"><span className="mb-2 block text-xs font-semibold text-ink-700">Password</span><Input type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} placeholder="Enter your password" /></label>{error && <div role="alert" className="rounded-lg border border-rose-100 bg-rose-50 px-3 py-2.5 text-xs text-rose-700">{error}</div>}<Button className="w-full" type="submit" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}{!busy && <ArrowRight className="h-4 w-4" />}</Button></form>
      <div className="mt-6 flex gap-2 rounded-lg bg-slate-50 p-3 text-[11px] leading-5 text-slate-500"><LockKeyhole className="mt-0.5 h-3.5 w-3.5 shrink-0 text-teal-700" />Demo accounts are created by the backend’s development seed script. No credentials are stored in this frontend.</div><div className="mt-8 text-center text-[10px] text-slate-400">AICTE Security Deposit / FDR Management and Intelligence Portal</div></div></section>
  </div>
}
