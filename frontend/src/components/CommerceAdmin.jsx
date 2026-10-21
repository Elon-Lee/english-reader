import React, { useMemo, useState } from 'react'
import { Alert, Button, Checkbox, Descriptions, Drawer, Dropdown, Empty, Form, Input, InputNumber, List, Modal, Segmented, Select, Space, Switch, Table, Tag, Typography, message } from 'antd'
import { MoreOutlined, PlusOutlined } from '@ant-design/icons'
import { postJson } from '../api/client'

const { Paragraph, Text, Title } = Typography

function money(cents) { return `¥${(Number(cents || 0) / 100).toFixed(0)}` }
function moneyExact(cents) { const amount = Number(cents || 0) / 100; return `¥${Number.isInteger(amount) ? amount.toFixed(0) : amount.toFixed(2)}` }

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

export default function CommerceAdmin({ products = [], entitlements = { builtIn: [], configured: [] }, onCreateProduct, onCreateVersion, onPublishVersion, onSetProductActive, onDeleteProduct, onCreateConfiguredBenefit, onUpdateConfiguredBenefit }) {
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('active')
  const [productOpen, setProductOpen] = useState(false)
  const [versionProduct, setVersionProduct] = useState(null)
  const [historyProduct, setHistoryProduct] = useState(null)
  const [detailProduct, setDetailProduct] = useState(null)
  const [linkVersion, setLinkVersion] = useState(null)
  const [purchaseUrl, setPurchaseUrl] = useState('')
  const [savingLink, setSavingLink] = useState(false)
  const [messageApi, contextHolder] = message.useMessage()
  const [productForm] = Form.useForm()
  const [versionForm] = Form.useForm()
  const originalAmountCents = Form.useWatch('originalAmountCents', versionForm) || 0
  const discountPercent = Form.useWatch('discountPercent', versionForm) || 100
  const discountedAmountCents = Math.round(Number(originalAmountCents) * Number(discountPercent) / 100)
  const productState = product => {
    const published = product.versions?.find(item => item.status === 'published')
    if (product.family === 'free' && product.active && published) return 'free'
    if (!product.active) return 'stopped'
    if (!published) return !product.versions?.length || product.versions.every(item => item.status === 'draft') ? 'draft' : 'stopped'
    if (published.amountCents > 0 && !published.purchaseUrl) return 'draft'
    return 'active'
  }
  const filtered = useMemo(() => products.filter(product => {
    const current = product.versions?.find(item => item.status === 'published')
    const matches = `${current?.name || product.slug} ${product.slug} ${product.family}`.toLowerCase().includes(query.trim().toLowerCase())
    return matches && (status === 'all' || productState(product) === status)
  }), [products, query, status])

  const createProduct = async values => { const created = await onCreateProduct?.(values); productForm.resetFields(); setProductOpen(false); if (created) openVersion({ ...created, versions: [] }) }
  const openVersion = product => {
    const latest = product.versions?.[0]
    const limits = latest?.featureLimits || {}
    const selected = Object.fromEntries(Object.entries(limits).filter(([, amount]) => Number(amount) > 0))
    const activeConfigured = new Set((entitlements.configured || []).filter(item => item.active).map(item => item.id))
    versionForm.setFieldsValue({
      name: latest?.name || '', shortName: latest?.shortName || '', tagline: latest?.tagline || '', description: latest?.description || '',
      durationDays: latest?.durationDays || 30,
      originalAmountCents: latest?.originalAmountCents ?? latest?.amountCents ?? (product.family === 'free' ? 0 : 3167),
      discountPercent: latest?.discountPercent ?? (product.family === 'free' ? 100 : 60),
      purchaseUrl: latest?.purchaseUrl || '', featureLimits: selected, configuredBenefitIds: (latest?.configuredBenefits || []).map(item => item.id).filter(id => activeConfigured.has(id)), featured: Boolean(latest?.featured),
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
    ...((!product.versions?.length || product.versions.every(item => item.status === 'draft')) && product.family !== 'free' ? [{ type: 'divider' }, { key: 'delete', danger: true, label: '删除未上架套餐' }] : []),
  ]
  const act = (product, key) => {
    if (key === 'detail') setDetailProduct(product)
    if (key === 'new-version') openVersion(product)
    if (key === 'history') setHistoryProduct(product)
    if (key === 'status') Modal.confirm({ title: product.active ? '确认停止新售？' : '确认恢复销售？', content: product.active ? '停售仅影响新订单，历史订单和已有会员权益保持不变。' : '恢复后，当前已发布版本会重新出现在公开套餐页。', okText: product.active ? '停止新售' : '恢复销售', cancelText: '取消', okButtonProps: { danger: product.active }, onOk: () => onSetProductActive?.(product.id, !product.active) })
    if (key === 'delete') Modal.confirm({ title: `删除未上架套餐 ${product.slug}？`, content: '仅全部版本均为草稿的套餐可删除。若已有订单、兑换码或订阅引用，服务端会拒绝删除。', okText: '删除套餐', cancelText: '取消', okButtonProps: { danger: true }, onOk: () => onDeleteProduct?.(product.id) })
  }
  const columns = [
    { title: '套餐', key: 'name', render: (_, product) => { const current = product.versions?.find(item => item.status === 'published'); return <Space direction="vertical" size={1}><Text strong>{current?.name || product.slug}</Text><Text type="secondary">{product.slug} · {product.family}</Text></Space> } },
    { title: '当前版本', key: 'version', width: 110, render: (_, product) => { const current = product.versions?.find(item => item.status === 'published'); return current ? <Tag color="blue">V{current.version}</Tag> : <Tag>无</Tag> } },
    { title: '价格', key: 'price', width: 165, render: (_, product) => { const current = product.versions?.find(item => item.status === 'published'); return current ? <Space direction="vertical" size={0}><Text>{money(current.amountCents)}</Text>{current.discountPercent < 100 && <Text type="secondary"><del>{moneyExact(current.originalAmountCents)}</del> · {current.discountPercent / 10}折</Text>}</Space> : '—' } },
    { title: '期限', key: 'duration', width: 110, render: (_, product) => product.family === 'free' ? '长期' : `${product.versions?.find(item => item.status === 'published')?.durationDays || '—'} 天` },
    { title: '受控功能', key: 'features', width: 120, render: (_, product) => { const current = product.versions?.find(item => item.status === 'published'); return current ? Object.values(current.featureLimits || {}).filter(value => Number(value) > 0).length : '—' } },
    { title: '状态', key: 'status', width: 110, render: (_, product) => { const state = productState(product); const label = state === 'free' ? '免费开放' : state === 'active' ? '销售中' : state === 'stopped' ? '已停售' : '未上架'; return <Tag color={state === 'active' || state === 'free' ? 'success' : state === 'draft' ? 'processing' : 'default'}>{label}</Tag> } },
    { title: '操作', key: 'actions', width: 90, fixed: 'right', render: (_, product) => <Dropdown trigger={['click']} menu={{ items: actionItems(product), onClick: ({ key }) => act(product, key) }}><Button type="text" icon={<MoreOutlined />} aria-label={`${product.slug} 功能菜单`} /></Dropdown> },
  ]
  const currentDetail = detailProduct?.versions?.find(item => item.status === 'published')

  const savePurchaseLink = async () => {
    setSavingLink(true)
    try {
      const result = await postJson(`/api/admin/commerce/versions/${encodeURIComponent(linkVersion.id)}/purchase-link`, { purchaseUrl })
      setHistoryProduct(current => current ? { ...current, versions: current.versions.map(item => item.id === result.id ? { ...item, purchaseUrl: result.purchaseUrl } : item) } : current)
      setLinkVersion(null); messageApi.success('云猫购买链接已保存')
    } catch (error) { messageApi.error(error.message || '保存云猫商品链接失败') }
    finally { setSavingLink(false) }
  }

  const versionActions = version => {
    const linkAction = <Button key="link" onClick={() => { setLinkVersion(version); setPurchaseUrl(version.purchaseUrl || '') }}>设置云猫链接</Button>
    const publishAction = <Button key="publish" type="primary" onClick={() => Modal.confirm({ title: `发布 ${version.name} V${version.version}？`, content: version.amountCents > 0 && !version.purchaseUrl ? '套餐会先公开展示，购买按钮保持禁用；云猫链接可稍后补充。' : '发布后当前线上版本停止新售，历史订单与已有会员权益不变。', okText: '确认发布', cancelText: '取消', onOk: () => onPublishVersion?.(version.id) })}>发布</Button>
    if (version.status === 'draft') return [publishAction, ...(version.amountCents > 0 && !version.purchaseUrl ? [linkAction] : [])]
    if (version.status === 'published' && version.amountCents > 0 && !version.purchaseUrl) return [linkAction]
    return []
  }

  return <>
    {contextHolder}
    <div className="commerce-list-toolbar"><Input.Search allowClear placeholder="搜索套餐名称或标识" value={query} onChange={event => setQuery(event.target.value)} style={{ width: 280 }} /><Segmented value={status} onChange={setStatus} options={[{ label: '全部', value: 'all' }, { label: '销售中', value: 'active' }, { label: '免费开放', value: 'free' }, { label: '未上架', value: 'draft' }, { label: '已停售', value: 'stopped' }]} /><Button type="primary" icon={<PlusOutlined />} onClick={() => setProductOpen(true)}>新开套餐</Button></div>
    <Table rowKey="id" columns={columns} dataSource={filtered} pagination={{ pageSize: 8 }} scroll={{ x: 900 }} locale={{ emptyText: <Empty description="暂无符合条件的套餐" /> }} />

    <Modal title="新开套餐" open={productOpen} onCancel={() => setProductOpen(false)} onOk={() => productForm.submit()} okText="创建并配置版本"><Form form={productForm} layout="vertical" onFinish={createProduct}><Form.Item label="公开标识" name="slug" extra="创建后保持稳定，例如 advanced-monthly。" rules={[{ required: true }]}><Input placeholder="advanced-monthly" /></Form.Item><Form.Item label="会员等级" name="family" rules={[{ required: true }]}><Select options={[{ value: 'free', label: '免费版' }, { value: 'advanced', label: '进阶版' }, { value: 'pro', label: 'Pro版' }]} /></Form.Item><Form.Item label="展示顺序" name="displayOrder" initialValue={100}><InputNumber min={0} style={{ width: '100%' }} /></Form.Item></Form></Modal>

    <Drawer width={860} title={`为 ${versionProduct?.slug || ''} 创建新版本`} open={Boolean(versionProduct)} onClose={() => setVersionProduct(null)} extra={<Space><Button onClick={() => setVersionProduct(null)}>取消</Button><Button type="primary" onClick={() => versionForm.submit()}>保存草稿</Button></Space>}><Form form={versionForm} layout="vertical" onFinish={createVersion}><Title level={4}>基础信息</Title><RowLike><Form.Item label="套餐名称" name="name" rules={[{ required: true }]}><Input placeholder="进阶会员月卡" /></Form.Item><Form.Item label="短名称" name="shortName" rules={[{ required: true }]}><Input placeholder="进阶版" /></Form.Item></RowLike><Form.Item label="核心卖点" name="tagline" rules={[{ required: true }]}><Input /></Form.Item><Form.Item label="商品说明" name="description" rules={[{ required: true }]}><Input.TextArea rows={3} /></Form.Item><Form.Item label="服务期限（天）" name="durationDays" rules={[{ required: true }]}><InputNumber min={1} max={3660} style={{ width: '100%' }} /></Form.Item><RowLike><Form.Item label="原价（分）" name="originalAmountCents" rules={[{ required: true }]}><InputNumber min={0} style={{ width: '100%' }} /></Form.Item><Form.Item label="折扣（%）" name="discountPercent" rules={[{ required: true }]}><InputNumber min={1} max={100} style={{ width: '100%' }} /></Form.Item></RowLike><Alert type="info" showIcon message={`折后售价 ${moneyExact(discountedAmountCents)}${discountPercent < 100 ? ` · ${Number.isInteger(discountPercent / 10) ? discountPercent / 10 : (discountPercent / 10).toFixed(1)} 折` : ''}`} /><Form.Item label="云猫商品链接" name="purchaseUrl" rules={versionProduct?.family === 'free' ? [] : [{ type: 'url', message: '请输入 HTTPS 云猫商品链接' }]}><Input placeholder={versionProduct?.family === 'free' ? '免费版无需云猫链接' : '商品上架后填写 https://catfk.com/shop/...'} /></Form.Item><Title level={4}>套餐权益</Title><Paragraph>视频收藏、音频收藏和私人学习空间为套餐分档权益；其余系统功能作为免费包含权益展示。</Paragraph><Form.Item name="featureLimits" rules={[{ required: true, message: '请配置视频上限、音频上限和私人空间' }]}><FeaturePicker items={entitlements.builtIn || []} /></Form.Item><Form.Item label="设为推荐方案" name="featured" valuePropName="checked"><Switch /></Form.Item></Form></Drawer>

    <Drawer width={720} title="当前套餐内容" open={Boolean(detailProduct)} onClose={() => setDetailProduct(null)}>{currentDetail ? <Space direction="vertical" size={20} style={{ width: '100%' }}><Descriptions bordered column={2}><Descriptions.Item label="版本">V{currentDetail.version}</Descriptions.Item><Descriptions.Item label="状态">{currentDetail.status}</Descriptions.Item><Descriptions.Item label="原价">{moneyExact(currentDetail.originalAmountCents)}</Descriptions.Item><Descriptions.Item label="折扣">{currentDetail.discountPercent < 100 ? `${currentDetail.discountPercent / 10} 折` : '无'}</Descriptions.Item><Descriptions.Item label="折后售价">{money(currentDetail.amountCents)}</Descriptions.Item><Descriptions.Item label="期限">{currentDetail.durationDays ? `${currentDetail.durationDays} 天` : '长期免费'}</Descriptions.Item></Descriptions><Title level={4}>套餐权益（系统额度）</Title><List dataSource={(entitlements.builtIn || []).filter(item => Number(currentDetail.featureLimits?.[item.key]) > 0)} renderItem={item => <List.Item><List.Item.Meta title={`${item.name}：${currentDetail.featureLimits[item.key]} ${item.unit}`} description={item.control} /><Tag color="success">系统受控</Tag></List.Item>} /><Title level={4}>免费包含权益</Title><List dataSource={currentDetail.benefits || []} renderItem={item => <List.Item>{item}</List.Item>} /><Title level={4}>配置权益</Title><List dataSource={currentDetail.configuredBenefits || []} locale={{ emptyText: '未配置附加权益' }} renderItem={item => <List.Item><List.Item.Meta title={item.name} description={item.text} /><Tag>展示项</Tag></List.Item>} /></Space> : <Empty description="暂无已发布版本" />}</Drawer>

    <Drawer width={680} title={`${historyProduct?.slug || ''} · 历史套餐`} open={Boolean(historyProduct)} onClose={() => setHistoryProduct(null)}><List dataSource={historyProduct?.versions || []} locale={{ emptyText: '暂无历史版本' }} renderItem={version => <List.Item actions={versionActions(version)}><List.Item.Meta title={<Space><Text strong>{version.name} · V{version.version}</Text><Tag color={version.status === 'published' ? 'success' : version.status === 'draft' ? 'processing' : 'default'}>{version.status}</Tag></Space>} description={<>{money(version.amountCents)} · {version.discountPercent < 100 ? `${moneyExact(version.originalAmountCents)} 原价 · ${version.discountPercent / 10}折 · ` : ''}{version.durationDays ? `${version.durationDays} 天` : '永久免费'} · {version.purchaseUrl || (version.amountCents > 0 ? '购买链接待补充' : '无需购买链接')} · {new Date(version.createdAt || version.publishedAt).toLocaleString('zh-CN')}</>} /></List.Item>} /></Drawer>
    <Modal title={`配置 ${linkVersion?.name || ''} 云猫商品链接`} open={Boolean(linkVersion)} onCancel={() => setLinkVersion(null)} onOk={savePurchaseLink} confirmLoading={savingLink}><Input value={purchaseUrl} onChange={event => setPurchaseUrl(event.target.value)} placeholder="https://catfk.com/shop/..." /></Modal>
  </>
}

function RowLike({ children }) { return <div className="commerce-form-grid">{children}</div> }
