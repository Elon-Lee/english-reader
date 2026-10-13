import React, { useEffect, useState } from 'react'
import { Alert, Button, Card, Col, Empty, List, Modal, Progress, Row, Space, Tag, Typography } from 'antd'
import { CheckCircleFilled, ThunderboltFilled } from '@ant-design/icons'

import { getJson } from '../api/client'

const { Paragraph, Text, Title } = Typography

const featureNames = {
  official_library_capacity: '官方书架容量', official_unlocks: '公版及授权材料使用', ai_context_generations: '词汇语境分析', ai_grammar_generations: '句法分析', mp3_imports: 'MP3 学习导入', video_imports: '视频学习导入', youtube_imports: '在线视频学习导入', storage_bytes: '私人学习空间', devices: '登录设备',
}

function quotaText(key, value) {
  if (key === 'storage_bytes') return `${(Number(value || 0) / 1024 / 1024 / 1024).toFixed(Number(value) >= 10 * 1024 ** 3 ? 0 : 1)} GB`
  return String(value ?? '—')
}

function money(cents) { return `¥${(Number(cents || 0) / 100).toFixed(0)}` }

export default function MembershipPage({ membership, membershipOrders }) {
  const [catalog, setCatalog] = useState({ products: [], payment: {}, support: { value: '289614546' } })
  const [manageOpen, setManageOpen] = useState(false)
  const plan = membership?.plan
  const usage = membership?.usage || []
  const ai = usage.find(item => item.feature === 'ai_context_generations')
  const aiPercent = ai?.limit ? Math.min(100, Math.round((ai.used / ai.limit) * 100)) : 0
  useEffect(() => { getJson('/api/commerce/products', { products: [], payment: {}, support: { value: '289614546' } }).then(setCatalog) }, [])

  return <div className="page-stack">
    <div className="page-intro"><div><Text className="eyebrow">MEMBERSHIP</Text><Title level={1}>会员中心</Title><Paragraph>查看当前权益、选择固定期限方案并管理历史订单。所有在线套餐均为单次购买，不自动续费。</Paragraph></div><Space><Button href="/pricing">公开套餐页</Button><Button type="primary" onClick={() => setManageOpen(true)}>续费或升级</Button></Space></div>
    {!catalog.payment?.configured && <Alert showIcon type="info" message="在线支付正在开通" description={<>套餐和订单流程已经就绪，支付渠道审核完成后开放付款。如需提前开通，请联系 QQ {catalog.support?.value || '289614546'}。</>} />}
    <Card className="membership-hero"><Space align="start"><div className="membership-icon"><ThunderboltFilled /></div><div className="membership-current-copy"><div className="membership-current-line"><Text className="card-kicker">当前方案</Text><Title level={2}>{plan?.name || '未登录或暂无套餐'}</Title></div><Text className="membership-expiry">{membership?.period?.endsAt ? `当前权益有效期至 ${new Date(membership.period.endsAt).toLocaleDateString('zh-CN')}` : '登录后读取真实会员周期'}</Text></div></Space><Progress percent={aiPercent} format={() => ai ? `本周期 AI 额度 ${ai.available} 可用` : '暂无额度数据'} strokeColor="#f08b67" /></Card>
    <Row gutter={[16, 16]}>{[['内容权益', ['official_unlocks', 'official_library_capacity', 'devices']], ['AI 学习', ['ai_context_generations', 'ai_grammar_generations']], ['导入能力', ['mp3_imports', 'video_imports', 'youtube_imports']]].map(([title, features]) => <Col span={8} key={title}><Card title={title} className="quota-card"><List size="small" dataSource={features} renderItem={feature => { const item = usage.find(value => value.feature === feature); return <List.Item><CheckCircleFilled className="check-icon" />{featureNames[feature]}：{quotaText(feature, item?.available)} 可用</List.Item> }} /></Card></Col>)}</Row>
    <Card title="订单记录"><List size="small" dataSource={membershipOrders || []} locale={{ emptyText: '暂无订单记录' }} renderItem={order => <List.Item><List.Item.Meta title={`${order.planVersion} · ${(order.amountCents / 100).toFixed(2)} ${order.currency || 'CNY'}`} description={`${order.provider === 'mbdpay' ? '面包多 Pay' : order.provider === 'paddle' ? '历史 Paddle 测试订单' : '人工订单'} · ${order.note || '无备注'}`} /><Tag color={order.status === 'paid' || order.status === 'completed' ? 'success' : order.status === 'pending' ? 'processing' : order.status === 'failed' ? 'error' : 'default'}>{order.status}</Tag></List.Item>} /></Card>
    <Modal width={980} title="选择固定期限学习方案" open={manageOpen} onCancel={() => setManageOpen(false)} footer={null}><Alert showIcon type="success" message="单次购买，不自动续费" description="到期前会提醒你，由你决定是否继续。提前续费同一方案时，从当前到期日顺延。" /><Row gutter={[16, 16]} style={{ marginTop: 18 }}>{catalog.products.map(product => <Col xs={24} md={12} xl={6} key={product.id}><Card className={`membership-plan-card ${product.featured ? 'current' : ''}`} title={<Space>{product.shortName}{product.featured && <Tag color="success">推荐</Tag>}</Space>}><Title level={3}>{money(product.amountCents)}</Title><Text type="secondary">{product.durationDays} 天固定期限</Text><List size="small" dataSource={product.benefits.slice(0, 7)} renderItem={item => <List.Item><CheckCircleFilled className="check-icon" />{item}</List.Item>} /><Button block type={product.featured ? 'primary' : 'default'} href={`/purchase/${product.slug}`}>查看并确认购买</Button></Card></Col>)}</Row>{!catalog.products.length && <Empty description="暂无可售套餐" />}</Modal>
  </div>
}
