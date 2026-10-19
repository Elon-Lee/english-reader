import React, { useEffect, useState } from 'react'
import { Alert, Button, Card, Modal, Space, Table, Tag, Typography } from 'antd'
import { getJson } from '../api/client'

const bytes = value => `${(Number(value || 0) / 1048576).toFixed(2)} MB`

export default function MediaAssetsAdmin() {
  const [users, setUsers] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState(null)
  const [videos, setVideos] = useState([])
  const [videoTotal, setVideoTotal] = useState(0)
  const [videoPage, setVideoPage] = useState(1)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')
  const load = async () => {
    setLoading(true); setError('')
    try {
      const result = await getJson(`/api/admin/media-assets?limit=10&offset=${(page - 1) * 10}`)
      setUsers(result.users || []); setTotal(result.total || 0)
    } catch (e) { setError(e.message) } finally { setLoading(false) }
  }
  useEffect(() => { void load() }, [page])
  useEffect(() => {
    if (!selected) return
    let disposed = false
    setDetailLoading(true); setDetailError(''); setVideos([])
    getJson(`/api/admin/media-assets?ownerId=${encodeURIComponent(selected.id)}&limit=10&offset=${(videoPage - 1) * 10}`)
      .then(result => { if (!disposed) { setVideos(result.videos || []); setVideoTotal(result.total || 0) } })
      .catch(e => { if (!disposed) setDetailError(e.message) })
      .finally(() => { if (!disposed) setDetailLoading(false) })
    return () => { disposed = true }
  }, [selected, videoPage])
  return <Card title="媒体资产" extra={<Button loading={loading} onClick={load}>刷新</Button>}>
    <Alert type="info" showIcon message="按用户汇总当前有效媒体占用，包含源文件与衍生文件。永久删除请在我的书架或运营后台的内容管理中操作。" style={{ marginBottom: 16 }} />
    {error ? <Alert type="error" message={error} action={<Button onClick={load}>重试</Button>} /> : <Table rowKey="id" loading={loading} dataSource={users} locale={{ emptyText: '暂无用户媒体资产' }} pagination={{ current: page, pageSize: 10, total, showSizeChanger: false, onChange: setPage }} columns={[
      { title: '用户', render: (_, row) => <Space direction="vertical" size={0}><Typography.Text>{row.displayName || row.email}</Typography.Text><Typography.Text type="secondary">{row.email}</Typography.Text></Space> },
      { title: '总占用', dataIndex: 'totalBytes', render: bytes },
      { title: '私人内容', dataIndex: 'privateBytes', render: bytes },
      { title: '官方内容', dataIndex: 'officialBytes', render: bytes },
      { title: '视频数', dataIndex: 'videoCount' },
      { title: '操作', render: (_, row) => <Button onClick={() => { setVideoPage(1); setVideoTotal(0); setSelected(row) }}>查看</Button> },
    ]} />}
    <Modal title={`${selected?.displayName || selected?.email || ''} · 导入视频`} open={Boolean(selected)} onCancel={() => setSelected(null)} footer={null} width={1000}>
      <Typography.Paragraph>当前总占用：{bytes(selected?.totalBytes)}，视频大小包含原文件、播放版本、音频、字幕与封面。</Typography.Paragraph>
      {detailError ? <Alert type="error" message={detailError} action={<Button onClick={() => setSelected({ ...selected })}>重试</Button>} /> : <Table rowKey="id" loading={detailLoading} dataSource={videos} locale={{ emptyText: '该用户暂无导入视频' }} pagination={{ current: videoPage, pageSize: 10, total: videoTotal, showSizeChanger: false, onChange: setVideoPage }} columns={[
        { title: '视频', dataIndex: 'title' },
        { title: '范围', dataIndex: 'scope', render: value => <Tag>{value === 'official' ? '官方' : '私人'}</Tag> },
        { title: '大小', render: (_, row) => <Space direction="vertical" size={0}><span>{bytes(row.originalBytes + row.generatedBytes)}</span><Typography.Text type="secondary">原文件 {bytes(row.originalBytes)} / 衍生 {bytes(row.generatedBytes)}</Typography.Text></Space> },
        { title: '内容路径', dataIndex: 'contentPath', render: value => <Typography.Text code style={{ overflowWrap: 'anywhere' }}>{value || '处理中，尚未生成内容'}</Typography.Text> },
        { title: '视频路径', dataIndex: 'storagePath', render: value => <Typography.Text code style={{ overflowWrap: 'anywhere' }}>{value}</Typography.Text> },
      ]} expandable={{ expandedRowRender: row => <Space direction="vertical">{row.variants.length ? row.variants.map(item => <Typography.Text key={item.name} code style={{ overflowWrap: 'anywhere' }}>{item.name} · {bytes(item.bytes)} · {item.storagePath}</Typography.Text>) : '暂无衍生文件'}</Space> }} />}
    </Modal>
  </Card>
}
