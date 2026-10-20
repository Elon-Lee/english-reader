import { getJson, postJson } from './client'

export const JOURNEY_CHANGED = 'shiyue:journey-changed'

export async function updateJourney(payload) {
  const state = await postJson('/api/workspace/journey', payload)
  window.dispatchEvent(new CustomEvent(JOURNEY_CHANGED, { detail: state }))
  return state
}

export async function refreshJourney() {
  const state = await getJson('/api/workspace/journey')
  window.dispatchEvent(new CustomEvent(JOURNEY_CHANGED, { detail: state }))
  return state
}
