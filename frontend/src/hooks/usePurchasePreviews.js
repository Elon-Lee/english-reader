import { useCallback, useEffect, useState } from 'react'
import { getJson } from '../api/client'

export default function usePurchasePreviews(products, authenticated) {
  const [states, setStates] = useState({})
  const [revision, setRevision] = useState(0)
  const targets = products.filter(item => item.family !== 'free').map(item => item.planVersion).join('|')
  useEffect(() => {
    let active = true
    setStates({})
    if (authenticated && targets) {
      for (const target of targets.split('|')) {
        getJson(`/api/membership/change-preview?targetPlan=${encodeURIComponent(target)}`)
          .then(preview => { if (active) setStates(current => ({ ...current, [target]: { preview } })) })
          .catch(error => { if (active) setStates(current => ({ ...current, [target]: { error } })) })
      }
    }
    return () => { active = false }
  }, [targets, authenticated, revision])
  const retry = useCallback(() => setRevision(value => value + 1), [])
  return { states, retry }
}
