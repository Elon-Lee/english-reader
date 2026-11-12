export { displayDate, formatBytes } from '../../../utils/presentation.mjs'

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

// Values come from the published product, including its public AI policy.
export function planHighlights(product) {
  const limits = product.featureLimits || {}
  const count = (key, suffix) => Number.isFinite(Number(limits[key])) && limits[key] != null ? `${Number(limits[key])} ${suffix}` : '以完整权益为准'
  const benefit = label => displayBenefits(product).find(item => item.includes(label))?.replace(label, '').trim() || '以完整权益为准'
  return [
    ['私人空间', count('storage_bytes', 'GB')],
    ['视频收藏', count('video_library_capacity', '个')],
    ['音频收藏', count('audio_library_capacity', '个')],
    ['词汇语境', benefit('词汇语境分析')],
    ['句法分析', benefit('句法分析')],
    ['同时登录', count('devices', '台设备')],
  ]
}

export function sharedBenefits(products) {
  if (!products.length) return []
  const benefits = products.map(displayBenefits)
  return benefits[0].filter(item => benefits.every(list => list.includes(item)))
}

export function purchaseAction(product, authenticated, state) {
  if (product.family === 'free') return { label: authenticated ? '进入学习空间' : '免费注册', disabled: false }
  if (!authenticated) return { label: '登录后购买 / 兑换', disabled: false }
  if (!state || state.loading) return { label: '正在核对会员权益', disabled: true, loading: true }
  if (state.error?.code === 'membership_downgrade_not_allowed') return { label: '当前会员高于此方案', disabled: true }
  if (state.error) return { label: '重新核对权益', disabled: false, retry: true }
  if (!(product.paymentMethods || []).length && product.redemptionEnabled === false) return { label: '暂未开放购买', disabled: true }
  if (state.preview?.changeType === 'renewal') return { label: `续费${product.shortName || product.name}`, disabled: false }
  if (state.preview?.changeType === 'upgrade') return { label: `升级到${product.shortName || product.name}`, disabled: false }
  return { label: '购买 / 兑换', disabled: false }
}


export const orderStatusNames = { paid: '已支付', completed: '已开通', pending: '待处理', failed: '未完成', cancelled: '已取消', refunded: '已退款', expired: '已过期', applied: '已生效' }
