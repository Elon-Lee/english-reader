import React, { useEffect, useState } from 'react'
import { Alert, Button, Card, Descriptions, Drawer, Form, Input, Modal, Pagination, Select, Space, Switch, Table, Tag, Typography, message } from 'antd'

import { getJson, postJson } from '../api/client'

const { Paragraph, Text } = Typography
const pageSize = 20
const orderStatus = { pending: '待支付', paid: '已支付', failed: '未完成', cancelled: '已取消', refunding: '退款处理中', refunded: '已退款' }
const redemptionStatus = { active: '未兑换', redeemed: '已兑换', revoked: '已作废' }

function useAdminList(path, filters) {
  const [data, setData] = useState({ total: 0 })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const reload = () => setRevision(value => value + 1)
  useEffect(() => {
    let active = true
    const timer = setTimeout(() => {
      setLoading(true); setError('')
      const query = new URLSearchParams({ limit: String(pageSize), offset: String((filters.page - 1) * pageSize) })
      if (filters.query.trim()) query.set('q', filters.query.trim())
      if (filters.status) query.set('status', filters.status)
      getJson(`${path}?${query}`).then(value => { if (active) setData(value) }).catch(failure => { if (active) setError(failure.message || '记录加载失败') }).finally(() => { if (active) setLoading(false) })
    }, 160)
    return () => { active = false; clearTimeout(timer) }
  }, [path, filters.query, filters.status, filters.page, revision])
  return { data, loading, error, reload }
}

export function PaymentMethodSettings() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [api, contextHolder] = message.useMessage()
  const load = async () => {
    setLoading(true); setError('')
    try { const result = await getJson('/api/admin/payment-config'); setData(result.payment) }
    catch (failure) { setError(failure.message || '支付设置加载失败') }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])
  const save = async key => {
    if (!data) return
    setSaving(true)
    try { const result = await postJson('/api/admin/payment-config', { alipayEnabled: data.alipayEnabled, cloudcatEnabled: data.cloudcatEnabled, redemptionEnabled: data.redemptionEnabled, [key]: !data[key] }); setData(result.payment); api.success('支付方式设置已保存') }
    catch (failure) { api.error(failure.message || '支付方式设置保存失败') }
    finally { setSaving(false) }
  }
  return <Card title="支付方式设置" extra={<Button onClick={load} loading={loading}>刷新</Button>}>
    {contextHolder}
    {error ? <Alert type="error" showIcon message={error} action={<Button onClick={load}>重试</Button>} /> : loading && !data ? <Paragraph>正在读取支付设置…</Paragraph> : data && <Space direction="vertical" size={18} style={{ width: '100%' }}>
      <Alert type={data.alipayRequirements?.testMode ? 'warning' : 'info'} showIcon message={data.alipayRequirements?.testMode ? '本地支付宝流程模拟已启用' : '支付宝尚未开放'} description={data.alipayRequirements?.testMode ? '模拟订单不会连接支付宝网关或产生真实扣款，仅用于验证订单、会员开通和后台管理流程。' : '支付宝应用号、RSA2 密钥和异步通知地址由服务端环境安全配置。当前后台不接收或展示密钥；获批具体支付产品并完成部署配置后，才能开启支付宝。'} />
      <Space align="start" size={18} style={{ width: '100%', justifyContent: 'space-between' }}><div><Text strong>支付宝扫码付款</Text><Paragraph type="secondary">付款确认和会员开通由服务端查单处理，不自动续费。</Paragraph>{data.alipayRequirements && <Text type="secondary">{data.alipayRequirements.testMode ? '本地模拟模式已就绪' : `服务端参数：${data.alipayRequirements.configured ? '已配置' : '未完整配置'}`}</Text>}</div><Switch checked={data.alipayEnabled} disabled={!data.alipayReady || saving} loading={saving} onChange={() => save('alipayEnabled')} aria-label="启用支付宝支付" /></Space>
      <Space align="start" size={18} style={{ width: '100%', justifyContent: 'space-between' }}><div><Text strong>云猫购买</Text><Paragraph type="secondary">用户前往对应云猫商品页付款并取得兑换码。</Paragraph></div><Switch checked={data.cloudcatEnabled} disabled={saving} loading={saving} onChange={() => save('cloudcatEnabled')} aria-label="启用云猫购买" /></Space>
      <Space align="start" size={18} style={{ width: '100%', justifyContent: 'space-between' }}><div><Text strong>兑换码开通</Text><Paragraph type="secondary">允许用户提交已取得的拾页兑换码开通会员。</Paragraph></div><Switch checked={data.redemptionEnabled} disabled={saving} loading={saving} onChange={() => save('redemptionEnabled')} aria-label="启用兑换码开通" /></Space>
    </Space>}
  </Card>
}

