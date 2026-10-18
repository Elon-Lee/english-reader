import React, { useEffect, useState } from 'react'
import { Alert, Button, Card, Modal, Select, Space, Table, Tag, Typography } from 'antd'
import { deleteJson, getJson, postJson } from '../api/client'

export default function MediaAssetsAdmin({ messageApi }) {
  const [assets, setAssets] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [scope, setScope] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [working, setWorking] = useState(false)
  const [scan, setScan] = useState(null)
  const load = async () => {
    setLoading(true); setError('')
    try {
      const result = await getJson(`/api/admin/media-assets?limit=10&offset=${(page - 1) * 10}&scope=${scope}`)
      setAssets(result.assets || []); setTotal(result.total || 0)
    } catch (e) { setError(e.message) } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [page, scope])
  const perform = async action => {
    setWorking(true)
    try { await action(); await load() }
    catch (e) { messageApi.error(e.message); throw e }
    finally { setWorking(false) }
  }
  const remove = asset => Modal.confirm({ title: '标记删除该媒体资产？', content: `${asset.storagePath}。删除后将无法继续播放，文件进入待清理状态。`, okText: '标记删除', cancelText: '取消', okButtonProps: { danger: true }, onOk: () => perform(async () => { await deleteJson(`/api/media/${encodeURIComponent(asset.id)}`); messageApi.success('媒体已标记删除') }) })
  const purge = dryRun => Modal.confirm({ title: dryRun ? '扫描待清理文件？' : '确认清理待删除文件？', content: dryRun ? '仅扫描，不移动文件。' : '待删除文件将移入媒体回收目录，该操作会记录审计日志。', okText: dryRun ? '开始扫描' : '执行清理', cancelText: '取消', okButtonProps: { danger: !dryRun }, onOk: () => perform(async () => { const result = await postJson('/api/admin/media-assets/purge', { dryRun }); setScan(result.files || []); messageApi.success(`${dryRun ? '扫描' : '清理'}完成：${result.files?.length || 0} 个文件`) }) })
  const columns = [
    { title: '资产', dataIndex: 'storagePath', render: (value, row) => <Space direction="vertical" size={0}><Typography.Text code>{value}</Typography.Text><Typography.Text type="secondary">{row.contentType}</Typography.Text></Space> },
    { title: '范围', dataIndex: 'scope', render: value => <Tag>{value === 'official' ? '官方' : '私人'}</Tag> },
    { title: '大小', render: (_, row) => `${((row.originalBytes + row.generatedBytes) / 1048576).toFixed(1)} MB` },
    { title: '状态', dataIndex: 'status', render: value => <Tag color={value === 'active' ? 'success' : 'default'}>{value === 'active' ? '正常' : '待清理'}</Tag> },
    { title: '操作', render: (_, row) => <Button danger disabled={working || row.status !== 'active'} onClick={() => remove(row)}>标记删除</Button> },
  ]
  return <Card title={`媒体资产（${total}）`} extra={<Space><Select aria-label="媒体范围" value={scope} onChange={value => { setScope(value); setPage(1) }} options={[{ value: '', label: '全部范围' }, { value: 'official', label: '官方媒体' }, { value: 'private', label: '私人媒体' }]} /><Button loading={loading} onClick={load}>刷新</Button></Space>}>
    <Space style={{ marginBottom: 16 }}><Button disabled={working} onClick={() => purge(true)}>扫描待清理文件</Button><Button danger disabled={working} onClick={() => purge(false)}>执行文件清理</Button></Space>
    {scan !== null && <Alert showIcon type="info" message={scan.length ? `待清理结果：${scan.length} 个文件` : '没有待清理文件'} style={{ marginBottom: 16 }} />}
    {error ? <Alert type="error" showIcon message={error} action={<Button onClick={load}>重试</Button>} /> : <Table rowKey="id" loading={loading} columns={columns} dataSource={assets} locale={{ emptyText: '暂无媒体资产' }} pagination={{ current: page, pageSize: 10, total, showSizeChanger: false, onChange: setPage }} />}
  </Card>
}
