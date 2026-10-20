export const READER_APPEARANCE = { readerFontSize: 20, readerLineHeight: 1.8, readerContentWidth: 760 }
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
