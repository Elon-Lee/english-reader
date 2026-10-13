import React, { useMemo, useState } from 'react'
import { Button, Checkbox, Descriptions, Drawer, Dropdown, Empty, Form, Input, InputNumber, List, Modal, Segmented, Select, Space, Switch, Table, Tag, Typography } from 'antd'
import { MoreOutlined, PlusOutlined } from '@ant-design/icons'

const { Paragraph, Text, Title } = Typography

function money(cents) { return `¥${(Number(cents || 0) / 100).toFixed(0)}` }

function FeaturePicker({ items, value = {}, onChange }) {
  const selected = value || {}
  const toggle = (key, checked, defaultLimit) => {
    const next = { ...selected }
    if (checked) next[key] = Number(next[key] ?? defaultLimit)
    else delete next[key]
    onChange?.(next)
  }
  const update = (key, amount) => onChange?.({ ...selected, [key]: Number(amount || 0) })
  return <div className="commerce-feature-picker">{items.map(item => {
    const checked = Object.prototype.hasOwnProperty.call(selected, item.key)
    return <div className={`commerce-feature-row ${checked ? 'is-selected' : ''}`} key={item.key}><Checkbox checked={checked} disabled={item.required} onChange={event => toggle(item.key, event.target.checked, item.defaultLimit)}><span className="commerce-feature-name">{item.name}</span></Checkbox><Text className="commerce-feature-control" type="secondary">{item.control}</Text><InputNumber min={item.minimum} disabled={!checked} value={checked ? selected[item.key] : item.defaultLimit} onChange={amount => update(item.key, amount)} addonAfter={item.unit} /></div>
  })}</div>
}

