const WORD = /[A-Za-z]+(?:['’][A-Za-z]+)?|\d+/g
const lexical = value => String(value).replace(/’/g, "'").toLowerCase()

// Render punctuation and spaces from the original sentence, keeping API word
// indices stable for lookup, annotations and playback.
export function sentenceParts(sentence) {
  const words = sentence.words || [], text = sentence.text || '', matches = [...text.matchAll(WORD)]
  if (!words.length) return [{ text }]
  if (matches.length !== words.length || matches.some((match, i) => lexical(match[0]) !== lexical(words[i].text || words[i].word || words[i].form || ''))) {
    return words.flatMap((word, wordIndex) => [
      { text: String(word.text || word.word || word.form || ''), wordIndex },
      { text: (word.punctuationAfter || '') + (wordIndex < words.length - 1 ? ' ' : '') },
    ])
  }
  const parts = []; let offset = 0
  matches.forEach((match, wordIndex) => {
    if (match.index > offset) parts.push({ text: text.slice(offset, match.index) })
    parts.push({ text: match[0], wordIndex })
    offset = match.index + match[0].length
  })
  if (offset < text.length) parts.push({ text: text.slice(offset) })
  return parts
}

export function wordIsSpoken(words, index, spoken) {
  if (spoken < 0) return false
  return index === spoken || Boolean(words[spoken]?.timingGroup && words[index]?.timingGroup === words[spoken].timingGroup)
}

export function sentenceOnlyHighlight(sentence, active) {
  return active && sentence.timingPolicy === 'kokoro-sentence-audio' &&
    !(sentence.words || []).some(word => Number.isFinite(word.start ?? word.startTime))
}
