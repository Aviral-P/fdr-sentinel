import { useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { Bell, Building2, FileChartColumn, FileStack, Gauge, History, Landmark, ListChecks, LogOut, Menu, ShieldCheck, X } from 'lucide-react'
import { useAuth } from '../auth/AuthProvider'
import { useRemote } from '../hooks/useRemote'
import { api } from '../lib/api'
import { cn, titleCase } from '../lib/utils'
import type { Role } from '../types/api'

type NavItem = { to: string; label: string; icon: typeof Gauge; section: string; roles?: Role[] }
const navItems: NavItem[] = [
  { to: '/', label: 'Overview', icon: Gauge, section: 'Workspace' },
  { to: '/institutions', label: 'Institutions', icon: Building2, section: 'Registry' },
  { to: '/fdrs', label: 'FDR register', icon: FileStack, section: 'Registry' },
  { to: '/action-queue', label: 'Action queue', icon: ListChecks, section: 'Operations' },
  { to: '/pending-scrutiny', label: 'Submitted cases', icon: ListChecks, section: 'Operations' },
  { to: '/scrutiny', label: 'Integrity findings', icon: ShieldCheck, section: 'Operations', roles: ['scrutiny_officer', 'auditor', 'admin'] },
  { to: '/releases', label: 'Release requests', icon: ShieldCheck, section: 'Operations' },
  { to: '/audit', label: 'Audit history', icon: History, section: 'Governance' },
  { to: '/notifications', label: 'Notifications', icon: Bell, section: 'Governance' },
  { to: '/reports', label: 'Reports', icon: FileChartColumn, section: 'Governance' },
]

export function AppShell() {
  const { user, logout } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)
  const unread = useRemote(() => api.notifications(true), [])
  const location = useLocation()
  const visibleLinks = navItems.filter(item => !item.roles || (user && item.roles.includes(user.role)))
  const sections = [...new Set(visibleLinks.map(item => item.section))]
  const pageLabel = visibleLinks.find(item => item.to === location.pathname)?.label || location.pathname.split('/').filter(Boolean).at(-1)?.replaceAll('-', ' ') || 'Overview'

  return <div className="min-h-screen bg-canvas text-ink-900">
    {menuOpen && <button aria-label="Close navigation overlay" className="fixed inset-0 z-30 bg-slate-950/45 lg:hidden" onClick={() => setMenuOpen(false)} />}
    <aside id="primary-navigation" className={cn('fixed inset-y-0 left-0 z-40 flex w-[238px] flex-col border-r border-slate-700/70 bg-ink-900 text-white transition-transform lg:translate-x-0', menuOpen ? 'translate-x-0' : '-translate-x-full')}>
      <div className="flex h-[58px] items-center gap-3 border-b border-slate-700/80 px-4">
        <div className="flex h-8 w-8 items-center justify-center bg-teal-700 text-white"><Landmark className="h-4 w-4" aria-hidden="true" /></div>
        <div className="leading-tight"><div className="text-[13px] font-semibold tracking-wide">FDR Sentinel</div><div className="mt-0.5 text-[9px] font-medium uppercase tracking-[.12em] text-slate-400">AICTE · Financial compliance</div></div>
        <button className="ml-auto rounded-sm p-1 text-slate-400 hover:bg-slate-700 hover:text-white focus-visible:outline-white lg:hidden" onClick={() => setMenuOpen(false)} aria-label="Close navigation"><X className="h-4 w-4" /></button>
      </div>
      <div className="border-b border-slate-700/80 px-4 py-3"><div className="flex items-center gap-2 text-[10px] font-medium text-slate-300"><span className="h-1.5 w-1.5 rounded-full bg-teal-400" /> Local prototype</div></div>
      <nav aria-label="Primary" className="flex-1 overflow-y-auto px-2.5 py-4">
        {sections.map(section => <div key={section} className="mb-5 last:mb-0"><h2 className="px-2 pb-1.5 text-[9px] font-bold uppercase tracking-[.14em] text-slate-500">{section}</h2><div className="space-y-0.5">{visibleLinks.filter(item => item.section === section).map(({ to, label, icon: Icon }) => <NavLink key={to} to={to} end={to === '/'} onClick={() => setMenuOpen(false)} className={({ isActive }) => cn('group flex min-h-9 items-center gap-2.5 border-l-2 px-2.5 text-[12px] font-medium transition-colors focus-visible:outline-white', isActive ? 'border-teal-400 bg-white/10 text-white' : 'border-transparent text-slate-300 hover:bg-white/5 hover:text-white')}><Icon className="h-4 w-4 shrink-0 text-slate-400 group-hover:text-slate-200" aria-hidden="true" /><span className="flex-1">{label}</span>{label === 'Notifications' && (unread.data?.total ?? 0) > 0 && <span className="min-w-5 bg-teal-700 px-1.5 py-0.5 text-center text-[9px] font-bold text-white">{unread.data?.total}</span>}</NavLink>)}</div></div>)}
      </nav>
      <div className="border-t border-slate-700/80 p-3"><div className="flex items-center gap-2.5 px-1 py-1.5"><div className="flex h-7 w-7 shrink-0 items-center justify-center bg-slate-700 text-[10px] font-semibold text-slate-100">{user?.full_name.split(' ').map(part => part[0]).slice(0, 2).join('')}</div><div className="min-w-0 flex-1"><div className="truncate text-[11px] font-semibold text-slate-100">{user?.full_name}</div><div className="mt-0.5 truncate text-[9px] text-slate-400">{user && titleCase(user.role)}</div></div><button title="Sign out" aria-label="Sign out" onClick={() => { void logout().catch(() => undefined) }} className="rounded-sm p-2 text-slate-400 hover:bg-slate-700 hover:text-white focus-visible:outline-white"><LogOut className="h-4 w-4" /></button></div></div>
    </aside>
    <div className="min-h-screen lg:pl-[238px]">
      <header className="sticky top-0 z-20 flex h-[54px] items-center justify-between border-b border-line bg-white px-4 sm:px-6">
        <div className="flex min-w-0 items-center gap-2"><button aria-label="Open navigation" aria-controls="primary-navigation" aria-expanded={menuOpen} className="rounded-sm p-2 text-slate-600 hover:bg-slate-100 focus-visible:ring-2 focus-visible:ring-teal-700 lg:hidden" onClick={() => setMenuOpen(true)}><Menu className="h-4 w-4" /></button><div className="hidden items-center gap-2 text-[11px] text-slate-400 sm:flex"><span>FDR Sentinel</span><span aria-hidden="true">/</span><span className="truncate font-semibold text-ink-800">{titleCase(pageLabel)}</span></div><div className="text-[12px] font-semibold text-ink-800 sm:hidden">{titleCase(pageLabel)}</div></div>
        <Link to="/notifications" aria-label={`Open notifications${(unread.data?.total ?? 0) ? `, ${unread.data?.total} unread` : ''}`} className="relative rounded-sm p-2 text-slate-600 hover:bg-slate-100 focus-visible:ring-2 focus-visible:ring-teal-700"><Bell className="h-4 w-4" aria-hidden="true" />{(unread.data?.total ?? 0) > 0 && <span className="absolute right-1 top-1 h-2 w-2 border border-white bg-rose-700" />}</Link>
      </header>
      <main className="mx-auto min-h-[calc(100vh-82px)] max-w-[1600px] px-4 py-5 sm:px-6 lg:px-7"><Outlet /></main>
      <footer className="border-t border-line bg-white px-4 py-2.5 text-[9px] text-slate-500 sm:px-6 lg:px-7">FDR Sentinel · Local-development prototype · No external bank verification connected</footer>
    </div>
  </div>
}
