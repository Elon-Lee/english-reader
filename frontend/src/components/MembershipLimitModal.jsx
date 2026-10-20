import React, { useEffect, useRef, useState } from 'react'
import { Alert, Button, Card, Empty, Modal, Skeleton, Space, Tag, Typography } from 'antd'
import { getJson } from '../api/client'
import { MEMBERSHIP_LIMIT_EVENT } from '../api/membershipLimit'
import { CloudCatPurchaseModal, PlanHighlights, PriceDisplay } from '../pages/PublicSite'
import { featuredProductId } from '../utils/presentation.mjs'

const { Text } = Typography

export default function MembershipLimitModal({ onRefresh }) {
  const [request, setRequest] = useState(null)
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [product, setProduct] = useState(null)
  const [completed, setCompleted] = useState(false)
  const [continuing, setContinuing] = useState(false)
  const sequence = useRef(0)

  const load = async () => {
    const id = ++sequence.current
    setLoading(true); setError(''); setProducts([])
    try {
      const catalog = await getJson('/api/commerce/products')
      const results = await Promise.all(catalog.products.filter(item => item.family !== 'free').map(async item => {
        try {
          const preview = await getJson(`/api/membership/change-preview?targetPlan=${encodeURIComponent(item.planVersion)}`)
          return preview.targetPlan.rank > preview.currentPlan.rank ? { ...item, rank: preview.targetPlan.rank } : null
        } catch (failure) {
          if (failure.code === 'membership_downgrade_not_allowed') return null
          throw failure
        }
      }))
      if (id === sequence.current) setProducts(results.filter(Boolean).sort((a, b) => a.rank - b.rank || a.amountCents - b.amountCents))
    } catch (failure) {
      if (id === sequence.current) setError(failure.message || '套餐加载失败')
    } finally { if (id === sequence.current) setLoading(false) }
  }

  useEffect(() => {
    const show = event => {
      setRequest(event.detail); setProduct(null); setCompleted(false); setContinuing(false)
      void load()
    }
    window.addEventListener(MEMBERSHIP_LIMIT_EVENT, show)
    return () => { sequence.current += 1; window.removeEventListener(MEMBERSHIP_LIMIT_EVENT, show) }
  }, [])

  const close = () => { sequence.current += 1; setRequest(null); setProduct(null) }
  const resume = async () => {
    const id = sequence.current
    setContinuing(true)
    try { await request.onContinue?.(); if (id === sequence.current) close() }
    catch (failure) { setError(failure.message || '继续操作失败，请返回原页面重试') }
    finally { setContinuing(false) }
  }

  return <>
    <Modal title={completed ? '会员升级成功' : '选择学习方案'} open={Boolean(request) && !product} onCancel={continuing ? undefined : close} footer={null} width={980}>
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Alert showIcon type={completed ? 'success' : 'warning'} message={completed ? '新会员权益已生效，可继续刚才的操作。' : request?.message} />
        {loading ? <Skeleton active /> : error ? <Alert showIcon type="error" message={error} action={<Button onClick={completed ? resume : load}>重试</Button>} /> : completed ? <Button type="primary" loading={continuing} onClick={resume}>{request?.onContinue ? '继续刚才的操作' : '返回继续使用'}</Button> : products.length ? <div className="membership-limit-plan-grid">{products.map(item => <Card key={item.id} className="membership-plan-card" title={<Space>{item.shortName || item.name}{item.id === featuredProductId(products) && <Tag color="success">推荐</Tag>}</Space>} extra={<PriceDisplay product={item} />}>
          <Text type="secondary">每次兑换 {item.durationDays || 30} 天</Text>
          <PlanHighlights product={item} />
          <Button block type="primary" onClick={() => setProduct(item)}>购买 / 兑换</Button>
          {!item.purchaseUrl && <Text type="secondary">暂未开放购买，可使用已有兑换码</Text>}
        </Card>)}</div> : <Empty description="当前暂无可升级套餐。可移除不再需要的收藏释放名额；每日额度可等待次日恢复。" />}
      </Space>
    </Modal>
    <CloudCatPurchaseModal product={product} open={Boolean(product)} authenticated returnTo={`${location.pathname}${location.search}`} onClose={() => setProduct(null)} onRedeemed={async () => {
      setCompleted(true); setProduct(null)
      try { await onRefresh?.() } catch { /* Server redemption has already committed. */ }
    }} />
  </>
}
