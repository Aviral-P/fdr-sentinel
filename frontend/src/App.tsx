import { Link, Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useAuth } from './auth/AuthProvider'
import { AppShell } from './components/AppShell'
import { LoadingState } from './components/ui'
import { DashboardPage } from './pages/DashboardPage'
import { InstitutionDetailPage, InstitutionsPage } from './pages/InstitutionsPage'
import { InstrumentDetailPage } from './pages/FdrPages'
import { FdrRegisterPage } from './pages/FdrRegisterPage'
import { LoginPage } from './pages/LoginPage'
import { ActionQueuePage, NotificationsPage, PendingScrutinyPage, ReportsPage, ScrutinyQueuePage } from './pages/OperationsPages'
import { ReleasePage } from './pages/ReleasePage'
import { AuditHistoryPage } from './pages/AuditHistoryPage'
import { DocumentWorkspacePage } from './pages/DocumentWorkspacePage'
import type { Role } from './types/api'

function Protected() {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <LoadingState label="Restoring your authenticated session…" />
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return <Outlet />
}

function RoleGate({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { user } = useAuth()
  if (!user || !roles.includes(user.role)) return <div role="alert" className="rounded-xl border border-amber-100 bg-amber-50 p-6"><h1 className="text-sm font-semibold text-amber-800">This workspace is not available for your role.</h1><p className="mt-1 text-xs leading-5 text-amber-800">Access is restricted in the interface and is enforced independently by the backend API.</p><Link to="/" className="mt-3 inline-block text-xs font-semibold text-teal-700">Return to overview</Link></div>
  return children
}

function NotFound() { return <div className="rounded-xl border border-line bg-white p-10 text-center"><h1 className="text-lg font-semibold">Page not found</h1><p className="mt-2 text-sm text-slate-500">This route is not part of the local FDR Sentinel frontend.</p><a className="mt-4 inline-block text-sm font-semibold text-teal-700" href="/">Return to overview</a></div> }

export function App() {
  const { user } = useAuth()
  return <Routes>
    <Route path="/login" element={user ? <Navigate to="/" replace /> : <LoginPage />} />
    <Route element={<Protected />}>
      <Route element={<AppShell />}>
        <Route index element={<DashboardPage />} />
        <Route path="institutions" element={<InstitutionsPage />} />
        <Route path="institutions/:id" element={<InstitutionDetailPage />} />
        <Route path="fdrs" element={<FdrRegisterPage />} />
        <Route path="fdrs/:id" element={<InstrumentDetailPage />} />
        <Route path="scrutiny" element={<RoleGate roles={['scrutiny_officer', 'auditor', 'admin']}><ScrutinyQueuePage /></RoleGate>} />
        <Route path="pending-scrutiny" element={<PendingScrutinyPage />} />
        <Route path="scrutiny/:id" element={<RoleGate roles={['scrutiny_officer', 'auditor', 'admin']}><DocumentWorkspacePage /></RoleGate>} />
        <Route path="action-queue" element={<ActionQueuePage />} />
        <Route path="releases" element={<RoleGate roles={['institution_user', 'scrutiny_officer', 'approving_authority', 'auditor', 'admin']}><ReleasePage /></RoleGate>} />
        <Route path="notifications" element={<NotificationsPage />} />
        <Route path="reports" element={<ReportsPage />} />
        <Route path="audit" element={<AuditHistoryPage />} />
        <Route path="fdrs/:id/review" element={<DocumentWorkspacePage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Route>
  </Routes>
}
