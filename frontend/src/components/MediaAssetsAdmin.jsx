import React, { useEffect, useState } from 'react'
import { Alert, Button, Card, Col, DatePicker, Modal, Row, Segmented, Skeleton, Space, Statistic, Table, Tag, Typography } from 'antd'
import { AudioOutlined, CalendarOutlined, DatabaseOutlined, FileOutlined, FolderOutlined, LineChartOutlined, ReloadOutlined, VideoCameraOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { getJson } from '../api/client'
import AdminTelemetryChart, { formatBytes as bytes } from './AdminTelemetryChart'

const { Text, Paragraph } = Typography
const icon = type => String(type).startsWith('audio/') ? <AudioOutlined /> : String(type).startsWith('video/') ? <VideoCameraOutlined /> : <FileOutlined />
const dateTime = value => value ? new Date(value).toLocaleString('zh-CN') : '—'

export default function MediaAssetsAdmin() {
  const [users, setUsers] = useState([]), [total, setTotal] = useState(0), [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true), [error, setError] = useState(''), [refresh, setRefresh] = useState(0)
  const [selected, setSelected] = useState(null), [assets, setAssets] = useState([]), [assetTotal, setAssetTotal] = useState(0), [assetPage, setAssetPage] = useState(1)
  const [detailLoading, setDetailLoading] = useState(false), [detailError, setDetailError] = useState('')
  const [period, setPeriod] = useState('day'), [range, setRange] = useState(null), [metric, setMetric] = useState('bytes')
  const [statistics, setStatistics] = useState(null), [statsLoading, setStatsLoading] = useState(true), [statsError, setStatsError] = useState('')
  useEffect(() => {
    let disposed = false
    setLoading(true); setError('')
    getJson(`/api/admin/media-assets?limit=10&offset=${(page - 1) * 10}`)
      .then(result => { if (!disposed) { setUsers(result.users || []); setTotal(result.total || 0) } })
      .catch(e => { if (!disposed) setError(e.message) }).finally(() => { if (!disposed) setLoading(false) })
    return () => { disposed = true }
  }, [page, refresh])
  useEffect(() => {
    let disposed = false
    setStatsLoading(true); setStatsError(''); setStatistics(null)
    const query = new URLSearchParams({ period })
    if (range?.length === 2) { query.set('start', range[0].format('YYYY-MM-DD')); query.set('end', range[1].format('YYYY-MM-DD')) }
    getJson(`/api/admin/media-assets/statistics?${query}`)
      .then(result => { if (!disposed) setStatistics(result) })
      .catch(e => { if (!disposed) setStatsError(e.message) }).finally(() => { if (!disposed) setStatsLoading(false) })
    return () => { disposed = true }
  }, [period, range, refresh])
  useEffect(() => {
    if (!selected) return undefined
    let disposed = false
    setDetailLoading(true); setDetailError(''); setAssets([])
    getJson(`/api/admin/media-assets?ownerId=${encodeURIComponent(selected.id)}&limit=10&offset=${(assetPage - 1) * 10}`)
      .then(result => { if (!disposed) { setAssets(result.assets || []); setAssetTotal(result.total || 0) } })
      .catch(e => { if (!disposed) setDetailError(e.message) }).finally(() => { if (!disposed) setDetailLoading(false) })
    return () => { disposed = true }
  }, [selected, assetPage, refresh])
  const summary = statistics?.summary
  const reload = () => setRefresh(value => value + 1)
  return <Space direction="vertical" size={20} style={{ width: '100%' }}>
    <Card title={<Space><DatabaseOutlined />资源占用</Space>} extra={<Button icon={<ReloadOutlined />} loading={loading || statsLoading} onClick={reload}>刷新媒体资产</Button>}>
      {statsError ? <Alert type="error" showIcon message={statsError} action={<Button onClick={reload}>重试统计</Button>} /> : statsLoading ? <Skeleton active paragraph={{ rows: 2 }} /> : summary && <>
        <Row gutter={[24, 16]}>
          {[['总占用空间', bytes(summary.totalBytes), <DatabaseOutlined />], ['源文件', bytes(summary.originalBytes), <FileOutlined />], ['衍生文件', bytes(summary.generatedBytes), <AudioOutlined />], ['资产数量', `${summary.assetCount} 个`, <FolderOutlined />]].map(([title, value, prefix]) => <Col span={6} key={title}><Statistic title={title} value={value} prefix={prefix} /></Col>)}
        </Row>
        <Paragraph type="secondary" style={{ marginTop: 20, marginBottom: 0 }}>当前有效资产 {summary.assetCount} 个，衍生文件 {summary.variantCount} 个，来自 {summary.ownerCount} 位用户。私人 {bytes(summary.privateBytes)} / 官方 {bytes(summary.officialBytes)}。以上为数据库登记占用；服务器磁盘实际使用量见“服务器观测”。</Paragraph>
      </>}
    </Card>
    <Card title={<Space><LineChartOutlined />导入增长</Space>} extra={<Segmented aria-label="增长统计指标" value={metric} onChange={setMetric} options={[{ label: '登记空间', value: 'bytes' }, { label: '资产数量', value: 'assets' }]} />}>
      <Space wrap style={{ marginBottom: 16 }}>
        <CalendarOutlined />
        <Segmented aria-label="导入统计周期" value={period} onChange={value => { setPeriod(value); setRange(null) }} options={[{ label: '按天', value: 'day' }, { label: '按月', value: 'month' }, { label: '按年', value: 'year' }]} />
        <DatePicker.RangePicker aria-label="导入统计日期范围" value={range} onChange={setRange} disabledDate={value => value && value.isAfter(dayjs(), 'day')} />
        <Text type="secondary">{statistics ? `${statistics.start} 至 ${statistics.end}` : '读取中…'} · 北京时间</Text>
      </Space>
      {statsError ? <Alert type="error" message={statsError} action={<Button onClick={reload}>重试统计</Button>} /> : statsLoading ? <Skeleton active /> : statistics && <AdminTelemetryChart key={`${period}-${metric}-${statistics.start}-${statistics.end}`} points={statistics.history.map(point => ({ ...point, label: period === 'year' ? point.date.slice(0, 4) : period === 'month' ? point.date.slice(0, 7) : point.date.slice(5) }))} valueKey={metric} labelKey="label" label={metric === 'bytes' ? '新增登记空间' : '新增资产'} format={metric === 'bytes' ? bytes : value => `${Math.round(value)} 个`} />}
      <Paragraph type="secondary" style={{ marginTop: 16, marginBottom: 0 }}>默认最近 30 天、12 个月或 5 年。源文件与衍生文件按各自登记时间计入，包含已删除资源的历史记录；图表展示新增量，非磁盘净增长。</Paragraph>
    </Card>
    <Card title="按用户查看资源">
      {error ? <Alert type="error" message={error} action={<Button onClick={reload}>重试列表</Button>} /> : <Table rowKey="id" loading={loading} dataSource={users} locale={{ emptyText: '暂无用户媒体资产' }} pagination={{ current: page, pageSize: 10, total, showSizeChanger: false, onChange: setPage }} columns={[
        { title: '用户', render: (_, row) => <Space direction="vertical" size={0}><Text>{row.displayName || row.email}</Text><Text type="secondary">{row.email}</Text></Space> },
        { title: '总占用', dataIndex: 'totalBytes', render: bytes },
        { title: '私人内容', dataIndex: 'privateBytes', render: bytes }, { title: '官方内容', dataIndex: 'officialBytes', render: bytes },
        { title: '资源数', dataIndex: 'assetCount' }, { title: '含音频', dataIndex: 'audioCount' }, { title: '视频数', dataIndex: 'videoCount' },
        { title: '操作', render: (_, row) => <Button onClick={() => { setAssetPage(1); setAssetTotal(0); setSelected(row) }}>查看资源</Button> },
      ]} />}
    </Card>
    <Modal title={`${selected?.displayName || selected?.email || ''} · 媒体资源`} open={Boolean(selected)} onCancel={() => setSelected(null)} footer={null} width={1120}>
      <Paragraph>包含音频、视频、EPUB、PDF 等源文件。展开资源可查看 MP3、字幕、封面等衍生文件的格式、大小和路径。</Paragraph>
      {detailError ? <Alert type="error" message={detailError} action={<Button onClick={reload}>重试资源</Button>} /> : <Table rowKey="id" loading={detailLoading} dataSource={assets} locale={{ emptyText: '该用户暂无有效媒体资源' }} pagination={{ current: assetPage, pageSize: 10, total: assetTotal, showSizeChanger: false, onChange: setAssetPage }} columns={[
        { title: '资源', render: (_, row) => <Space align="start">{icon(row.contentType)}<Space direction="vertical" size={0}><Text strong>{row.title}</Text><Text type="secondary">{row.filename}</Text><Text type="secondary">{row.contentType}</Text><Text type="secondary">{dateTime(row.createdAt)}</Text></Space></Space> },
        { title: '范围', dataIndex: 'scope', render: value => <Tag>{value === 'official' ? '官方' : '私人'}</Tag> },
        { title: '大小', render: (_, row) => <Space direction="vertical" size={0}><span>{bytes(row.originalBytes + row.generatedBytes)}</span><Text type="secondary">源文件 {bytes(row.originalBytes)}<br />衍生 {bytes(row.generatedBytes)}</Text></Space> },
        { title: '资源路径', dataIndex: 'storagePath', render: value => <Text code style={{ overflowWrap: 'anywhere' }}>{value}</Text> },
      ]} expandable={{ expandedRowRender: row => <Table size="small" rowKey="name" pagination={false} dataSource={row.variants} locale={{ emptyText: '暂无衍生文件' }} columns={[
        { title: '衍生文件', render: (_, item) => <Space>{icon(item.contentType)}<Text>{item.name === 'audio' ? '朗读音频' : item.name}</Text></Space> },
        { title: '格式', dataIndex: 'contentType' }, { title: '大小', dataIndex: 'bytes', render: bytes },
        { title: '时长', dataIndex: 'duration', render: value => value == null ? '—' : `${Number(value).toFixed(1)} 秒` },
        { title: '文件路径', dataIndex: 'storagePath', render: value => <Text code style={{ overflowWrap: 'anywhere' }}>{value}</Text> },
      ]} /> }} />}
    </Modal>
  </Space>
}
