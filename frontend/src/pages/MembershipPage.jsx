import React, { useEffect, useRef, useState } from 'react'
import { Alert, Button, Card, Col, Input, List, Modal, Progress, Row, Space, Table, Tabs, Tag, Typography, message } from 'antd'
import { ThunderboltFilled } from '@ant-design/icons'
import { getJson, postJson } from '../api/client'
import { CloudCatPurchaseModal, PricingSection } from './PublicSite'
import { displayDate, formatBytes, orderStatusNames } from '../utils/presentation.mjs'
import { PurchaseRecovery } from '../components/LearningJourney'
import { refreshJourney } from '../api/journey'

const { Paragraph, Text, Title } = Typography

function UsageCard({ title, used, limit, unlimited, storage = false, note }) {
  const known = used != null && (limit != null || unlimited)
  const format = value => storage ? formatBytes(value) : `${value} 个`
  const percent = known && Number(limit) > 0 ? Math.min(100, Number(used) / Number(limit) * 100) : 0
  const over = known && !unlimited && Number(used) > Number(limit)
  return <Card title={title} className="quota-card">
    <Text strong className="quota-value">{known ? `${format(used)} / ${unlimited ? '不限量' : format(limit)}` : '暂无用量数据'}</Text>
    {known && !unlimited && <Progress percent={percent} showInfo={false} strokeColor={over ? '#b75a31' : '#2f6f50'} />}
    <Paragraph type={over ? 'warning' : 'secondary'}>{over ? '已超过当前方案上限，释放空间或名额后可继续新增。' : note}</Paragraph>
  </Card>
}

