import { useCallback, useEffect, useRef, useState } from 'react'
import { getJson } from '../api/client'
import { JOURNEY_CHANGED } from '../api/journey'

export default function useJourney(enabled = true) {
  const [state, setState] = useState(null)
  const [loading, setLoading] = useState(enabled)
  const [error, setError] = useState('')
  const sequence = useRef(0)
  const reload = useCallback(async () => {
    const request = ++sequence.current
    setLoading(true); setError('')
    try {
      const result = await getJson('/api/workspace/journey')
      if (request === sequence.current) setState(result)
    } catch (failure) {
      if (request === sequence.current) setError(failure.message || '请稍后重试')
    } finally { if (request === sequence.current) setLoading(false) }
  }, [])
  useEffect(() => {
    if (!enabled) { setState(null); setLoading(false); return }
    void reload()
    const change = event => { sequence.current += 1; setState(event.detail); setLoading(false); setError('') }
    const refresh = () => { if (document.visibilityState === 'visible') void reload() }
    window.addEventListener(JOURNEY_CHANGED, change)
    document.addEventListener('visibilitychange', refresh)
    return () => { sequence.current += 1; window.removeEventListener(JOURNEY_CHANGED, change); document.removeEventListener('visibilitychange', refresh) }
  }, [enabled, reload])
  return { state, loading, error, reload }
}
