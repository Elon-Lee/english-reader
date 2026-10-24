export const READER_APPEARANCE = { readerFontSize: 20, readerLineHeight: 1.8, readerContentWidth: 760 }
export function mediaCompletionProgress({ ended, trial = false, sentences = [] } = {}) {
  const lastSentenceId = sentences.at(-1)?.id
  return ended === true && !trial && lastSentenceId != null && String(lastSentenceId).trim()
    ? { lastSentenceId: String(lastSentenceId), completed: true } : null
}
export function readerAppearance(values = {}) {
  const bounded = (key, min, max) => {
    const value = Number(values[key])
    return values[key] !== null && values[key] !== '' && Number.isFinite(value) && value >= min && value <= max ? value : READER_APPEARANCE[key]
  }
  return { readerFontSize: bounded('readerFontSize', 16, 28), readerLineHeight: bounded('readerLineHeight', 1.4, 2.4), readerContentWidth: bounded('readerContentWidth', 560, 1040) }
}
// Remove only equivalent entries; distinct meanings and parts of speech survive.
export function dictionaryGroups(groups = []) {
  const clean = value => String(value || '').trim()
  const normalized = groups.map(group => ({ ...group, translations: [...new Set((group.translations || []).map(clean).filter(Boolean))] }))
  const specific = new Set(normalized.filter(g => g.pos && !/^any$/i.test(g.pos)).flatMap(g => g.translations))
  const seen = new Set()
  return normalized.map(group => {
    const generic = !group.pos || /^any$/i.test(group.pos)
    const translations = group.translations.filter(value => {
      if (generic && specific.has(value)) return false
      const key = `${String(group.pos || 'any').toLowerCase()}:${value}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
    return { ...group, translations }
  }).filter(group => group.translations.length)
}
export function sentenceIndex(sentences, id, fallback = 0) {
  const index = id == null ? -1 : sentences.findIndex(sentence => String(sentence.id) === String(id))
  return index < 0 ? Math.max(0, Math.min(sentences.length - 1, fallback)) : index
}
export function sentencePlaybackRange(sentences, index, duration) {
  const finite = value => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value)) ? Number(value) : null
  const start = finite(sentences[index]?.start)
  const end = finite(sentences[index]?.end) ?? finite(sentences[index + 1]?.start) ?? finite(duration)
  return start !== null && start >= 0 && end !== null && end > start ? { start, end } : null
}
export function mediaSentenceIndex(sentences, time) {
  let active = -1
  for (let index = 0; index < sentences.length; index++) {
    const start = sentences[index].start
    if (start === null || start === undefined || start === '' || !Number.isFinite(Number(start))) continue
    if (active < 0 || Number(start) <= time) active = index
    if (Number(start) > time) break
  }
  return active
}

// Line mode keeps the active sentence near the reading position. Screen mode
// leaves the reader alone while the sentence is fully visible, then starts the
// next page from the top when the active sentence crosses the viewport edge.
export function readerScrollTop({ mode = 'line', scrollTop = 0, viewportHeight = 0, targetTop = 0, targetHeight = 0, padding = 18 } = {}) {
  const current = Math.max(0, Number(scrollTop) || 0)
  const height = Math.max(0, Number(viewportHeight) || 0)
  const top = Number(targetTop) || 0
  const rowHeight = Math.max(0, Number(targetHeight) || 0)
  if (mode !== 'screen') return Math.max(0, current + top - Math.max(padding, (height - rowHeight) * 0.3))
  const visibleBottom = Math.max(padding, height - padding)
  if (top >= padding && top + rowHeight <= visibleBottom) return null
  return Math.max(0, current + top - padding)
}
