const WORD = /[A-Za-z]+(?:['’][A-Za-z]+)?|\d+/g

export function canReadExtensively(book, trial = Boolean(book?.trial)) {
  if (!book) return false
  const document = book.readingDocument
  if (document?.version === 1 && document.format === 'epub' && document.blocks?.length > 0) return true
  return !trial && (book.mediaAssets || []).some(asset => asset.contentType === 'application/pdf' ||
    (asset.variants || []).some(variant => variant.contentType === 'application/pdf'))
}

export function readingBlocks(book) {
  if (book?.readingDocument?.version === 1 && book.readingDocument.blocks?.length) return book.readingDocument.blocks
  // Read-only compatibility: historical sentence data has no recoverable paragraph boundaries.
  return (book?.sentences || []).map((sentence, index) => ({
    id: `legacy-${index}`, type: 'paragraph', text: sentence.text, page: sentence.page,
    words: Array.from(sentence.text.matchAll(WORD), (match, wordIndex) => ({
      start: Array.from(sentence.text.slice(0, match.index)).length,
      end: Array.from(sentence.text.slice(0, match.index + match[0].length)).length,
      sentenceId: sentence.id, wordIndex,
    })),
  }))
}

export function blockParts(block) {
  const chars = Array.from(block.text || ''), parts = []
  let offset = 0
  for (const word of block.words || []) {
    if (word.start < offset || word.end > chars.length) continue
    if (word.start > offset) parts.push({ text: chars.slice(offset, word.start).join('') })
    parts.push({ ...word, text: chars.slice(word.start, word.end).join('') })
    offset = word.end
  }
  if (offset < chars.length) parts.push({ text: chars.slice(offset).join('') })
  return parts
}

export function pageForOffset(offset, width, gap = 48) {
  return Math.max(0, Math.floor((offset + 1) / Math.max(1, width + gap)))
}

export function readingChapters(blocks, title) {
  const chapters = []
  let previous
  for (const block of blocks) {
    if (block.type === 'heading' || (block.section && block.section !== previous)) {
      chapters.push({ id: block.id, title: block.type === 'heading' ? block.text : `章节 ${chapters.length + 1}`, sentenceId: block.words?.[0]?.sentenceId, page: block.page })
    }
    previous = block.section
  }
  return chapters.length ? chapters : [{ id: blocks[0]?.id, title, sentenceId: blocks[0]?.words?.[0]?.sentenceId, page: 1 }]
}
