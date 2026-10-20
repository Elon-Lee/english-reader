// Each service can finish independently; stale selections/retries cannot replace newer results.
export function createReaderRequests() {
  let selection = 0
  const revisions = new Map()
  return {
    select() { selection += 1; revisions.clear(); return selection },
    async run(section, load, resolve, reject) {
      const selected = selection
      const revision = (revisions.get(section) || 0) + 1
      revisions.set(section, revision)
      const current = () => selected === selection && revisions.get(section) === revision
      try { const result = await load(); if (current()) resolve(result) }
      catch (error) { if (current()) reject(error) }
    },
  }
}

export function readerWordMeaning(info, savedWord) {
  const context = info?.context || {}
  return savedWord?.payload?.meaning || context.meaning || context.explanation || context.contextExplanation || context.payload?.text || info?.dictionary?.groups?.flatMap(group => group.translations || []).filter(Boolean).slice(0,3).join('；') || ''
}

export function createReaderDraftStore(storage, ownerId, bookId, kind) {
  const key = `shiyue:reader-draft:v1:${encodeURIComponent(ownerId)}:${kind}:${encodeURIComponent(bookId)}`
  return {
    read() {
      try {
        const data = JSON.parse(storage?.getItem(key) || 'null')
        if (!data || data.version !== 1 || data.ownerId !== ownerId || data.bookId !== bookId || data.kind !== kind || !Number.isFinite(data.updatedAt) || Date.now() - data.updatedAt > 7 * 86400000) return null
        if (!Number.isFinite(data.seconds) || data.seconds < 0 || !Array.isArray(data.visited) || !Array.isArray(data.newWordIds)) return null
        if (data.counters && (typeof data.counters !== 'object' || Array.isArray(data.counters) || Object.values(data.counters).some(value => !Number.isFinite(value) || value < 0))) return null
        if (data.pending && (data.pending.bookId !== bookId || typeof data.pending.idempotencyKey !== 'string' || !data.pending.idempotencyKey.startsWith('modern-reader-') || !Number.isFinite(data.pending.readingSeconds))) return null
        return data
      } catch { return null }
    },
    write(data) {
      try { if (!storage) return false; storage.setItem(key, JSON.stringify({...data, version:1, ownerId, bookId, kind, updatedAt:Date.now()})); return true }
      catch { return false }
    },
    clear() { try { storage?.removeItem(key) } catch {} },
  }
}