export default function MembershipPage({ membership, membershipOrders, onRefresh }) {
  const [catalog, setCatalog] = useState({ products: [] })
  const [catalogLoading, setCatalogLoading] = useState(true)
  const [catalogError, setCatalogError] = useState('')
  const [revision, setRevision] = useState(0)
  const [manageOpen, setManageOpen] = useState(false)
  const [purchaseProduct, setPurchaseProduct] = useState(null)
  const [redeemOpen, setRedeemOpen] = useState(false)
  const [redeemCode, setRedeemCode] = useState('')
  const [redeemError, setRedeemError] = useState('')
  const [redeeming, setRedeeming] = useState(false)
  const [redeemResult, setRedeemResult] = useState(null)
  const [messageApi, contextHolder] = message.useMessage()
  const pending = useRef(false)
  const attempt = useRef({ code: '', key: '' })
  const plan = membership?.plan
  const usage = membership?.usage || []
  const capacity = membership?.mediaCapacity || {}
  const storage = usage.find(item => item.feature === 'storage_bytes')
  const ai = usage.find(item => item.feature === 'ai_context_generations')
  const grammar = usage.find(item => item.feature === 'ai_grammar_generations')
  const purchaseSlug = new URLSearchParams(location.search).get('purchase')
  const needsCatalog = manageOpen || Boolean(purchaseSlug)
  useEffect(() => {
    if (!needsCatalog) return
    let active = true
    setCatalogLoading(true); setCatalogError('')
    getJson('/api/commerce/products').then(value => { if (active) setCatalog(value) }).catch(error => { if (active) setCatalogError(error.message || '套餐加载失败') }).finally(() => { if (active) setCatalogLoading(false) })
    return () => { active = false }
  }, [needsCatalog, revision])
  useEffect(() => {
    const product = catalog.products.find(item => item.slug === purchaseSlug && item.family !== 'free')
    if (product) setPurchaseProduct(product)
  }, [catalog.products, purchaseSlug])

  const redeem = async () => {
    if (pending.current || redeemResult) return
    const code = redeemCode.trim().toUpperCase()
    if (!/^SY-[A-F0-9]{32}$/.test(code)) { setRedeemError('请输入完整兑换码：SY- 后接 32 位字符。'); return }
    pending.current = true; setRedeeming(true); setRedeemError('')
    if (attempt.current.code !== code) attempt.current = { code, key: `membership-redeem-${crypto.randomUUID?.() || Date.now()}` }
    try {
      const result = await postJson('/api/membership/redeem', { code, idempotencyKey: attempt.current.key })
      setRedeemResult(result); setRedeemCode('')
      void refreshJourney().catch(() => {})
      try { await onRefresh?.() } catch { messageApi.warning('兑换已成功，用量暂未刷新，请稍后重试。') }
    } catch (error) { setRedeemError(error.message || '兑换未完成，请重试。') }
    finally { pending.current = false; setRedeeming(false) }
  }
  const openPurchase = product => {
    setManageOpen(false); setPurchaseProduct(product)
    const params = new URLSearchParams(location.search); params.set('purchase', product.slug)
    history.replaceState({}, '', `${location.pathname}?${params}`)
  }
  const closePurchase = () => {
    setPurchaseProduct(null)
    const params = new URLSearchParams(location.search); params.delete('purchase')
    history.replaceState({}, '', `${location.pathname}?${params}`)
  }
  const orderColumns = [
    { title: '方案与金额', key: 'plan', render: (_, order) => <Space direction="vertical" size={2}><Text strong>{order.planName || '会员服务'}</Text><Text>{new Intl.NumberFormat('zh-CN', { style: 'currency', currency: order.currency || 'CNY' }).format(Number(order.amountCents || 0) / 100)}</Text></Space> },
    { title: '创建时间', dataIndex: 'createdAt', render: value => displayDate(value, true) },
    { title: '来源', dataIndex: 'provider', render: value => ({ cloudcat: '云猫兑换', mbdpay: '历史支付订单', paddle: '历史支付订单', manual: '人工开通' })[value] || '会员订单' },
    { title: '状态', dataIndex: 'status', render: value => <Tag color={['paid', 'completed'].includes(value) ? 'success' : value === 'failed' ? 'error' : 'default'}>{orderStatusNames[value] || '处理中'}</Tag> },
    { title: '订单编号', dataIndex: 'id', render: value => <Text copyable={{ text: value }} className="order-id">{value}</Text> },
  ]

  return <div className="page-stack">
    {contextHolder}
    <PurchaseRecovery />
    <div className="page-intro"><div><Text className="eyebrow">MEMBERSHIP</Text><Title level={1}>会员中心</Title><Paragraph>你的当前权益、使用情况与开通记录。</Paragraph></div><Space><Button onClick={() => { setRedeemOpen(true); setRedeemResult(null); setRedeemError('') }}>兑换码</Button><Button type="primary" onClick={() => setManageOpen(true)}>{plan?.slug === 'free' ? '升级会员' : '续费 / 比较方案'}</Button></Space></div>
    {!plan ? <Alert type="error" showIcon message="会员信息暂时不可用" action={<Button onClick={onRefresh}>重新加载</Button>} /> : <Card className="membership-hero">
      <Space align="start"><div className="membership-icon"><ThunderboltFilled /></div><div className="membership-current-copy">
        <div className="membership-current-line"><Text className="card-kicker">当前方案</Text><Title level={2}>{plan.name}</Title></div>
        <Text className="membership-expiry">{membership?.subscription?.endsAt ? `有效期至 ${displayDate(membership.subscription.endsAt)} · 不自动续费` : plan.slug === 'free' ? '免费权益持续可用' : '暂无有效期信息'}</Text>
        <Text type="secondary">{membership?.canWatchHdVideo ? '支持流畅与高清画质' : '流畅画质 · 付费会员可切换高清'}</Text>
      </div></Space>
      <div className="membership-ai-summary"><Tag color="green">{ai?.unlimited ? '词汇语境分析不限次数' : `今日词汇分析剩余 ${ai?.available ?? '—'} 次`}</Tag><Tag color="green">{grammar?.unlimited ? '句法分析不限次数' : `今日句法分析剩余 ${grammar?.available ?? '—'} 次`}</Tag>{!ai?.unlimited && <Text type="secondary">每日额度按北京时间零点恢复</Text>}</div>
    </Card>}
    <Row gutter={[16, 16]}>
      <Col xs={24} md={8}><UsageCard title="私人学习空间" used={storage?.used} limit={storage?.limit} unlimited={storage?.unlimited} storage note="包含私人原文件及生成的学习资源" /></Col>
      <Col xs={24} md={8}><UsageCard title="视频收藏" used={capacity.video?.used} limit={capacity.video?.limit} note="官方与私人视频合计，归档仍占名额" /></Col>
      <Col xs={24} md={8}><UsageCard title="音频收藏" used={capacity.audio?.used} limit={capacity.audio?.limit} note="官方与私人音频合计，归档仍占名额" /></Col>
    </Row>
    <Tabs className="membership-history" items={[
      { key: 'orders', label: '开通订单', children: <Card><Table rowKey="id" columns={orderColumns} dataSource={membershipOrders || []} pagination={{ pageSize: 5, hideOnSinglePage: true, showSizeChanger: false }} locale={{ emptyText: '暂无开通订单，免费方案也可开始学习。' }} /></Card> },
      { key: 'changes', label: '权益变更', children: <Card><List pagination={{ pageSize: 5, hideOnSinglePage: true }} dataSource={membership?.changeOrders || []} locale={{ emptyText: '暂无权益变更' }} renderItem={order => <List.Item><List.Item.Meta title={`${({ upgrade: '升级', renewal: '续费', activation: '开通', downgrade: '历史调整' })[order.changeType] || '开通'}：${order.toPlanName || '会员方案'}`} description={`${orderStatusNames[order.status] || '处理中'} · ${order.status === 'cancelled' ? '记录于' : '生效于'} ${displayDate(order.status === 'cancelled' ? order.createdAt : order.effectiveAt)}${order.carryDays ? ` · 剩余权益折算 ${order.carryDays} 天` : ''}`} /></List.Item>} /></Card> },
    ]} />
    <Modal title="兑换会员码" open={redeemOpen} onCancel={redeeming ? undefined : () => setRedeemOpen(false)} closable={!redeeming} maskClosable={!redeeming} keyboard={!redeeming} onOk={redeemResult ? () => setRedeemOpen(false) : redeem} okText={redeemResult ? '完成' : '确认兑换'} confirmLoading={redeeming} cancelButtonProps={{ disabled: redeeming }}>
      <Paragraph>权益开通到当前账号。同级续费延长有效期，升级按剩余价值折算；不支持降级。</Paragraph>
      {!redeemResult && <Input aria-label="云猫兑换码" value={redeemCode} disabled={redeeming} status={redeemError ? 'error' : undefined} onChange={event => { setRedeemCode(event.target.value.toUpperCase()); setRedeemError('') }} onPressEnter={redeem} placeholder="SY- 后接 32 位兑换码" maxLength={35} autoComplete="off" />}
      {redeemError && <Alert showIcon type="error" message={redeemError} style={{ marginTop: 12 }} />}
      {redeemResult && <Alert showIcon type="success" message={`${redeemResult.planName}兑换成功`} description={`有效期至 ${displayDate(redeemResult.endsAt)}`} />}
    </Modal>
    <Modal width={1200} title="选择学习方案" open={manageOpen} onCancel={() => setManageOpen(false)} footer={null} destroyOnClose>
      {manageOpen && <PricingSection authenticated products={catalog.products} loading={catalogLoading} error={catalogError} onRetry={() => setRevision(value => value + 1)} onPurchase={product => openPurchase(product)} title="按需要续费或升级" />}
    </Modal>
    {catalogError && purchaseSlug && !manageOpen && <Alert type="error" showIcon message={catalogError} action={<Button onClick={() => setRevision(value => value + 1)}>重试</Button>} />}
    {purchaseSlug && !catalogLoading && !catalogError && !catalog.products.some(item => item.slug === purchaseSlug && item.family !== 'free') && <Alert type="info" showIcon message="上次选择的方案已停止新售" description="已有兑换码仍可通过会员中心核验开通，也可以重新比较当前方案。" action={<Button onClick={() => { closePurchase(); setRedeemOpen(true); setRedeemResult(null); setRedeemError('') }}>已有兑换码</Button>} />}
    <CloudCatPurchaseModal product={purchaseProduct} open={Boolean(purchaseProduct)} authenticated returnTo="/app?screen=membership" onClose={closePurchase} onRedeemed={() => onRefresh?.()} />
  </div>
}
