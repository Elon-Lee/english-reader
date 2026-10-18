import React, { useEffect, useState } from 'react'
import { Alert, Button, Card, Col, Empty, Input, List, Modal, Progress, Row, Space, Tag, Typography, message } from 'antd'
import { CheckCircleFilled, ThunderboltFilled } from '@ant-design/icons'

import { getJson, postJson } from '../api/client'
import { CloudCatPurchaseModal, PriceDisplay } from './PublicSite'

const { Paragraph, Text, Title } = Typography

const featureNames = {
  official_library_capacity: '官方书架容量', official_unlocks: '公版及授权材料使用', ai_context_generations: '词汇语境分析', ai_grammar_generations: '句法分析', mp3_imports: 'MP3 学习导入', video_imports: '视频学习导入', youtube_imports: '在线视频学习导入', storage_bytes: '私人学习空间', devices: '登录设备',
}

function quotaText(key, value) {
  if (key === 'storage_bytes') return `${(Number(value || 0) / 1024 / 1024 / 1024).toFixed(Number(value) >= 10 * 1024 ** 3 ? 0 : 1)} GB`
  return String(value ?? '—')
}

function money(cents) { return `¥${(Number(cents || 0) / 100).toFixed(0)}` }

export default function MembershipPage({ membership, membershipOrders, onRefresh }) {
  const [catalog, setCatalog] = useState({ products: [], payment: {}, support: { value: '289614546' } })
  const [manageOpen, setManageOpen] = useState(false)
  const [purchaseProduct, setPurchaseProduct] = useState(null)
  const [redeemOpen, setRedeemOpen] = useState(false)
  const [redeemCode, setRedeemCode] = useState('')
  const [redeeming, setRedeeming] = useState(false)
  const [messageApi, contextHolder] = message.useMessage()
  const plan = membership?.plan
  const usage = membership?.usage || []
  const changeOrders = membership?.changeOrders || []
  const ai = usage.find(item => item.feature === 'ai_context_generations')
  const grammar = usage.find(item => item.feature === 'ai_grammar_generations')
  const aiPercent = ai?.limit ? Math.min(100, Math.round((ai.used / ai.limit) * 100)) : 0
  useEffect(() => { getJson('/api/commerce/products', { products: [], payment: {}, support: { value: '289614546' } }).then(setCatalog) }, [])
  useEffect(() => {
    const slug = new URLSearchParams(location.search).get('purchase')
    if (!slug || !catalog.products.length) return
    const product = catalog.products.find(item => item.slug === slug && item.purchaseUrl)
    if (product) setPurchaseProduct(product)
  }, [catalog.products])
  const redeem = async () => {
    setRedeeming(true)
    try {
      const result = await postJson('/api/membership/redeem', { code: redeemCode.trim() })
      setRedeemOpen(false); setRedeemCode(''); await onRefresh?.()
      messageApi.success(`兑换成功：${result.planName}，有效期至 ${new Date(result.endsAt).toLocaleDateString('zh-CN')}`)
    } catch (error) { messageApi.error(error.message || '兑换失败') }
    finally { setRedeeming(false) }
  }
  const openPurchase = product => {
    setManageOpen(false)
    setPurchaseProduct(product)
    const params = new URLSearchParams(location.search)
    params.set('purchase', product.slug)
    history.replaceState({}, '', `${location.pathname}?${params}`)
  }
  const closePurchase = () => {
    setPurchaseProduct(null)
    const params = new URLSearchParams(location.search)
    params.delete('purchase')
    const query = params.toString()
    history.replaceState({}, '', `${location.pathname}${query ? `?${query}` : ''}`)
  }
  const capacity = membership?.mediaCapacity || {}

  return <div className="page-stack">
    {contextHolder}
    <div className="page-intro"><div><Text className="eyebrow">MEMBERSHIP</Text><Title level={1}>会员中心</Title><Paragraph>查看当前空间和收藏上限。购买月卡后，在这里兑换云猫寄售提供的兑换码。</Paragraph></div><Space><Button onClick={() => setRedeemOpen(true)}>兑换码</Button><Button href="/pricing">套餐价格</Button><Button type="primary" onClick={() => setManageOpen(true)}>续费或升级</Button></Space></div>
    <Card className="membership-hero">
      <Space align="start"><div className="membership-icon"><ThunderboltFilled /></div><div className="membership-current-copy">
        <div className="membership-current-line"><Text className="card-kicker">当前方案</Text><Title level={2}>{plan?.name || '未登录或暂无套餐'}</Title></div>
        <Text className="membership-expiry">{membership?.subscription?.endsAt ? `当前会员权益有效至 ${new Date(membership.subscription.endsAt).toLocaleDateString('zh-CN')}` : plan?.slug === 'free' ? '免费权益持续可用' : '登录后读取会员有效期'}</Text>
        <Text type="secondary">{membership?.canWatchHdVideo ? '视频可在流畅与高清之间切换' : '视频仅可观看流畅版；开通付费会员可使用高清'}</Text>
      </div></Space>
      <Progress percent={ai?.unlimited ? 0 : aiPercent} format={() => ai?.unlimited ? '词汇语境与句法分析不限次数' : ai ? `今日词汇 ${ai.available} 次 · 句法 ${grammar?.available ?? '—'} 次` : '暂无额度数据'} strokeColor="#f08b67" />
    </Card>
    {changeOrders.length > 0 && <Card title="会员变更记录"><List size="small" dataSource={changeOrders} renderItem={order => <List.Item><List.Item.Meta title={`${order.changeType === 'upgrade' ? '升级' : order.changeType === 'downgrade' ? '降级' : order.changeType === 'renewal' ? '续费' : '首次开通'}：${order.toPlanName || order.toPlanVersion}`} description={`${order.status === 'applied' ? '已生效' : order.status === 'cancelled' ? '已取消' : order.status} · ${new Date(order.effectiveAt).toLocaleDateString('zh-CN')} 生效${order.carryDays ? ` · 折算 ${order.carryDays} 天` : ''}`} /></List.Item>} /></Card>}
    <Row gutter={[16, 16]}>{[['私人空间', <Text strong key="storage">{usage.find(item => item.feature === 'storage_bytes')?.used || 0} / {quotaText('storage_bytes', usage.find(item => item.feature === 'storage_bytes')?.limit)} 已使用</Text>], ['视频收藏', `${capacity.video?.used ?? 0} / ${capacity.video?.limit ?? 0} 个（公版 + 私人）`], ['音频收藏', `${capacity.audio?.used ?? 0} / ${capacity.audio?.limit ?? 0} 个（公版 + 私人）`]].map(([title, value]) => <Col xs={24} md={8} key={title}><Card title={title} className="quota-card">{value}</Card></Col>)}</Row>
    <Card title="订单记录"><List size="small" dataSource={membershipOrders || []} locale={{ emptyText: '暂无订单记录' }} renderItem={order => <List.Item><List.Item.Meta title={`${order.planVersion} · ${(order.amountCents / 100).toFixed(2)} ${order.currency || 'CNY'}`} description={`${order.provider === 'cloudcat' ? '云猫寄售兑换' : order.provider === 'mbdpay' ? '历史面包多 Pay 订单' : order.provider === 'paddle' ? '历史 Paddle 订单' : '人工订单'} · ${order.note || '无备注'}`} /><Tag color={order.status === 'paid' || order.status === 'completed' ? 'success' : order.status === 'pending' ? 'processing' : order.status === 'failed' ? 'error' : 'default'}>{order.status}</Tag></List.Item>} /></Card>
    <Modal title="兑换会员码" open={redeemOpen} onCancel={() => setRedeemOpen(false)} onOk={redeem} okText="确认兑换" confirmLoading={redeeming}><Input value={redeemCode} onChange={event => setRedeemCode(event.target.value.toUpperCase())} placeholder="SY- 后接 32 位兑换码" maxLength={35} autoComplete="off" /></Modal>
    <Modal width={980} title="选择学习方案" open={manageOpen} onCancel={() => setManageOpen(false)} footer={null}><Alert showIcon type="success" message="免费版持续可用；付费方案每次兑换 30 天" description="进阶与 Pro 通过云猫寄售单次购买，不自动续费。" /><Row gutter={[16, 16]} style={{ marginTop: 18 }}>{catalog.products.map(product => <Col xs={24} md={12} xl={8} key={product.id}><Card className={`membership-plan-card ${product.featured ? 'current' : ''}`} title={<Space>{product.shortName}{product.featured && <Tag color="success">推荐</Tag>}</Space>}><Title level={3}><PriceDisplay product={product} />{product.family !== 'free' && <Text type="secondary"> / 月</Text>}</Title><Text type="secondary">{product.family === 'free' ? '永久免费' : '每次兑换 30 天'}</Text><List size="small" dataSource={product.benefits.slice(0, 10)} renderItem={item => <List.Item><CheckCircleFilled className="check-icon" />{item}</List.Item>} />{product.family === 'free' ? <Button block type="default" disabled>当前免费权益</Button> : <Button block type={product.featured ? 'primary' : 'default'} onClick={() => openPurchase(product)} disabled={!product.purchaseUrl}>{product.purchaseUrl ? '购买 / 兑换' : '商品上线准备中'}</Button>}</Card></Col>)}</Row>{!catalog.products.length && <Empty description="套餐正在准备中" />}</Modal>
    <CloudCatPurchaseModal product={purchaseProduct} open={Boolean(purchaseProduct)} authenticated returnTo="/app?screen=membership" onClose={closePurchase} onRedeemed={() => onRefresh?.()} />
  </div>
}