export default function CommerceAdmin({ products = [], entitlements = { builtIn: [], configured: [] }, onCreateProduct, onCreateVersion, onPublishVersion, onSetProductActive, onCreateConfiguredBenefit, onUpdateConfiguredBenefit }) {
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('all')
  const [productOpen, setProductOpen] = useState(false)
  const [versionProduct, setVersionProduct] = useState(null)
  const [historyProduct, setHistoryProduct] = useState(null)
  const [detailProduct, setDetailProduct] = useState(null)
  const [productForm] = Form.useForm()
  const [versionForm] = Form.useForm()
  const filtered = useMemo(() => products.filter(product => {
    const current = product.versions?.find(item => item.status === 'published')
    const matches = `${current?.name || ''} ${product.slug} ${product.family}`.toLowerCase().includes(query.trim().toLowerCase())
    return matches && (status === 'all' || (status === 'active' ? product.active : !product.active))
  }), [products, query, status])

  const createProduct = async values => { const created = await onCreateProduct?.(values); productForm.resetFields(); setProductOpen(false); if (created) openVersion({ ...created, versions: [] }) }
  const openVersion = product => {
    const latest = product.versions?.[0]
    const limits = latest?.featureLimits || {}
    const selected = Object.fromEntries(Object.entries(limits).filter(([, amount]) => Number(amount) > 0))
    const activeConfigured = new Set((entitlements.configured || []).filter(item => item.active).map(item => item.id))
    const devices = entitlements.builtIn?.find(item => item.key === 'devices')
    if (!Object.prototype.hasOwnProperty.call(selected, 'devices')) selected.devices = devices?.defaultLimit || 1
    versionForm.setFieldsValue({
      name: latest?.name || '', shortName: latest?.shortName || '', tagline: latest?.tagline || '', description: latest?.description || '',
      durationDays: latest?.durationDays || 30, amountCents: latest?.amountCents || 0,
      featureLimits: selected, configuredBenefitIds: (latest?.configuredBenefits || []).map(item => item.id).filter(id => activeConfigured.has(id)), featured: Boolean(latest?.featured),
    })
    setVersionProduct(product)
  }
  const createVersion = async values => { await onCreateVersion?.(versionProduct.id, values); versionForm.resetFields(); setVersionProduct(null) }
  const actionItems = product => [
    { key: 'detail', label: '查看当前版本' },
    { key: 'new-version', label: '创建新版本' },
    { key: 'history', label: '历史套餐' },
    { type: 'divider' },
    { key: 'status', danger: product.active, label: product.active ? '停止新售' : '恢复销售' },
  ]
  const act = (product, key) => {
    if (key === 'detail') setDetailProduct(product)
    if (key === 'new-version') openVersion(product)
    if (key === 'history') setHistoryProduct(product)
    if (key === 'status') Modal.confirm({ title: product.active ? '确认停止新售？' : '确认恢复销售？', content: product.active ? '停售仅影响新订单，历史订单和已有会员权益保持不变。' : '恢复后，当前已发布版本会重新出现在公开套餐页。', okText: product.active ? '停止新售' : '恢复销售', cancelText: '取消', okButtonProps: { danger: product.active }, onOk: () => onSetProductActive?.(product.id, !product.active) })
  }
  const columns = [
    { title: '套餐', key: 'name', render: (_, product) => { const current = product.versions?.find(item => item.status === 'published'); return <Space direction="vertical" size={1}><Text strong>{current?.name || product.slug}</Text><Text type="secondary">{product.slug} · {product.family}</Text></Space> } },
    { title: '当前版本', key: 'version', width: 110, render: (_, product) => { const current = product.versions?.find(item => item.status === 'published'); return current ? <Tag color="blue">V{current.version}</Tag> : <Tag>无</Tag> } },
    { title: '价格', key: 'price', width: 110, render: (_, product) => money(product.versions?.find(item => item.status === 'published')?.amountCents) },
    { title: '期限', key: 'duration', width: 110, render: (_, product) => `${product.versions?.find(item => item.status === 'published')?.durationDays || '—'} 天` },
    { title: '受控功能', key: 'features', width: 120, render: (_, product) => Object.values(product.versions?.find(item => item.status === 'published')?.featureLimits || {}).filter(value => Number(value) > 0).length },
    { title: '状态', key: 'status', width: 110, render: (_, product) => <Tag color={product.active ? 'success' : 'default'}>{product.active ? '销售中' : '已停售'}</Tag> },
    { title: '操作', key: 'actions', width: 90, fixed: 'right', render: (_, product) => <Dropdown trigger={['click']} menu={{ items: actionItems(product), onClick: ({ key }) => act(product, key) }}><Button type="text" icon={<MoreOutlined />} aria-label={`${product.slug} 功能菜单`} /></Dropdown> },
  ]
  const currentDetail = detailProduct?.versions?.find(item => item.status === 'published')

  return <>
    <div className="commerce-list-toolbar"><Input.Search allowClear placeholder="搜索套餐名称或标识" value={query} onChange={event => setQuery(event.target.value)} style={{ width: 280 }} /><Segmented value={status} onChange={setStatus} options={[{ label: '全部', value: 'all' }, { label: '销售中', value: 'active' }, { label: '已停售', value: 'stopped' }]} /><Button type="primary" icon={<PlusOutlined />} onClick={() => setProductOpen(true)}>新开套餐</Button></div>
    <Table rowKey="id" columns={columns} dataSource={filtered} pagination={{ pageSize: 8 }} scroll={{ x: 900 }} locale={{ emptyText: <Empty description="暂无符合条件的套餐" /> }} />

    <Modal title="新开套餐" open={productOpen} onCancel={() => setProductOpen(false)} onOk={() => productForm.submit()} okText="创建并配置版本"><Form form={productForm} layout="vertical" onFinish={createProduct}><Form.Item label="公开标识" name="slug" extra="创建后保持稳定，例如 advanced-90。" rules={[{ required: true }]}><Input placeholder="advanced-90" /></Form.Item><Form.Item label="会员等级" name="family" rules={[{ required: true }]}><Select options={[{ value: 'advanced', label: '进阶版' }, { value: 'pro', label: 'Pro版' }]} /></Form.Item><Form.Item label="展示顺序" name="displayOrder" initialValue={100}><InputNumber min={0} style={{ width: '100%' }} /></Form.Item></Form></Modal>

    <Drawer width={860} title={`为 ${versionProduct?.slug || ''} 创建新版本`} open={Boolean(versionProduct)} onClose={() => setVersionProduct(null)} extra={<Space><Button onClick={() => setVersionProduct(null)}>取消</Button><Button type="primary" onClick={() => versionForm.submit()}>保存草稿</Button></Space>}><Form form={versionForm} layout="vertical" onFinish={createVersion}><Title level={4}>基础信息</Title><RowLike><Form.Item label="套餐名称" name="name" rules={[{ required: true }]}><Input placeholder="进阶会员 90 天" /></Form.Item><Form.Item label="短名称" name="shortName" rules={[{ required: true }]}><Input placeholder="进阶 90 天" /></Form.Item></RowLike><Form.Item label="核心卖点" name="tagline" rules={[{ required: true }]}><Input /></Form.Item><Form.Item label="商品说明" name="description" rules={[{ required: true }]}><Input.TextArea rows={3} /></Form.Item><RowLike><Form.Item label="服务期限（天）" name="durationDays" rules={[{ required: true }]}><InputNumber min={1} max={3660} style={{ width: '100%' }} /></Form.Item><Form.Item label="售价（分）" name="amountCents" rules={[{ required: true }]}><InputNumber min={0} style={{ width: '100%' }} /></Form.Item></RowLike><Title level={4}>内置权益</Title><Paragraph>仅可选择系统真实执行检查的产品功能。发布后会生成独立会员权益版本，并在实际使用时扣减或校验。</Paragraph><Form.Item name="featureLimits" rules={[{ required: true, message: '请配置内置权益' }]}><FeaturePicker items={entitlements.builtIn || []} /></Form.Item><Title level={4}>配置权益</Title><Paragraph>附加服务只用于套餐展示，不参与系统使用次数扣减。</Paragraph><Form.Item name="configuredBenefitIds"><Checkbox.Group className="commerce-configured-checks" options={(entitlements.configured || []).filter(item => item.active).map(item => ({ value: item.id, label: `${item.name} · ${item.defaultText}` }))} /></Form.Item><Form.Item label="设为推荐方案" name="featured" valuePropName="checked"><Switch /></Form.Item></Form></Drawer>

    <Drawer width={720} title="当前套餐内容" open={Boolean(detailProduct)} onClose={() => setDetailProduct(null)}>{currentDetail ? <Space direction="vertical" size={20} style={{ width: '100%' }}><Descriptions bordered column={2}><Descriptions.Item label="版本">V{currentDetail.version}</Descriptions.Item><Descriptions.Item label="状态">{currentDetail.status}</Descriptions.Item><Descriptions.Item label="价格">{money(currentDetail.amountCents)}</Descriptions.Item><Descriptions.Item label="期限">{currentDetail.durationDays} 天</Descriptions.Item></Descriptions><Title level={4}>内置权益与实际限制</Title><List dataSource={(entitlements.builtIn || []).filter(item => Number(currentDetail.featureLimits?.[item.key]) > 0)} renderItem={item => <List.Item><List.Item.Meta title={`${item.name}：${currentDetail.featureLimits[item.key]} ${item.unit}`} description={item.control} /><Tag color="success">系统受控</Tag></List.Item>} /><Title level={4}>配置权益</Title><List dataSource={currentDetail.configuredBenefits || []} locale={{ emptyText: '未配置附加权益' }} renderItem={item => <List.Item><List.Item.Meta title={item.name} description={item.text} /><Tag>展示项</Tag></List.Item>} /></Space> : <Empty description="暂无已发布版本" />}</Drawer>

    <Drawer width={680} title={`${historyProduct?.slug || ''} · 历史套餐`} open={Boolean(historyProduct)} onClose={() => setHistoryProduct(null)}><List dataSource={historyProduct?.versions || []} locale={{ emptyText: '暂无历史版本' }} renderItem={version => <List.Item actions={version.status === 'draft' ? [<Button key="publish" type="primary" onClick={() => Modal.confirm({ title: `发布 ${version.name} V${version.version}？`, content: '发布后当前线上版本停止新售，历史订单与已有会员权益不变。', okText: '确认发布', cancelText: '取消', onOk: () => onPublishVersion?.(version.id) })}>发布</Button>] : []}><List.Item.Meta title={<Space><Text strong>{version.name} · V{version.version}</Text><Tag color={version.status === 'published' ? 'success' : version.status === 'draft' ? 'processing' : 'default'}>{version.status}</Tag></Space>} description={`${money(version.amountCents)} · ${version.durationDays} 天 · ${Object.values(version.featureLimits || {}).filter(value => Number(value) > 0).length} 项受控功能 · ${new Date(version.createdAt || version.publishedAt).toLocaleString('zh-CN')}`} /></List.Item>} /></Drawer>
  </>
}

function RowLike({ children }) { return <div className="commerce-form-grid">{children}</div> }
