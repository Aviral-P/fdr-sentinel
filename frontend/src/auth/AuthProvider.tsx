import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api } from '../lib/api'
import type { User } from '../types/api'

interface AuthValue { user: User | null; loading: boolean; login: (email: string, password: string) => Promise<void>; logout: () => Promise<void> }
const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(Boolean(sessionStorage.getItem('fdr-sentinel-token')))
  const logoutLocal = useCallback(() => { sessionStorage.removeItem('fdr-sentinel-token'); setUser(null); setLoading(false) }, [])
  useEffect(() => {
    const expired = () => logoutLocal()
    window.addEventListener('fdr-auth-expired', expired)
    const token = sessionStorage.getItem('fdr-sentinel-token')
    if (token) void api.me().then(setUser).catch(logoutLocal).finally(() => setLoading(false))
    return () => window.removeEventListener('fdr-auth-expired', expired)
  }, [logoutLocal])
  const login = useCallback(async (email: string, password: string) => {
    const token = await api.login(email, password)
    sessionStorage.setItem('fdr-sentinel-token', token.access_token)
    setUser(await api.me())
  }, [])
  const logout = useCallback(async () => { try { await api.logout() } finally { logoutLocal() } }, [logoutLocal])
  const value = useMemo(() => ({ user, loading, login, logout }), [user, loading, login, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() { const value = useContext(AuthContext); if (!value) throw new Error('useAuth must be used inside AuthProvider'); return value }
