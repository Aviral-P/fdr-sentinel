import { useCallback, useEffect, useState } from 'react'
import { ApiError } from '../lib/api'

export function useRemote<T>(load: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const refresh = useCallback(async () => {
    setLoading(true); setError(null)
    try { setData(await load()) } catch (e) { setError(e instanceof ApiError ? e.message : 'Something went wrong. Try again.') }
    finally { setLoading(false) }
  // load identity is represented by deps at call sites.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  useEffect(() => { void refresh() }, [refresh])
  return { data, loading, error, refresh, setData }
}
