import React, { useEffect, useState } from 'react'
import { Button, Card, Col, Empty, Form, List, Modal, Progress, Row, Space, Tag, Typography } from 'antd'
import { CheckCircleFilled, ThunderboltFilled } from '@ant-design/icons'

import { getJson, postJson } from '../api/client'

const { Paragraph, Text, Title } = Typography

const featureNames = {
  official_library_capacity: '官方书架容量', official_unlocks: '官方读物解锁', ai_context_generations: '词汇语境', ai_grammar_generations: '句法分析', mp3_imports: 'MP3 导入', video_imports: '视频导入', youtube_imports: 'YouTube 导入', storage_bytes: '私人空间', devices: '登录设备',
}

function quotaText(key, value) {
  if (key === 'storage_bytes') return `${(Number(value || 0) / 1024 / 1024 / 1024).toFixed(Number(value) >= 10 * 1024 ** 3 ? 0 : 1)} GB`
  return String(value ?? '—')
}

export default function MembershipPage({ membership, membershipOrders, messageApi }) {
  const [plans, setPlans] = useState([])
  const [requests, setRequests] = useState([])
  const [manageOpen, setManageOpen] = useState(false)
  const [submitting, setSubmitting] = useState('')
  const plan = membership?.plan
  const usage = membership?.usage || []
  const ai = usage.find(item => item.feature === 'ai_context_generations')
  const aiPercent = ai?.limit ? Math.min(100, Math.round((ai.used / ai.limit) * 100)) : 0

  const load = async () => {
    const [planData, requestData] = await Promise.all([getJson('/api/membership/plans', { plans: [] }), getJson('/api/membership/requests', { requests: [] })])
    setPlans(planData.plans || [])
    setRequests(requestData.requests || [])
  }
  useEffect(() => { load() }, [])

  const requestPlan = selected => Modal.confirm({
    title: `申请变更为${selected.name}？`,
    content: '申请会提交给平台运营处理。正式支付渠道接入后可直接在此完成付款；当前不会自动扣款。',
    okText: '提交申请',
    onOk: async () => {
      setSubmitting(selected.id)
      try { await postJson('/api/membership/requests', { planVersion: selected.id, note: `用户从 ${plan?.id || 'unknown'} 申请变更` }); await load(); messageApi.success('套餐变更申请已提交') }
      catch (error) { messageApi.error(error.message); throw error }
      finally { setSubmitting('') }
    },
  })

  return <div className="page-stack"><div className="page-intro"><div><Text className="eyebrow">MEMBERSHIP</Text><Title level={1}>会员中心</Title><Paragraph>查看当前权益、对比套餐并提交真实的会员变更申请。</Paragraph></div><Button type="primary" onClick={() => setManageOpen(true)}>管理订阅</Button></div><Card className="membership-hero"><Space align="start"><div className="membership-icon"><ThunderboltFilled /></div><div className="membership-current-copy"><div className="membership-current-line"><Text className="card-kicker">当前方案</Text><Title level={2}>{plan?.name || '未登录或暂无套餐'}</Title></div><Text className="membership-expiry">{membership?.period?.endsAt ? `有效期至 ${new Date(membership.period.endsAt).toLocaleDateString('zh-CN')}` : '登录后读取真实会员周期'}</Text></div></Space><Progress percent={aiPercent} format={() => ai ? `本月 AI 额度 ${ai.available} 可用` : '暂无额度数据'} strokeColor="#f08b67" /></Card><Row gutter={[16, 16]}>{[['内容权益', ['official_unlocks', 'official_library_capacity', 'devices']], ['AI 学习', ['ai_context_generations', 'ai_grammar_generations']], ['导入能力', ['mp3_imports', 'video_imports', 'youtube_imports']]].map(([title, features]) => <Col span={8} key={title}><Card title={title} className="quota-card"><List size="small" dataSource={features} renderItem={feature => { const item = usage.find(value => value.feature === feature); return <List.Item><CheckCircleFilled className="check-icon" />{featureNames[feature]}：{quotaText(feature, item?.available)} 可用</List.Item> }} /></Card></Col>)}</Row><Card title="套餐变更申请"><List size="small" dataSource={requests} locale={{ emptyText: '暂无套餐变更申请' }} renderItem={item => <List.Item><List.Item.Meta title={`${item.currentName || item.currentPlan} → ${item.requestedName || item.requestedPlan}`} description={`${new Date(item.createdAt).toLocaleString('zh-CN')} · ${item.note || '无备注'}`} /><Tag color={item.status === 'pending' ? 'processing' : item.status === 'completed' ? 'success' : 'default'}>{item.status}</Tag></List.Item>} /></Card><Card title="订单记录"><List size="small" dataSource={membershipOrders || []} locale={{ emptyText: '暂无订单记录' }} renderItem={order => <List.Item><List.Item.Meta title={`${order.planVersion} · ${(order.amountCents / 100).toFixed(2)} ${order.currency || 'CNY'}`} description={order.note || '无备注'} /><Tag>{order.status}</Tag></List.Item>} /></Card><Modal width={900} title="选择会员方案" open={manageOpen} onCancel={() => setManageOpen(false)} footer={null}><Row gutter={[16, 16]}>{plans.map(item => <Col span={8} key={item.id}><Card className={`membership-plan-card ${item.id === plan?.id ? 'current' : ''}`} title={<Space>{item.name}{item.id === plan?.id && <Tag color="success">当前方案</Tag>}</Space>}><Title level={3}>{item.pricing?.monthlyCents ? `¥${(item.pricing.monthlyCents / 100).toFixed(0)}` : item.pricing?.amountCents ? `¥${(item.pricing.amountCents / 100).toFixed(0)}` : '联系运营'}</Title><Text type="secondary">{item.periodDays} 天权益周期</Text><List size="small" dataSource={Object.entries(item.quotas || {}).slice(0, 8)} renderItem={([key, value]) => <List.Item><CheckCircleFilled className="check-icon" />{featureNames[key] || key}：{quotaText(key, value)}</List.Item>} /><Button block type={item.rank > Number(plan?.rank || 0) ? 'primary' : 'default'} disabled={item.id === plan?.id || requests.some(request => request.status === 'pending')} loading={submitting === item.id} onClick={() => requestPlan(item)}>{item.rank > Number(plan?.rank || 0) ? '申请升级' : '申请变更'}</Button></Card></Col>)}</Row>{!plans.length && <Empty description="暂无可用套餐" />}</Modal></div>
}