export function PaymentOrdersAdmin() {
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const [refundOrder, setRefundOrder] = useState(null)
  const [detail, setDetail] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [syncingId, setSyncingId] = useState('')
  const [refunding, setRefunding] = useState(false)
  const [form] = Form.useForm()
  const [api, contextHolder] = message.useMessage()
  const { data, loading, error, reload } = useAdminList('/api/admin/payment-orders', { query, status, page })
  const submitRefund = async values => {
    if (!refundOrder) return
    setRefunding(true)
    try {
      const result = await postJson(`/api/admin/payment-orders/${encodeURIComponent(refundOrder.orderId)}/refund`, { reason: values.reason })
      api[result.status === 'refunded' ? 'success' : 'warning'](result.status === 'refunded' ? '支付宝已确认退款，会员权益已撤销' : '退款已受理，等待支付宝确认；会员权益暂时保持有效')
      setRefundOrder(null); form.resetFields(); reload()
    }
    catch (failure) { api.error(failure.message || '退款处理失败'); throw failure }
    finally { setRefunding(false) }
  }
  const openDetail = async row => {
    setDetail({ orderId: row.orderId }); setDetailLoading(true)
    try { setDetail(await getJson(`/api/admin/payment-orders/${encodeURIComponent(row.orderId)}`)) }
    catch (failure) { setDetail({ orderId: row.orderId, error: failure.message || '订单详情加载失败' }) }
    finally { setDetailLoading(false) }
  }
  const syncRefund = async row => {
    setSyncingId(row.orderId)
    try {
      const result = await postJson(`/api/admin/payment-orders/${encodeURIComponent(row.orderId)}/sync-refund`, {})
      api[result.status === 'refunded' ? 'success' : 'warning'](result.status === 'refunded' ? '支付宝已确认退款，会员权益已撤销' : '支付宝尚未确认退款，会员权益保持有效')
      reload()
    } catch (failure) { api.error(failure.message || '退款状态查询失败') }
    finally { setSyncingId('') }
  }
  const columns = [
    { title: '订单号', dataIndex: 'orderId', width: 210, render: value => <Text code>{value}</Text> },
    { title: '用户', dataIndex: 'email', width: 210 },
    { title: '套餐', dataIndex: 'productName', width: 150 },
    { title: '金额', dataIndex: 'amountCents', width: 100, render: value => `¥${(value / 100).toFixed(2)}` },
    { title: '状态', dataIndex: 'status', width: 120, render: value => <Tag color={value === 'paid' ? 'success' : value === 'refunded' ? 'default' : value === 'refunding' ? 'processing' : value === 'failed' ? 'error' : 'warning'}>{orderStatus[value] || value}</Tag> },
    { title: '支付宝交易号', dataIndex: 'tradeNo', width: 190, render: value => value || '—' },
    { title: '创建时间', dataIndex: 'createdAt', width: 175, render: value => value ? new Date(value).toLocaleString('zh-CN') : '—' },
    { title: '操作', fixed: 'right', width: 170, render: (_, row) => <Space><Button size="small" onClick={() => openDetail(row)}>详情</Button>{row.status === 'paid' ? <Button danger size="small" onClick={() => { setRefundOrder(row); form.resetFields() }}>退款</Button> : row.status === 'refunding' ? <Button size="small" loading={syncingId === row.orderId} onClick={() => syncRefund(row)}>查退款</Button> : null}</Space> },
  ]
  return <Card title="支付宝订单" extra={<Button onClick={reload}>刷新</Button>}>
    {contextHolder}
    <Space wrap style={{ marginBottom: 16 }}><Input.Search allowClear placeholder="订单号、交易号、邮箱或套餐" value={query} onChange={event => { setQuery(event.target.value); setPage(1) }} style={{ width: 320 }} /><Select allowClear placeholder="全部状态" value={status || undefined} onChange={value => { setStatus(value || ''); setPage(1) }} style={{ width: 150 }} options={Object.entries(orderStatus).map(([value, label]) => ({ value, label }))} /></Space>
    {error && <Alert type="error" showIcon message={error} action={<Button onClick={reload}>重试</Button>} style={{ marginBottom: 16 }} />}
    <Table rowKey="orderId" size="small" loading={loading} columns={columns} dataSource={data.orders || []} pagination={false} scroll={{ x: 1400 }} locale={{ emptyText: error ? '订单加载失败' : '暂无支付宝订单' }} />
    {data.total > pageSize && <Pagination style={{ marginTop: 16, textAlign: 'right' }} current={page} pageSize={pageSize} total={data.total} showSizeChanger={false} onChange={setPage} />}
    <Drawer title="支付宝订单详情" open={Boolean(detail)} width={560} onClose={() => setDetail(null)}>{detailLoading ? <Paragraph>正在读取订单详情…</Paragraph> : detail?.error ? <Alert type="error" showIcon message={detail.error} /> : detail && <Descriptions bordered size="small" column={1}>
      <Descriptions.Item label="订单号">{detail.orderId}</Descriptions.Item><Descriptions.Item label="用户">{detail.email}</Descriptions.Item><Descriptions.Item label="商品">{detail.productName}</Descriptions.Item><Descriptions.Item label="订单状态">{orderStatus[detail.status] || detail.status}</Descriptions.Item><Descriptions.Item label="金额">¥{(detail.amountCents / 100).toFixed(2)} {detail.currency}</Descriptions.Item><Descriptions.Item label="支付宝交易号">{detail.tradeNo || '—'}</Descriptions.Item><Descriptions.Item label="创建时间">{detail.createdAt ? new Date(detail.createdAt).toLocaleString('zh-CN') : '—'}</Descriptions.Item><Descriptions.Item label="退款原因">{detail.refundReason || '—'}</Descriptions.Item><Descriptions.Item label="退款金额">{detail.refundAmountCents ? `¥${(detail.refundAmountCents / 100).toFixed(2)}` : '—'}</Descriptions.Item><Descriptions.Item label="会员变更单">{detail.membershipChangeOrderId || '—'}</Descriptions.Item>
    </Descriptions>}</Drawer>
    <Modal title="支付宝全额退款" open={Boolean(refundOrder)} confirmLoading={refunding} onCancel={() => !refunding && setRefundOrder(null)} onOk={() => form.submit()} okText="提交退款" okButtonProps={{ danger: true }}>
      {refundOrder && <><Alert type="warning" showIcon message={`将退款 ¥${(refundOrder.amountCents / 100).toFixed(2)}`} description="此操作会调用支付宝退款，并撤销本订单首次开通的会员权益；退款结果和操作原因会写入审计记录。续费、升级或后续已有会员变更的订单会被服务端拒绝自动退款。" /><Form form={form} layout="vertical" onFinish={submitRefund} style={{ marginTop: 16 }}><Form.Item label="退款原因" name="reason" rules={[{ required: true, message: '请填写退款原因' }]}><Input.TextArea rows={3} maxLength={500} /></Form.Item></Form></>}
    </Modal>
  </Card>
}

