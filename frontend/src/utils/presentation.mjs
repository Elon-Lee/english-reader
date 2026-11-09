export function formatBytes(value) {
  const bytes = Number(value)
  if (!Number.isFinite(bytes) || bytes < 0) return '—'
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${Number((bytes / 1024 ** index).toFixed(index ? 2 : 0))} ${units[index]}`
}

export function displayDate(value, withTime = false) {
  if (!value || !Number.isFinite(new Date(value).getTime())) return '—'
  return new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit', ...(withTime ? { hour: '2-digit', minute: '2-digit' } : {}) }).format(new Date(value))
}

export function isReviewDue(item, now = Date.now()) {
  const due = new Date(item.payload?.due_at || item.payload?.dueAt || 0).getTime()
  return !Number.isFinite(due) || due <= now
}

export function continueReadingBook(books = []) {
  const active = books.filter(book => book.shelfState !== 'later' && book.canRead !== false)
  const recent = [...active].sort((a, b) => (Date.parse(b.readingProgress?.updatedAt) || 0) - (Date.parse(a.readingProgress?.updatedAt) || 0))
  return recent.find(book => book.readingProgress?.updatedAt && !book.readingProgress?.completedAt)
    || active.find(book => !book.readingProgress?.completedAt) || recent[0]
}

export function openReview({ mode = '', ids = [], size = 5, scope = '' } = {}) {
  const query = new URLSearchParams({ screen: 'vocab', size: String(size) })
  if (mode) query.set('review', mode)
  if (scope) query.set('scope', scope)
  if (ids.length) query.set('words', ids.join(','))
  location.href = `/app?${query}`
}

export function learningDuration(seconds = 0) {
  return seconds < 60 ? `${Math.floor(seconds)} 秒` : `${Math.floor(seconds / 60)} 分 ${Math.floor(seconds % 60)} 秒`
}

export function bookDescription(book) {
  const text = String(book.description || '').trim()
  if (text && text !== book.title && text !== book.englishTitle) return text
  return ({ youtube: '跟随原视频逐句听读，点击单词查看语境释义。', video: '结合原声与字幕精读，反复练习不熟悉的句子。', audio: '使用原音逐句听读，把听不清的地方慢慢读懂。' })[book.resourceType] || '逐句阅读正文，积累生词并记录学习进度。'
}

export const resourceNames = { youtube: '在线视频', video: '视频', audio: '音频', book: '文本', text: '文本', pdf: 'PDF' }
