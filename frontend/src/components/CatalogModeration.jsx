import React, { useEffect, useState } from 'react'
import { Alert, Button, Card, Form, Input, InputNumber, Modal, Select, Space, Table, Tag } from 'antd'
import { getJson, postJson } from '../api/client'

const publications = [{ value: 'draft', label: '未审核' }, { value: 'published', label: '审核通过并发布' }, { value: 'archived', label: '已下架' }]
const rights = [{ value: 'private', label: '未确认 / 仅私人' }, { value: 'licensed', label: '已授权' }, { value: 'public_domain', label: '公版' }, { value: 'prohibited', label: '禁止发布' }]

export default function CatalogModeration({ messageApi }) {
  const [sources, setSources] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState(null)
  const [mode, setMode] = useState('review')
  const [saving, setSaving] = useState(false)
  const [filter, setFilter] = useState('all')
  const [form] = Form.useForm()
  const load = async () => {
    setLoading(true); setError('')
    try { setSources((await getJson('/api/admin/catalog/sources')).sources || []) }
    catch (e) { setError(e.message) }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])
  const edit = (row, nextMode) => {
    setMode(nextMode)
    form.resetFields()
    form.setFieldsValue({ ...row, tags: (row.tags || []).map(item => item.title), seriesTitle: row.series || '未分组' })
    setEditing(row)
  }
  const save = async values => {
    setSaving(true)
    try {
      await postJson('/api/admin/catalog/books', values)
      setEditing(null)
      messageApi.success(mode === 'edit' ? '内容信息已保存' : values.publicationStatus === 'published' ? '审核通过，已发布到首页书城' : '审核状态已保存')
      await load()
    } catch (e) { messageApi.error(e.message) }
    finally { setSaving(false) }
  }
  const submit = async () => {
    let values
    try { values = await form.validateFields() } catch { return }
    values = { ...editing, seriesTitle: editing.series || '未分组', tags: (editing.tags || []).map(item => item.title), ...values }
    if (mode === 'edit') { await save(values); return }
    if (values.publicationStatus === 'published') {
      Modal.confirm({ title: `确认发布《${values.title}》？`, content: '请确认已核实版权及内容质量。发布后，首页书城将向用户公开展示该读物。', okText: '审核通过并发布', cancelText: '返回检查', onOk: () => save(values) })
    } else if (editing.publicationStatus === 'published') {
      Modal.confirm({ title: '确认停止公开该读物？', content: '保存后将从首页书城隐藏，现有收藏也无法继续访问完整正文和媒体。', okText: '确认停止公开', cancelText: '取消', okButtonProps: { danger: true }, onOk: () => save(values) })
    } else await save(values)
  }
  const columns = [
    { title: '内容', dataIndex: 'title' },
    { title: '类型', dataIndex: 'resourceType' },
    { title: '版权', dataIndex: 'rightsStatus', render: value => rights.find(item => item.value === value)?.label || value },
    { title: '审核状态', dataIndex: 'publicationStatus', render: value => <Tag color={value === 'published' ? 'success' : value === 'draft' ? 'warning' : 'default'}>{publications.find(item => item.value === value)?.label || value}</Tag> },
    { title: '操作', render: (_, row) => <Space><Button onClick={() => edit(row, 'review')}>审核</Button><Button onClick={() => edit(row, 'edit')}>编辑</Button></Space> },
  ]
  return <Card title="内容审核" extra={<Space><Select aria-label="审核状态" value={filter} onChange={setFilter} options={[{ value: 'all', label: '全部状态' }, ...publications]} /><Button loading={loading} onClick={load}>刷新</Button></Space>}>
    <Alert type="info" showIcon message="本地内容上传后默认为未审核。请在此核实版权和内容，再选择审核通过并发布，读物才会出现在首页书城。" style={{ marginBottom: 16 }} />
    {error ? <Alert type="error" showIcon message={error} action={<Button onClick={load}>重试</Button>} /> : <Table loading={loading} rowKey="sourceBookId" columns={columns} dataSource={sources.filter(row => filter === 'all' || row.publicationStatus === filter)} pagination={{ pageSize: 10 }} locale={{ emptyText: '暂无待审核内容' }} />}
    <Modal title={editing ? `${mode === 'review' ? '审核' : '编辑'}《${editing.title}》` : '内容审核'} open={Boolean(editing)} onCancel={() => { if (!saving) setEditing(null) }} onOk={submit} confirmLoading={saving} okText={mode === 'review' ? '保存审核结果' : '保存内容信息'} cancelText="取消" width={620}>
      <Form form={form} layout="vertical">
        <Form.Item name="sourceBookId" hidden><Input /></Form.Item>
        {mode === 'edit' ? <>
        <Form.Item name="title" label="标题" rules={[{ required: true, whitespace: true }]}><Input /></Form.Item>
        <Form.Item name="englishTitle" label="英文标题"><Input /></Form.Item>
        <Form.Item name="author" label="作者"><Input /></Form.Item>
        <Form.Item name="description" label="简介"><Input.TextArea rows={3} /></Form.Item>
        <Form.Item name="seriesTitle" label="系列"><Input /></Form.Item>
        <Form.Item name="level" label="等级"><Input /></Form.Item>
        <Form.Item name="tags" label="标签"><Select mode="tags" /></Form.Item>
        <Form.Item name="featuredRank" label="推荐排序"><InputNumber min={0} /></Form.Item>
        </> : <>
        <Alert type="info" message={`当前审核内容：${editing?.title || ''}`} style={{ marginBottom: 16 }} />
        <Form.Item name="rightsStatus" label="版权状态" rules={[{ required: true }]}><Select options={rights} /></Form.Item>
        <Form.Item name="publicationStatus" label="审核结果" rules={[{ required: true }, ({ getFieldValue }) => ({ validator: (_, value) => value === 'published' && !['licensed', 'public_domain'].includes(getFieldValue('rightsStatus')) ? Promise.reject(new Error('发布前必须确认内容为公版或已授权')) : Promise.resolve() })]} dependencies={['rightsStatus']}><Select options={publications} /></Form.Item>
        </>}
      </Form>
    </Modal>
  </Card>
}
