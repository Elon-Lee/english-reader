import React, { useEffect, useState } from 'react'
import { Alert, Button, Card, Form, Input, InputNumber, Modal, Select, Space, Table, Tag, message } from 'antd'
import { getJson, postJson } from '../api/client'

export default function RedemptionAdmin({ products = [] }) {
  const [batches, setBatches] = useState([])
  const [loading, setLoading] = useState(false)
  const [creating, setCreating] = useState(false)
  const [codes, setCodes] = useState(null)
  const [form] = Form.useForm()
  const [messageApi, contextHolder] = message.useMessage()
  const published = products.flatMap(product => (product.versions || []).filter(version => version.status === 'published' && Number(version.amountCents) > 0).map(version => ({ ...version, slug: product.slug })))

  const load = async () => {
    setLoading(true)
    try { const result = await getJson('/api/admin/commerce/redemption-batches?limit=100', { batches: [] }); setBatches(result.batches || []) }
    catch (error) { messageApi.error(error.message || '读取兑换库存批次失败') }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const generate = async values => {
    setCreating(true)
    try {
      const result = await postJson('/api/admin/commerce/redemption-batches', values)
      setCodes(result); await load()
    } catch (error) { messageApi.error(error.message || '生成兑换码失败') }
    finally { setCreating(false) }
  }
  const download = () => {
    const blob = new Blob([codes.codes.join('\n') + '\n'], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob); const link = document.createElement('a')
    link.href = url; link.download = `${codes.batchId}.txt`; link.click(); URL.revokeObjectURL(url)
  }
  const columns = [
    { title: '批次', dataIndex: 'id', render: value => <code>{value}</code> },
    { title: '套餐', dataIndex: 'productName' },
    { title: '价格', dataIndex: 'amountCents', render: value => `¥${(value / 100).toFixed(0)}` },
    { title: '总数', dataIndex: 'generatedCount' },
    { title: '可用', dataIndex: 'activeCount', render: value => <Tag color="green">{value}</Tag> },
    { title: '已兑换', dataIndex: 'redeemedCount' },
    { title: '已作废', dataIndex: 'revokedCount' },
    { title: '创建时间', dataIndex: 'createdAt', render: value => new Date(value).toLocaleString('zh-CN') },
  ]

  return <>
    {contextHolder}
    <Card title="兑换码库存" extra={<Button onClick={load}>刷新</Button>}>
      <Alert showIcon type="warning" message="兑换码是实际会员权益凭证" description="仅为已发布套餐生成。生成后明文只展示一次；安全保存导出文件，并仅上传到对应云猫商品库存。已发给买家的兑换码不能再次分配。" />
      <Form layout="inline" form={form} onFinish={generate} style={{ margin: '16px 0' }}>
        <Form.Item label="套餐" name="productVersionId" rules={[{ required: true }]}><Select style={{ width: 250 }} placeholder="选择已发布月卡" options={published.map(item => ({ value: item.id, label: `${item.name} · ¥${(item.amountCents / 100).toFixed(0)}` }))} /></Form.Item>
        <Form.Item label="数量" name="count" initialValue={20} rules={[{ required: true }]}><InputNumber min={1} max={5000} /></Form.Item>
        <Form.Item label="批次备注" name="note"><Input placeholder="例如：云猫首批库存" /></Form.Item>
        <Button type="primary" htmlType="submit" loading={creating} disabled={!published.length}>生成并导出兑换码</Button>
      </Form>
      <Table rowKey="id" size="small" loading={loading} columns={columns} dataSource={batches} pagination={{ pageSize: 10 }} />
    </Card>
    <Modal width={760} title="兑换码已生成，请立即导出" open={Boolean(codes)} onCancel={() => setCodes(null)} footer={<Space><Button onClick={() => { navigator.clipboard?.writeText(codes?.codes.join('\n') || ''); messageApi.success('兑换码已复制') }}>复制全部</Button><Button type="primary" onClick={download}>下载 TXT</Button><Button onClick={() => setCodes(null)}>关闭</Button></Space>}>
      <Alert showIcon type="error" message="明文不会再次显示" description="将 TXT 导入刚才选择的云猫商品后，安全删除本地导出文件；不要把码发入群聊、工单或日志。" />
      <Input.TextArea readOnly rows={10} value={codes?.codes.join('\n') || ''} style={{ marginTop: 12, fontFamily: 'monospace' }} />
    </Modal>
  </>
}
