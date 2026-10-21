import React, { useEffect, useState } from 'react'
import dayjs from 'dayjs'
import { Button, Card, Col, DatePicker, Descriptions, Drawer, Dropdown, Empty, Form, Input, InputNumber, List, Modal, Pagination, Row, Segmented, Select, Skeleton, Space, Table, Tabs, Tag, Typography } from 'antd'
import { BookOutlined, CheckCircleOutlined, CrownOutlined, FileTextOutlined, PlusOutlined, TeamOutlined } from '@ant-design/icons'

import { getJson, postJson } from '../api/client'
import BenefitAdmin from '../components/BenefitAdmin'
import CatalogModeration from '../components/CatalogModeration'
import MediaAssetsAdmin from '../components/MediaAssetsAdmin'
import CommerceAdmin from '../components/CommerceAdmin'
import RedemptionAdmin from '../components/RedemptionAdmin'
import { PaymentMethodSettings, PaymentOrdersAdmin, RedemptionRecordsAdmin } from '../components/PaymentOperations'
import JourneyReport from '../components/JourneyReport'

const { Paragraph, Text, Title } = Typography
const { RangePicker } = DatePicker
const durations = { week: 7, month: 30, quarter: 90, year: 365 }

export default function AdminPage({ messageApi, adminData, onUpdateUserStatus, onVerifyUser, onDeleteUnverifiedUser, onCreateInvitation, onDeleteUnusedInvitations, onRevokeDevice, onAdjustQuota, onUpdateSubscription, onCreateManualOrder, onCreateCommerceProduct, onCreateCommerceVersion, onPublishCommerceVersion, onSetCommerceProductActive, onDeleteCommerceProduct, onCreateConfiguredBenefit, onUpdateConfiguredBenefit, onExportAdminSummary }) {
  const [activeTab, setActiveTab] = useState(() => new URLSearchParams(location.search).get('adminTab') === 'catalog' ? 'catalog' : 'overview')
  const [detailOpen, setDetailOpen] = useState(false)
  const [detail, setDetail] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [orderOpen, setOrderOpen] = useState(false)
  const [inviteOpen, setInviteOpen] = useState(false)
  const [inviteQuery, setInviteQuery] = useState('')
  const [invitePage, setInvitePage] = useState(1)
  const [inviteData, setInviteData] = useState({ batches: [], total: 0 })
  const [inviteDetail, setInviteDetail] = useState(null)
  const [inviteDetailLoading, setInviteDetailLoading] = useState(false)
  const [selectedInvitationIds, setSelectedInvitationIds] = useState([])
  const [auditQuery, setAuditQuery] = useState('')
  const [auditAction, setAuditAction] = useState('')
  const [auditPage, setAuditPage] = useState(1)
  const [auditTotal, setAuditTotal] = useState(0)
  const [auditActions, setAuditActions] = useState([])
  const [auditLoading, setAuditLoading] = useState(false)
  const [auditError, setAuditError] = useState('')
  const [auditRefreshKey, setAuditRefreshKey] = useState(0)
  const [auditItems, setAuditItems] = useState(adminData?.audit || [])
  const [duration, setDuration] = useState('month')
  const [orderForm] = Form.useForm(), [inviteForm] = Form.useForm(), [quotaForm] = Form.useForm()
  const users = adminData?.users || [], dashboard = adminData?.dashboard, invitePageSize = 8

  const loadInvitations = async () => {
    const params = new URLSearchParams({ limit: String(invitePageSize), offset: String((invitePage - 1) * invitePageSize) })
    if (inviteQuery.trim()) params.set('q', inviteQuery.trim())
    setInviteData(await getJson(`/api/admin/invitation-batches?${params}`, { batches: [], total: 0 }))
  }
  useEffect(() => { if (activeTab !== 'invites') return undefined; const timer = setTimeout(loadInvitations, 180); return () => clearTimeout(timer) }, [activeTab, invitePage, inviteQuery])
  useEffect(() => { if (activeTab !== 'audit') return undefined; const timer = setTimeout(async () => { setAuditLoading(true); setAuditError(''); const params = new URLSearchParams({ limit: '20', offset: String((auditPage - 1) * 20) }); if (auditQuery.trim()) params.set('q', auditQuery.trim()); if (auditAction) params.set('action', auditAction); try { const data = await getJson(`/api/admin/audit?${params}`); setAuditItems(data.items || []); setAuditTotal(data.total || 0); setAuditActions(data.actions || []) } catch (error) { setAuditError(error.message || '审计记录加载失败') } finally { setAuditLoading(false) } }, 180); return () => clearTimeout(timer) }, [activeTab, auditQuery, auditAction, auditPage, auditRefreshKey])

  const openDetail = async user => { setDetailOpen(true); setDetailLoading(true); try { setDetail(await getJson(`/api/admin/users/${encodeURIComponent(user.id)}`)) } catch (error) { setDetail({ error: error.message }) } finally { setDetailLoading(false) } }
  const selectDuration = value => { setDuration(value); const start = dayjs().startOf('minute'); orderForm.setFieldValue('period', [start, start.add(durations[value], 'day')]) }
  const openOrder = () => { setDuration('month'); const start = dayjs().startOf('minute'); orderForm.setFieldsValue({ duration: 'month', period: [start, start.add(30, 'day')], amountCents: 0 }); setOrderOpen(true) }
  const submitOrder = async values => { const [startsAt, endsAt] = values.period || []; await onCreateManualOrder?.({ userId: values.userId, planVersion: values.planVersion, startsAt: startsAt?.toISOString(), endsAt: endsAt?.toISOString(), note: values.note || `运营后台创建 ${duration} 订阅`, amountCents: Number(values.amountCents || 0) }); orderForm.resetFields(); setOrderOpen(false) }
  const submitInvite = async values => { const result = await onCreateInvitation?.({ code: values.code?.trim() || '', count: Number(values.count || 1), maxUses: Number(values.maxUses || 1), expiresAt: values.expiresAt?.toISOString(), note: values.note?.trim() || '运营后台创建', channel: 'admin' }); inviteForm.resetFields(); setInviteOpen(false); setInvitePage(1); await loadInvitations(); if (result?.batch?.id) openInvitationBatch(result.batch.id) }
  const openInvitationBatch = async batchId => { setInviteDetailLoading(true); setInviteDetail({ batch: { id: batchId }, invitations: [] }); setSelectedInvitationIds([]); try { setInviteDetail(await getJson(`/api/admin/invitation-batches/${encodeURIComponent(batchId)}`)) } finally { setInviteDetailLoading(false) } }
  const deleteSelectedInvitations = () => Modal.confirm({ title: `删除 ${selectedInvitationIds.length} 个未使用邀请码？`, content: '删除后邀请码立即失效且不可恢复；已使用或关联邀请奖励的邀请码不会出现在可选范围。', okText: '确认删除', cancelText: '取消', okButtonProps: { danger: true }, onOk: async () => { const result = await onDeleteUnusedInvitations?.(inviteDetail.batch.id, selectedInvitationIds); setSelectedInvitationIds([]); await loadInvitations(); if (result?.batchDeleted) setInviteDetail(null); else await openInvitationBatch(inviteDetail.batch.id) } })

  const columns = [
    { title: '用户', dataIndex: 'email', render: (value, row) => <Space direction="vertical" size={0}><Text strong>{row.displayName || '未设置昵称'}</Text><Text type="secondary">{value}</Text></Space> },
    { title: '方案', dataIndex: 'planVersion', render: value => <Tag color="green">{value}</Tag> }, { title: '设备', dataIndex: 'devices' },
    { title: '状态', dataIndex: 'status', render: value => <Tag color={value === 'active' ? 'success' : value === 'deleted' ? 'default' : 'warning'}>{{ active: '正常', suspended: '已暂停', deleted: '已删除' }[value] || value}</Tag> },
    { title: '邮箱', dataIndex: 'emailVerified', render: value => value ? <Tag color="success">已验证</Tag> : <Tag>待验证</Tag> },
    { title: '操作', fixed: 'right', render: (_, row) => <Dropdown menu={{ items: [{ key: 'detail', label: '查看详情' }, ...(!row.emailVerified && row.status !== 'deleted' ? [{ key: 'verify', label: '标记已验证' }, { key: 'delete', label: '删除待验证账号', danger: true }] : []), ...(row.status === 'active' ? [{ key: 'suspended', label: '暂停账号', danger: true }] : row.status === 'suspended' ? [{ key: 'active', label: '恢复账号' }] : [])], onClick: ({ key }) => key === 'detail' ? openDetail(row) : key === 'verify' ? Modal.confirm({ title: `将 ${row.email} 标记为已验证？`, content: '该操作会跳过邮箱验证流程并立即开放账号。', okText: '确认验证', cancelText: '取消', onOk: () => onVerifyUser?.(row) }) : key === 'delete' ? Modal.confirm({ title: `删除待验证账号 ${row.email}？`, content: '账号将被停用并匿名化，登录会话和验证链接会失效，相关历史记录会保留。此操作不可撤销。', okText: '删除账号', cancelText: '取消', okButtonProps: { danger: true }, onOk: () => onDeleteUnverifiedUser?.(row) }) : onUpdateUserStatus?.(row, key) }}><Button>管理</Button></Dropdown> },
  ]
  const count = key => dashboard?.users?.[key] ?? '—'
  const metricItems = [
    { label: '用户总数', value: count('total'), note: `活跃 ${count('active')} 人`, icon: <TeamOutlined />, tone: 'green' },
    { label: '已验证用户', value: count('verified'), note: `暂停 ${count('suspended')} 人`, icon: <CheckCircleOutlined />, tone: 'blue' },
    { label: '有效订阅', value: dashboard?.activeSubscriptions ?? '—', note: `有效邀请码 ${dashboard?.activeInvitations ?? '—'}`, icon: <CrownOutlined />, tone: 'orange' },
    { label: '书城内容', value: dashboard?.catalog?.published ?? '—', note: `总内容 ${dashboard?.catalog?.total ?? '—'} 本`, icon: <BookOutlined />, tone: 'purple' },
  ]
  const metrics = <Row gutter={[16, 16]}>{metricItems.map(item => <Col span={6} key={item.label}><Card className="admin-metric-card"><div className={`admin-metric-icon ${item.tone}`}>{item.icon}</div><div><Text>{item.label}</Text><Title level={2}>{item.value}</Title><Text type="secondary">{item.note}</Text></div></Card></Col>)}</Row>

  const invitationColumns = [
    { title: '创建记录', key: 'summary', render: (_, row) => <Space direction="vertical" size={1}><Text strong>{row.note || '邀请码批次'}</Text><Text type="secondary">{new Date(row.createdAt).toLocaleString('zh-CN')} · {row.channel || '未标记渠道'}</Text></Space> },
    { title: '邀请码', dataIndex: 'count', width: 100, render: (value, row) => `${value}/${row.requestedCount} 个` },
    { title: '使用情况', key: 'usage', width: 255, render: (_, row) => <Space size={[0, 4]} wrap><Tag color="success">未使用 {row.unusedCount}</Tag><Tag>已使用 {row.usedCount}</Tag>{row.expiredCount > 0 && <Tag color="error">已过期 {row.expiredCount}</Tag>}</Space> },
    { title: '单码次数', dataIndex: 'maxUses', width: 100, render: value => `${value} 次` },
    { title: '操作', width: 90, render: (_, row) => <Button onClick={() => openInvitationBatch(row.id)}>详情</Button> },
  ]
  const invitationDetailColumns = [
    { title: '邀请码', dataIndex: 'code', render: value => <Text code>{value}</Text> },
    { title: '状态', key: 'status', width: 105, render: (_, row) => <Tag color={row.usageStatus === 'expired' ? 'error' : row.usedCount ? 'default' : 'success'}>{row.usedCount ? '已使用' : row.usageStatus === 'expired' ? '已过期' : '未使用'}</Tag> },
    { title: '使用次数', key: 'uses', width: 110, render: (_, row) => `${row.usedCount}/${row.maxUses}` },
    { title: '注册邮箱', key: 'emails', render: (_, row) => row.uses?.length ? row.uses.map(item => item.email).join('、') : '—' },
    { title: '操作', width: 80, render: (_, row) => <Button size="small" onClick={() => navigator.clipboard?.writeText(row.code)}>复制</Button> },
  ]

  const detailDrawer = <Drawer title="用户详情" open={detailOpen} onClose={() => setDetailOpen(false)} width={660}>{detailLoading ? <Skeleton active paragraph={{ rows: 10 }} /> : detail?.error ? <Empty description={detail.error} /> : detail && <Space direction="vertical" size={16} style={{ width: '100%' }}><Descriptions bordered column={1} size="small"><Descriptions.Item label="邮箱">{detail.user?.email}</Descriptions.Item><Descriptions.Item label="状态">{detail.user?.status}</Descriptions.Item><Descriptions.Item label="套餐">{detail.user?.planVersion}</Descriptions.Item><Descriptions.Item label="成长值">{detail.growthBalance || 0}</Descriptions.Item></Descriptions><Card size="small" title="登录设备"><List dataSource={detail.devices || []} renderItem={device => <List.Item actions={!device.revoked ? [<Button key="revoke" danger size="small" onClick={() => onRevokeDevice?.(detail.user.id, device.id)}>撤销</Button>] : []}><List.Item.Meta title={device.label || '未命名设备'} description={device.userAgent} /><Tag>{device.revoked ? '已撤销' : '活跃'}</Tag></List.Item>} /></Card><Card size="small" title="订阅记录"><List dataSource={detail.subscriptions || []} locale={{ emptyText: '暂无订阅' }} renderItem={item => <List.Item><List.Item.Meta title={`${item.planVersion} · ${item.status}`} description={`${new Date(item.startsAt).toLocaleDateString('zh-CN')} 至 ${new Date(item.endsAt).toLocaleDateString('zh-CN')}`} /></List.Item>} /></Card><Card size="small" title="额度调整"><Form form={quotaForm} layout="inline" onFinish={async values => { await onAdjustQuota?.(detail.user.id, { feature: values.feature, quantity: Number(values.quantity), reason: values.reason }); quotaForm.resetFields() }}><Form.Item name="feature" rules={[{ required: true }]}><Select placeholder="额度类型" style={{ width: 190 }} options={(adminData?.commerceEntitlements?.builtIn || []).map(item => ({ value: item.key, label: item.name }))} /></Form.Item><Form.Item name="quantity" rules={[{ required: true }]}><InputNumber placeholder="数量" /></Form.Item><Form.Item name="reason" rules={[{ required: true }]}><Input placeholder="调整原因" /></Form.Item><Button htmlType="submit">确认</Button></Form></Card></Space>}</Drawer>

  const removeExpiredInvitations = () => Modal.confirm({ title: '删除所有可清理的过期邀请码？', content: '仅删除过期、未使用且没有邀请奖励关联的邀请码，并写入审计记录。', okText: '删除过期码', cancelText: '取消', okButtonProps: { danger: true }, onOk: async () => { try { const result = await postJson('/api/admin/invitations/delete-expired', {}); messageApi.success(`已删除 ${result.deleted || 0} 个过期邀请码`); await loadInvitations() } catch (error) { messageApi.error(error.message || '清理过期邀请码失败'); throw error } } })

  const tabItems = [
    { key: 'overview', label: '概览', children: <Space direction="vertical" size={20} style={{ width: '100%' }}>{metrics}<JourneyReport /><Card title="快捷操作"><Space wrap><Button type="primary" onClick={() => setActiveTab('plans')}>管理套餐</Button><Button onClick={openOrder}>创建人工订阅</Button><Button onClick={() => setInviteOpen(true)}>创建邀请码</Button><Button icon={<FileTextOutlined />} onClick={onExportAdminSummary}>导出数据</Button></Space></Card></Space> },
    { key: 'media', label: '媒体资产', children: activeTab === 'media' ? <MediaAssetsAdmin messageApi={messageApi} /> : null },
    { key: 'catalog', label: '内容管理', children: activeTab === 'catalog' ? <CatalogModeration messageApi={messageApi} /> : null },
    { key: 'plans', label: '套餐管理', children: <Card><CommerceAdmin products={adminData?.commerceProducts || []} entitlements={adminData?.commerceEntitlements || { builtIn: [], configured: [] }} onCreateProduct={onCreateCommerceProduct} onCreateVersion={onCreateCommerceVersion} onPublishVersion={onPublishCommerceVersion} onSetProductActive={onSetCommerceProductActive} onDeleteProduct={onDeleteCommerceProduct} /></Card> },
    { key: 'redemptions', label: '兑换码库存', children: <RedemptionAdmin products={adminData?.commerceProducts || []} /> },
    { key: 'redemption-records', label: '兑换记录', children: activeTab === 'redemption-records' ? <RedemptionRecordsAdmin /> : null },
    { key: 'payment-settings', label: '支付方式', children: activeTab === 'payment-settings' ? <PaymentMethodSettings /> : null },
    { key: 'payment-orders', label: '支付宝订单', children: activeTab === 'payment-orders' ? <PaymentOrdersAdmin /> : null },
    { key: 'benefits', label: '套餐内容', children: <BenefitAdmin entitlements={adminData?.commerceEntitlements || { builtIn: [], configured: [] }} onCreate={onCreateConfiguredBenefit} onUpdate={onUpdateConfiguredBenefit} /> },
    { key: 'users', label: '用户与订阅', children: <Card title="用户与订阅" extra={<Button onClick={openOrder}>创建人工订阅</Button>}><Table rowKey="id" columns={columns} dataSource={users} pagination={{ pageSize: 8 }} scroll={{ x: 860 }} /></Card> },
    { key: 'invites', label: '邀请码', children: <Card title="邀请码创建记录" extra={<Space wrap><Input.Search allowClear placeholder="搜索批次备注、渠道或邀请码" value={inviteQuery} onChange={event => { setInviteQuery(event.target.value); setInvitePage(1) }} style={{ width: 290 }} /><Button danger onClick={removeExpiredInvitations}>删除过期邀请码</Button><Button type="primary" icon={<PlusOutlined />} onClick={() => setInviteOpen(true)}>创建邀请码</Button></Space>}><Table rowKey="id" columns={invitationColumns} dataSource={inviteData.batches || []} pagination={false} locale={{ emptyText: <Empty description="暂无邀请码创建记录" /> }} />{inviteData.total > invitePageSize && <Pagination className="admin-invite-pagination" current={invitePage} pageSize={invitePageSize} total={inviteData.total} showSizeChanger={false} onChange={setInvitePage} />}</Card> },
    { key: 'audit', label: '审计记录', children: <Card title="审计记录" extra={<Space wrap><Input.Search allowClear placeholder="搜索操作、原因或邮箱" value={auditQuery} onChange={event => { setAuditQuery(event.target.value); setAuditPage(1) }} style={{ width: 250 }} /><Select allowClear placeholder="全部操作" value={auditAction || undefined} onChange={value => { setAuditAction(value || ''); setAuditPage(1) }} style={{ width: 210 }} options={auditActions.map(action => ({ value: action, label: action }))} /></Space>}>{auditError ? <Empty description={auditError}><Button onClick={() => setAuditRefreshKey(value => value + 1)}>重试</Button></Empty> : <><List loading={auditLoading} dataSource={auditItems} locale={{ emptyText: '暂无审计记录' }} renderItem={item => <List.Item><List.Item.Meta title={item.action} description={`${item.actor || '系统'} · ${item.target ? `${item.target} · ` : ''}${item.reason || '未填写原因'}`} /><Text type="secondary">{item.createdAt ? new Date(item.createdAt).toLocaleString('zh-CN') : '—'}</Text></List.Item>} /><Pagination current={auditPage} pageSize={20} total={auditTotal} showSizeChanger={false} onChange={setAuditPage} /></>}</Card> },
  ]

  return <div className="page-stack"><div className="page-intro"><div><Text className="eyebrow">OPERATIONS</Text><Title level={1}>运营后台</Title><Paragraph>管理内容管理、套餐、权益、用户、邀请码和审计记录。</Paragraph></div><Button icon={<FileTextOutlined />} onClick={onExportAdminSummary}>导出数据</Button></div><Card className="admin-tabs-card"><Tabs activeKey={activeTab} onChange={setActiveTab} items={tabItems} /></Card>{detailDrawer}<Drawer width={900} title="邀请码批次详情" open={Boolean(inviteDetail)} onClose={() => { setInviteDetail(null); setSelectedInvitationIds([]) }} extra={<Space><Button onClick={() => navigator.clipboard?.writeText((inviteDetail?.invitations || []).map(item => item.code).join('\n'))}>复制全部</Button><Button danger disabled={!selectedInvitationIds.length} onClick={deleteSelectedInvitations}>删除所选未使用码</Button></Space>}>{inviteDetailLoading ? <Skeleton active paragraph={{ rows: 10 }} /> : inviteDetail && <Space direction="vertical" size={18} style={{ width: '100%' }}><Descriptions bordered size="small" column={2}><Descriptions.Item label="创建时间">{new Date(inviteDetail.batch.createdAt).toLocaleString('zh-CN')}</Descriptions.Item><Descriptions.Item label="创建人">{inviteDetail.batch.createdBy || '系统'}</Descriptions.Item><Descriptions.Item label="备注">{inviteDetail.batch.note || '无备注'}</Descriptions.Item><Descriptions.Item label="渠道">{inviteDetail.batch.channel || '未标记'}</Descriptions.Item><Descriptions.Item label="单码可用次数">{inviteDetail.batch.maxUses}</Descriptions.Item><Descriptions.Item label="过期时间">{inviteDetail.batch.expiresAt ? new Date(inviteDetail.batch.expiresAt).toLocaleString('zh-CN') : '永久'}</Descriptions.Item></Descriptions><Table rowKey="id" columns={invitationDetailColumns} dataSource={inviteDetail.invitations || []} pagination={{ pageSize: 10 }} rowSelection={{ selectedRowKeys: selectedInvitationIds, onChange: setSelectedInvitationIds, getCheckboxProps: row => ({ disabled: !row.deletable, title: row.deletable ? '可删除' : '已使用或关联邀请奖励，不能删除' }) }} /></Space>}</Drawer><Modal width={680} title="创建人工订阅" open={orderOpen} onCancel={() => setOrderOpen(false)} onOk={() => orderForm.submit()} okText="创建订阅"><Form form={orderForm} layout="vertical" onFinish={submitOrder}><Form.Item label="用户" name="userId" rules={[{ required: true }]}><Select showSearch optionFilterProp="label" options={users.map(user => ({ value: user.id, label: `${user.displayName || '未设置昵称'} · ${user.email}` }))} /></Form.Item><Form.Item label="权益版本" name="planVersion" rules={[{ required: true }]}><Select options={(adminData?.planVersions || []).filter(plan => plan.active).map(plan => ({ value: plan.id, label: `${plan.name} (${plan.id})` }))} /></Form.Item><Form.Item label="快捷时长" name="duration"><Segmented block value={duration} onChange={selectDuration} options={[{ label: '1 周', value: 'week' }, { label: '1 月', value: 'month' }, { label: '1 季度', value: 'quarter' }, { label: '1 年', value: 'year' }]} /></Form.Item><Form.Item label="开始与结束时间" name="period" rules={[{ required: true }]}><RangePicker showTime style={{ width: '100%' }} /></Form.Item><Form.Item label="金额（分）" name="amountCents"><InputNumber min={0} style={{ width: '100%' }} /></Form.Item><Form.Item label="备注" name="note"><Input.TextArea rows={3} /></Form.Item></Form></Modal><Modal title="创建邀请码" open={inviteOpen} onCancel={() => setInviteOpen(false)} onOk={() => inviteForm.submit()} okText="生成邀请码"><Form form={inviteForm} layout="vertical" onFinish={submitInvite}><Form.Item label="指定邀请码（可选）" name="code"><Input /></Form.Item><Row gutter={12}><Col span={12}><Form.Item label="生成数量" name="count" initialValue={1}><InputNumber min={1} max={100} style={{ width: '100%' }} /></Form.Item></Col><Col span={12}><Form.Item label="每个码可使用次数" name="maxUses" initialValue={1}><InputNumber min={1} max={1000000} style={{ width: '100%' }} /></Form.Item></Col></Row><Form.Item label="过期时间（可选）" name="expiresAt"><DatePicker showTime style={{ width: '100%' }} /></Form.Item><Form.Item label="备注" name="note" initialValue="运营后台创建"><Input.TextArea rows={3} /></Form.Item></Form></Modal></div>
}
