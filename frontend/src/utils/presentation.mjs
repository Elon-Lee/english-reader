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

export function displayBenefits(product) {
  return [...new Set((product?.benefits || []).map(text => String(text)
    .replace(/^免费包含[：:]\s*/, '')
    .replace('公版书架收藏不限量', '官方文本收藏不限量；音视频计入收藏上限')))]
    .sort((a, b) => benefitOrder(a) - benefitOrder(b))
}

function benefitOrder(text) {
  return /词汇|句法/.test(text) ? 0 : /空间/.test(text) ? 1 : /最多收藏/.test(text) ? 2 : /视频可/.test(text) ? 3 : /设备/.test(text) ? 4 : 5
}

export function featuredProductId(products) {
  return products.find(product => product.family !== 'free' && product.featured)?.id
}

export function purchaseAction(product, authenticated, state) {
  if (product.family === 'free') return { label: authenticated ? '进入学习空间' : '免费注册', disabled: false }
  if (!authenticated) return { label: '登录后购买 / 兑换', disabled: false }
  if (!state || state.loading) return { label: '正在核对会员权益', disabled: true, loading: true }
  if (state.error?.code === 'membership_downgrade_not_allowed') return { label: '当前会员高于此方案', disabled: true }
  if (state.error) return { label: '重新核对权益', disabled: false, retry: true }
  if (state.preview?.changeType === 'renewal') return { label: `续费${product.shortName || product.name}`, disabled: false }
  if (state.preview?.changeType === 'upgrade') return { label: `升级到${product.shortName || product.name}`, disabled: false }
  return { label: '购买 / 兑换', disabled: false }
}

export function isReviewDue(item, now = Date.now()) {
  const due = new Date(item.payload?.due_at || item.payload?.dueAt || 0).getTime()
  return !Number.isFinite(due) || due <= now
}

export function bookDescription(book) {
  const text = String(book.description || '').trim()
  if (text && text !== book.title && text !== book.englishTitle) return text
  return ({ youtube: '跟随原视频逐句听读，点击单词查看语境释义。', video: '结合原声与字幕精读，反复练习不熟悉的句子。', audio: '使用原音逐句听读，把听不清的地方慢慢读懂。' })[book.resourceType] || '逐句阅读正文，积累生词并记录学习进度。'
}

export const resourceNames = { youtube: '在线视频', video: '视频', audio: '音频', book: '文本', text: '文本', pdf: 'PDF' }
export const orderStatusNames = { paid: '已支付', completed: '已开通', pending: '待处理', failed: '未完成', cancelled: '已取消', refunded: '已退款', expired: '已过期', applied: '已生效' }