export function RedemptionRecordsAdmin() {
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const { data, loading, error, reload } = useAdminList('/api/admin/commerce/redemption-records', { query, status, page })
  const columns = [
    { title: '记录编号', dataIndex: 'id', width: 220, render: value => <Text code>{value}</Text> },
    { title: '批次', dataIndex: 'batchId', width: 220, render: value => <Text code>{value}</Text> },
    { title: '兑换码前缀', dataIndex: 'codePrefix', width: 130, render: value => value ? `${value}…` : '—' },
    { title: '套餐', dataIndex: 'productName', width: 150 },
    { title: '状态', dataIndex: 'status', width: 100, render: value => <Tag color={value === 'redeemed' ? 'success' : value === 'revoked' ? 'default' : 'processing'}>{redemptionStatus[value] || value}</Tag> },
    { title: '兑换账号', dataIndex: 'email', width: 220, render: value => value || '—' },
    { title: '兑换时间', dataIndex: 'redeemedAt', width: 180, render: value => value ? new Date(value).toLocaleString('zh-CN') : '—' },
    { title: '会员订阅', dataIndex: 'subscriptionId', width: 190, render: value => value ? <Text code>{value}</Text> : '—' },
  ]
  return <Card title="兑换记录" extra={<Button onClick={reload}>刷新</Button>}>
    <Paragraph type="secondary">查询拾页兑换码的生成、核销和作废状态。云猫侧付款与退款订单需在云猫商户后台核对；拾页不展示未同步的云猫订单。</Paragraph>
    <Space wrap style={{ marginBottom: 16 }}><Input.Search allowClear placeholder="记录号、批次、前缀、邮箱或套餐" value={query} onChange={event => { setQuery(event.target.value); setPage(1) }} style={{ width: 330 }} /><Select allowClear placeholder="全部状态" value={status || undefined} onChange={value => { setStatus(value || ''); setPage(1) }} style={{ width: 150 }} options={Object.entries(redemptionStatus).map(([value, label]) => ({ value, label }))} /></Space>
    {error && <Alert type="error" showIcon message={error} action={<Button onClick={reload}>重试</Button>} style={{ marginBottom: 16 }} />}
    <Table rowKey="id" size="small" loading={loading} columns={columns} dataSource={data.records || []} pagination={false} scroll={{ x: 1400 }} locale={{ emptyText: error ? '记录加载失败' : '暂无兑换记录' }} />
    {data.total > pageSize && <Pagination style={{ marginTop: 16, textAlign: 'right' }} current={page} pageSize={pageSize} total={data.total} showSizeChanger={false} onChange={setPage} />}
  </Card>
}
