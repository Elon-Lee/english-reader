import React, { useMemo, useState } from 'react'
import { Button, Card, Col, Descriptions, Form, Input, InputNumber, List, Modal, Row, Select, Space, Switch, Tag, Typography } from 'antd'
import { PlusOutlined } from '@ant-design/icons'

const { Paragraph, Text, Title } = Typography

function money(cents) { return `¥${(Number(cents || 0) / 100).toFixed(0)}` }

export default function CommerceAdmin({ products = [], planVersions = [], onCreateProduct, onCreateVersion, onPublishVersion, onSetProductActive }) {
  const [productOpen, setProductOpen] = useState(false)
  const [versionProduct, setVersionProduct] = useState(null)
  const [productForm] = Form.useForm()
  const [versionForm] = Form.useForm()
  const planOptions = useMemo(() => planVersions.filter(item => item.id !== 'free-v1').map(item => ({ value: item.id, label: `${item.name} · ${item.id}` })), [planVersions])

  const createProduct = async values => { await onCreateProduct?.(values); productForm.resetFields(); setProductOpen(false) }
  const openVersion = product => {
    const latest = product.versions?.[0]
    versionForm.setFieldsValue({
      name: latest?.name || '', shortName: latest?.shortName || '', tagline: latest?.tagline || '', description: latest?.description || '',
      durationDays: latest?.durationDays || 30, amountCents: latest?.amountCents || 0, planVersion: latest?.planVersion || 'advanced-v1',
      benefitsText: (latest?.benefits || []).join('\n'), featured: Boolean(latest?.featured),
    })
    setVersionProduct(product)
  }
  const createVersion = async values => {
    await onCreateVersion?.(versionProduct.id, { ...values, benefits: String(values.benefitsText || '').split('\n').map(value => value.trim()).filter(Boolean) })
    versionForm.resetFields(); setVersionProduct(null)
  }

  return <Card className="commerce-admin-card" title={<div><Title level={3}>商品与版本</Title><Paragraph>名称、价格、期限或权益有变化时创建新版本。历史订单继续引用购买时的旧版本。</Paragraph></div>} extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => setProductOpen(true)}>创建商品</Button>}>
    <Row gutter={[16, 16]}>{products.map(product => {
      const current = product.versions?.find(item => item.status === 'published')
      return <Col xs={24} xl={12} key={product.id}><Card className="commerce-product-card" title={<Space><Text strong>{current?.name || product.slug}</Text><Tag color={product.active ? 'success' : 'default'}>{product.active ? '销售中' : '已下架'}</Tag></Space>} extra={<Space><Button size="small" onClick={() => onSetProductActive?.(product.id, !product.active)}>{product.active ? '停止新售' : '恢复销售'}</Button><Button size="small" type="primary" onClick={() => openVersion(product)}>创建新版本</Button></Space>}>
        {current ? <Descriptions size="small" column={2}><Descriptions.Item label="当前版本">V{current.version}</Descriptions.Item><Descriptions.Item label="价格">{money(current.amountCents)}</Descriptions.Item><Descriptions.Item label="期限">{current.durationDays} 天</Descriptions.Item><Descriptions.Item label="权益版本">{current.planVersion}</Descriptions.Item><Descriptions.Item label="公开标识" span={2}>{product.slug}</Descriptions.Item></Descriptions> : <Text type="secondary">暂无已发布版本</Text>}
        <List className="commerce-version-list" size="small" header="版本历史" dataSource={product.versions || []} locale={{ emptyText: '暂无版本' }} renderItem={version => <List.Item actions={version.status === 'draft' ? [<Button key="publish" size="small" type="primary" onClick={() => Modal.confirm({ title: `发布 ${version.name} V${version.version}？`, content: '发布后，当前线上版本会停止新售，但历史订单和已有会员权益保持不变。', okText: '确认发布', cancelText: '取消', onOk: () => onPublishVersion?.(version.id) })}>发布</Button>] : []}><List.Item.Meta title={<Space><Text>{version.name} · V{version.version}</Text><Tag color={version.status === 'published' ? 'success' : version.status === 'draft' ? 'processing' : 'default'}>{version.status}</Tag></Space>} description={`${money(version.amountCents)} · ${version.durationDays} 天 · ${version.planVersion}`} /></List.Item>} />
      </Card></Col>
    })}</Row>

    <Modal title="创建商品" open={productOpen} onCancel={() => setProductOpen(false)} onOk={() => productForm.submit()} okText="创建"><Form form={productForm} layout="vertical" onFinish={createProduct}><Form.Item label="公开标识" name="slug" extra="创建后保持稳定，例如 advanced-90。" rules={[{ required: true }]}><Input placeholder="advanced-90" /></Form.Item><Form.Item label="商品系列" name="family" rules={[{ required: true }]}><Input placeholder="advanced" /></Form.Item><Form.Item label="展示顺序" name="displayOrder" initialValue={100}><InputNumber min={0} style={{ width: '100%' }} /></Form.Item></Form></Modal>

    <Modal width={720} title={`为 ${versionProduct?.slug || ''} 创建新版本`} open={Boolean(versionProduct)} onCancel={() => setVersionProduct(null)} onOk={() => versionForm.submit()} okText="保存草稿"><Form form={versionForm} layout="vertical" onFinish={createVersion}><Row gutter={12}><Col span={14}><Form.Item label="商品名称" name="name" rules={[{ required: true }]}><Input placeholder="进阶会员 90 天" /></Form.Item></Col><Col span={10}><Form.Item label="短名称" name="shortName" rules={[{ required: true }]}><Input placeholder="进阶 90 天" /></Form.Item></Col></Row><Form.Item label="核心卖点" name="tagline" rules={[{ required: true }]}><Input placeholder="一句话说明用户为什么需要它" /></Form.Item><Form.Item label="商品说明" name="description" rules={[{ required: true }]}><Input.TextArea rows={3} /></Form.Item><Row gutter={12}><Col span={8}><Form.Item label="服务期限（天）" name="durationDays" rules={[{ required: true }]}><InputNumber min={1} max={3660} style={{ width: '100%' }} /></Form.Item></Col><Col span={8}><Form.Item label="售价（分）" name="amountCents" rules={[{ required: true }]}><InputNumber min={0} style={{ width: '100%' }} /></Form.Item></Col><Col span={8}><Form.Item label="权益版本" name="planVersion" rules={[{ required: true }]}><Select options={planOptions} /></Form.Item></Col></Row><Form.Item label="公开权益" name="benefitsText" extra="每行一项，至少 3 项。必须写清数量、单位或限制。" rules={[{ required: true }]}><Input.TextArea rows={7} /></Form.Item><Form.Item label="设为推荐方案" name="featured" valuePropName="checked"><Switch /></Form.Item></Form></Modal>
  </Card>
}
