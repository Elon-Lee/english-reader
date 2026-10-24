// Derive reading state from book progress
export function deriveReadingState(book) {
  if (book.progress >= 95) return 'finished'
  if (book.progress > 0) return 'reading'
  return 'unstarted'
}

export const READING_STATES = [
  { key: 'all', label: '全部' },
  { key: 'reading', label: '正在读' },
  { key: 'unstarted', label: '未开始' },
  { key: 'finished', label: '已读完' },
]

export function formatLastUpdated(timestamp) {
  if (!timestamp) return ''
  const now = Date.now()
  const diff = now - new Date(timestamp).getTime()
  const days = Math.floor(diff / (1000 * 60 * 60 * 24))
  if (days === 0) return '今天更新'
  if (days === 1) return '昨天更新'
  if (days < 7) return `${days} 天前更新`
  if (days < 30) return `${Math.floor(days / 7)} 周前更新`
  return `${Math.floor(days / 30)} 个月前更新`
}
