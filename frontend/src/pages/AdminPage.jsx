import React, { useEffect, useMemo, useState } from 'react'
import dayjs from 'dayjs'
import { Button, Card, Col, DatePicker, Descriptions, Drawer, Dropdown, Empty, Form, Input, InputNumber, List, Modal, Pagination, Row, Segmented, Select, Skeleton, Space, Table, Tag, Typography } from 'antd'
import { FileTextOutlined, PlusOutlined } from '@ant-design/icons'

import { getJson } from '../api/client'

const { Paragraph, Text, Title } = Typography
const { RangePicker } = DatePicker

const durations = { week: 7, month: 30, quarter: 90, year: 365 }

export default function AdminPage({ adminData, onUpdateUserStatus, onCreateInvitation, onRevokeDevice, onAdjustQuota, onUpdateSubscription, onCreateManualOrder, onExportAdminSummary }) {
  const [detailOpen, setDetailOpen] = useState(false)
  const [detail, setDetail] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [orderOpen, setOrderOpen] = useState(false)
  const [inviteOpen, setInviteOpen] = useState(false)
  const [inviteQuery, setInviteQuery] = useState('')
  const [invitePage, setInvitePage] = useState(1)
  const [inviteData, setInviteData] = useState({ invitations: adminData?.invitations || [], total: adminData?.invitations?.length || 0 })
  const [auditQuery, setAuditQuery] = useState('')
  const [auditItems, setAuditItems] = useState(adminData?.audit || [])
  const [duration, setDuration] = useState('month')
  const [orderForm] = Form.useForm()
  const [inviteForm] = Form.useForm()
  const [quotaForm] = Form.useForm()
  const users = adminData?.users || []
  const dashboard = adminData?.dashboard
  const invitePageSize = 6

  const loadInvitations = async () => {
    const params = new URLSearchParams({ limit: String(invitePageSize), offset: String((invitePage - 1) * invitePageSize) })
    if (inviteQuery.trim()) params.set('q', inviteQuery.trim())
    setInviteData(await getJson(`/api/admin/invitations?${params}`, { invitations: [], total: 0 }))
  }
  useEffect(() => { const timer = setTimeout(loadInvitations, 180); return () => clearTimeout(timer) }, [invitePage, inviteQuery, adminData?.invitations])
  useEffect(() => { const timer = setTimeout(() => { const params = new URLSearchParams({ limit: '100' }); if (auditQuery.trim()) params.set('q', auditQuery.trim()); getJson(`/api/admin/audit?${params}`, { items: [] }).then(data => setAuditItems(data.items || [])) }, 180); return () => clearTimeout(timer) }, [auditQuery, adminData?.audit])

  const openDetail = async user => {
    setDetailOpen(true); setDetailLoading(true)
    try { setDetail(await getJson(`/api/admin/users/${encodeURIComponent(user.id)}`)) }
    catch (error) { setDetail({ error: error.message }) }
    finally { setDetailLoading(false) }
  }
  const selectDuration = value => {
    setDuration(value)
    const start = dayjs().startOf('minute')
    orderForm.setFieldValue('period', [start, start.add(durations[value], 'day')])
  }
  const openOrder = () => {
    setDuration('month')
    const start = dayjs().startOf('minute')
    orderForm.setFieldsValue({ duration: 'month', period: [start, start.add(30, 'day')], amountCents: 0 })
    setOrderOpen(true)
  }
  const submitOrder = async values => {
    const [startsAt, endsAt] = values.period || []
    await onCreateManualOrder?.({ userId: values.userId, planVersion: values.planVersion, startsAt: startsAt?.toISOString(), endsAt: endsAt?.toISOString(), note: values.note || `运营后台创建 ${duration} 订阅`, amountCents: Number(values.amountCents || 0) })
    orderForm.resetFields(); setOrderOpen(false)
  }
  const submitInvite = async values => {
    await onCreateInvitation?.({ code: values.code?.trim() || '', count: Number(values.count || 1), maxUses: Number(values.maxUses || 1), expiresAt: values.expiresAt?.toISOString(), note: values.note?.trim() || '运营后台创建', channel: 'admin' })
    inviteForm.resetFields(); setInviteOpen(false); setInvitePage(1); await loadInvitations()
  }

  const columns = [
    { title: '用户', dataIndex: 'email', render: (value, row) => <Space direction="vertical" size={0}><Text strong>{row.displayName || '未设置昵称'}</Text><Text type="secondary">{value}</Text></Space> },
    { title: '方案', dataIndex: 'planVersion', render: value => <Tag color="green">{value}</Tag> },
    { title: '设备', dataIndex: 'devices' },
    { title: '状态', dataIndex: 'status', render: value => <Tag color={value === 'active' ? 'success' : 'warning'}>{value}</Tag> },
    { title: '邮箱', dataIndex: 'emailVerified', render: value => value ? <Tag color="success">已验证</Tag> : <Tag>待验证</Tag> },
    { title: '操作', fixed: 'right', render: (_, row) => <Dropdown menu={{ items: [{ key: 'detail', label: '查看详情' }, row.status === 'active' ? { key: 'suspended', label: '暂停账号', danger: true } : { key: 'active', label: '恢复账号' }], onClick: ({ key }) => key === 'detail' ? openDetail(row) : onUpdateUserStatus?.(row, key) }}><Button type="link">管理</Button></Dropdown> },
  ]
  const count = key => dashboard?.users?.[key] ?? '—'
  const detailDrawer = <Drawer title="用户详情" open={detailOpen} onClose={() => setDetailOpen(false)} width={620}>{detailLoading ? <Space direction="vertical" size={16} style={{ width: '100%' }}><Card><Skeleton active paragraph={{ rows: 4 }} /></Card><Card><Skeleton active paragraph={{ rows: 3 }} /></Card><Card><Skeleton active paragraph={{ rows: 3 }} /></Card></Space> : detail?.error ? <Empty description={detail.error} /> : detail && <Space direction="vertical" size={16} style={{ width: '100%' }}><Descriptions bordered column={1} size="small"><Descriptions.Item label="邮箱">{detail.user?.email}</Descriptions.Item><Descriptions.Item label="状态">{detail.user?.status}</Descriptions.Item><Descriptions.Item label="套餐">{detail.user?.planVersion}</Descriptions.Item><Descriptions.Item label="成长值">{detail.growthBalance || 0}</Descriptions.Item></Descriptions><Card size="small" title="登录设备"><List dataSource={detail.devices || []} renderItem={device => <List.Item actions={!device.revoked ? [<Button key="revoke" danger size="small" onClick={() => onRevokeDevice?.(detail.user.id, device.id)}>撤销</Button>] : []}><List.Item.Meta title={device.label || '未命名设备'} description={device.userAgent} /><Tag>{device.revoked ? '已撤销' : '活跃'}</Tag></List.Item>} /></Card><Card size="small" title="订阅记录"><List dataSource={detail.subscriptions || []} locale={{ emptyText: '暂无订阅' }} renderItem={item => <List.Item><List.Item.Meta title={`${item.planVersion} · ${item.status}`} description={`${new Date(item.startsAt).toLocaleDateString('zh-CN')} 至 ${new Date(item.endsAt).toLocaleDateString('zh-CN')}`} /></List.Item>} /></Card><Card size="small" title="额度调整"><Form form={quotaForm} layout="inline" onFinish={async values => { await onAdjustQuota?.(detail.user.id, { feature: values.feature, quantity: Number(values.quantity), reason: values.reason }); quotaForm.resetFields() }}><Form.Item name="feature" rules={[{ required: true }]}><Select placeholder="额度类型" style={{ width: 180 }} options={['official_unlocks', 'ai_context_generations', 'ai_grammar_generations', 'mp3_imports', 'video_imports', 'youtube_imports'].map(value => ({ value, label: value }))} /></Form.Item><Form.Item name="quantity" rules={[{ required: true }]}><InputNumber placeholder="数量" /></Form.Item><Form.Item name="reason" rules={[{ required: true }]}><Input placeholder="调整原因" /></Form.Item><Button htmlType="submit">确认</Button></Form></Card></Space>}</Drawer>

  return <div className="page-stack">
    <div className="page-intro"><div><Text className="eyebrow">OPERATIONS</Text><Title level={1}>运营后台</Title><Paragraph>用户、订阅、邀请码与审计操作的商业工作区。</Paragraph></div><Space><Button icon={<FileTextOutlined />} onClick={onExportAdminSummary}>导出数据</Button><Button onClick={openOrder}>创建人工订阅</Button><Button type="primary" icon={<PlusOutlined />} onClick={() => setInviteOpen(true)}>创建邀请码</Button></Space></div>
    <Row gutter={[16, 16]}><Col span={6}><Card><Text>用户总数</Text><Title level={2}>{count('total')}</Title><Text type="secondary">活跃 {count('active')} 人</Text></Card></Col><Col span={6}><Card><Text>已验证用户</Text><Title level={2}>{count('verified')}</Title><Text type="secondary">暂停 {count('suspended')} 人</Text></Card></Col><Col span={6}><Card><Text>有效订阅</Text><Title level={2}>{dashboard?.activeSubscriptions ?? '—'}</Title><Text type="secondary">邀请码 {dashboard?.activeInvitations ?? '—'}</Text></Card></Col><Col span={6}><Card><Text>书城内容</Text><Title level={2}>{dashboard?.catalog?.published ?? '—'}</Title><Text type="secondary">总内容 {dashboard?.catalog?.total ?? '—'} 本</Text></Card></Col></Row>
    <Card title="用户与订阅"><Table rowKey="id" columns={columns} dataSource={users} pagination={{ pageSize: 8 }} scroll={{ x: 860 }} /></Card>
    <Row gutter={[20, 20]}><Col span={12}><Card title="最近邀请码" extra={<Input.Search allowClear size="small" placeholder="查询邀请码、备注或渠道" value={inviteQuery} onChange={event => { setInviteQuery(event.target.value); setInvitePage(1) }} style={{ width: 230 }} />}><List dataSource={inviteData.invitations || []} locale={{ emptyText: '暂无邀请码' }} renderItem={item => <List.Item actions={[<Button key="copy" size="small" onClick={() => navigator.clipboard?.writeText(item.code)}>复制</Button>]}><List.Item.Meta title={<Text code>{item.code}</Text>} description={`${item.usedCount}/${item.maxUses} 次 · 激活邮件 ${item.verificationEmailCount || 0}/${item.verificationEmailLimit || 3} · ${item.status} · ${item.note || '无备注'}`} /></List.Item>} />{inviteData.total > invitePageSize && <Pagination size="small" current={invitePage} pageSize={invitePageSize} total={inviteData.total} showSizeChanger={false} onChange={setInvitePage} />}</Card></Col><Col span={12}><Card title="最近审计操作" extra={<Input.Search allowClear size="small" placeholder="搜索操作" value={auditQuery} onChange={event => setAuditQuery(event.target.value)} style={{ width: 200 }} />}><List dataSource={auditItems.slice(0, 10)} locale={{ emptyText: '暂无审计记录' }} renderItem={item => <List.Item><List.Item.Meta title={item.action} description={`${item.actor || '系统'} · ${item.reason || '未填写原因'}`} /><Text type="secondary">{item.createdAt ? new Date(item.createdAt).toLocaleString('zh-CN') : '—'}</Text></List.Item>} /></Card></Col></Row>
    {detailDrawer}
    <Modal width={680} title="创建人工订阅" open={orderOpen} onCancel={() => setOrderOpen(false)} onOk={() => orderForm.submit()} okText="创建订阅"><Form form={orderForm} layout="vertical" onFinish={submitOrder}><Form.Item label="用户" name="userId" rules={[{ required: true, message: '请选择用户' }]}><Select showSearch optionFilterProp="label" options={users.map(user => ({ value: user.id, label: `${user.displayName || '未设置昵称'} · ${user.email}` }))} /></Form.Item><Form.Item label="套餐" name="planVersion" rules={[{ required: true, message: '请选择套餐' }]}><Select options={(adminData?.planVersions || []).map(plan => ({ value: plan.id, label: `${plan.name} (${plan.id})` }))} /></Form.Item><Form.Item label="快捷时长" name="duration"><Segmented block value={duration} onChange={selectDuration} options={[{ label: '1 周', value: 'week' }, { label: '1 月', value: 'month' }, { label: '1 季度', value: 'quarter' }, { label: '1 年', value: 'year' }]} /></Form.Item><Form.Item label="开始与结束时间" name="period" rules={[{ required: true, message: '请选择订阅时间段' }]}><RangePicker showTime style={{ width: '100%' }} /></Form.Item><Form.Item label="金额（分）" name="amountCents"><InputNumber min={0} style={{ width: '100%' }} /></Form.Item><Form.Item label="备注" name="note"><Input.TextArea rows={3} /></Form.Item></Form></Modal>
    <Modal title="创建邀请码" open={inviteOpen} onCancel={() => setInviteOpen(false)} onOk={() => inviteForm.submit()} okText="生成邀请码"><Form form={inviteForm} layout="vertical" onFinish={submitInvite}><Form.Item label="指定邀请码（可选）" name="code" extra="留空由后台自动生成；指定邀请码时只能生成一个。"><Input placeholder="留空自动生成" /></Form.Item><Row gutter={12}><Col span={12}><Form.Item label="生成数量" name="count" initialValue={1} rules={[{ required: true }]}><InputNumber min={1} max={100} style={{ width: '100%' }} /></Form.Item></Col><Col span={12}><Form.Item label="每个码可使用次数" name="maxUses" initialValue={1} rules={[{ required: true }]}><InputNumber min={1} max={1000000} style={{ width: '100%' }} /></Form.Item></Col></Row><Form.Item label="过期时间（可选）" name="expiresAt"><DatePicker showTime style={{ width: '100%' }} /></Form.Item><Form.Item label="备注" name="note" initialValue="运营后台创建"><Input.TextArea rows={3} /></Form.Item></Form></Modal>
  </div>
}
