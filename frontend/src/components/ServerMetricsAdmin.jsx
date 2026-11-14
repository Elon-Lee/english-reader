import React, { useEffect, useState } from 'react'
import { Alert, Button, Card, Col, Descriptions, Progress, Row, Segmented, Skeleton, Space, Statistic, Switch, Typography } from 'antd'
import { CloudServerOutlined, DashboardOutlined, DatabaseOutlined, ReloadOutlined } from '@ant-design/icons'
import { getJson } from '../api/client'
import AdminTelemetryChart, { formatBytes as bytes } from './AdminTelemetryChart'

const { Text, Paragraph } = Typography
const percent = value => value == null ? '—' : `${Number(value).toFixed(1)}%`
const uptime = value => value == null ? '—' : `${Math.floor(value / 86400)} 天 ${Math.floor(value % 86400 / 3600)} 小时 ${Math.floor(value % 3600 / 60)} 分钟`

function Usage({ title, value, children, icon }) {
  return <Card size="small" title={<Space>{icon}{title}</Space>}><Statistic value={percent(value)} /><Progress percent={value == null ? 0 : Math.min(100, value)} showInfo={false} status={value >= 90 ? 'exception' : 'normal'} /><Text type="secondary">{children}</Text></Card>
}

export default function ServerMetricsAdmin() {
  const [data, setData] = useState(null), [loading, setLoading] = useState(true), [error, setError] = useState('')
  const [automatic, setAutomatic] = useState(true), [refresh, setRefresh] = useState(0), [metric, setMetric] = useState('cpu')
  useEffect(() => {
    let disposed = false, timer, inFlight = false
    const load = async () => {
      if (disposed || document.hidden || inFlight) return
      clearTimeout(timer); inFlight = true; setLoading(true)
      try { const result = await getJson('/api/admin/server-metrics'); if (!disposed) { setData(result); setError('') } }
      catch (e) { if (!disposed) setError(e.message || '服务器指标读取失败') }
      finally { inFlight = false; if (!disposed) { setLoading(false); if (automatic && !document.hidden) timer = setTimeout(load, 10000) } }
    }
    const visible = () => { clearTimeout(timer); if (!document.hidden) void load() }
    void load(); document.addEventListener('visibilitychange', visible)
    return () => { disposed = true; clearTimeout(timer); document.removeEventListener('visibilitychange', visible) }
  }, [automatic, refresh])
  const reload = () => setRefresh(value => value + 1)
  return <Space direction="vertical" size={20} style={{ width: '100%' }}>
    <Card title={<Space><CloudServerOutlined />当前应用服务器</Space>} extra={<Space><Text>每 10 秒刷新</Text><Switch aria-label="自动刷新服务器指标" checked={automatic} onChange={setAutomatic} /><Button icon={<ReloadOutlined />} loading={loading} onClick={reload}>刷新服务器指标</Button></Space>}>
      <Paragraph type="secondary">显示运行当前 API 的服务器指标；本地开发显示本机，部署后显示服务器运行环境。仅在本模块打开且页面可见时采样。</Paragraph>
      {error && <Alert type="error" showIcon message={error} description={data ? `保留上次采样：${new Date(data.sampledAt).toLocaleString('zh-CN')}` : undefined} action={<Button onClick={reload}>重试服务器指标</Button>} style={{ marginBottom: 16 }} />}
      {!data && loading ? <Skeleton active paragraph={{ rows: 4 }} /> : data && <>
        <Paragraph><Text strong>{data.platform} · {data.scope === 'container' ? '容器可见系统' : '主机'}</Text><Text type="secondary"> · 采样于 {new Date(data.sampledAt).toLocaleString('zh-CN')}</Text></Paragraph>
        {data.errors?.length > 0 && <Alert type="warning" showIcon message={`以下指标暂不可用：${data.errors.join('、')}`} style={{ marginBottom: 16 }} />}
        {data.scope === 'container' && <Alert type="info" showIcon message="系统指标按容器可见范围展示；容器限制单独列出。磁盘容量指所在文件系统，不等于本应用独占空间。" style={{ marginBottom: 16 }} />}
        <Row gutter={[16, 16]}>
          <Col span={12}><Usage title="CPU 使用率" value={data.cpu?.percent} icon={<DashboardOutlined />}>{data.cpu?.logicalCount ?? '—'} 个逻辑核心 · 负载（1 / 5 / 15 分钟）：{data.cpu?.loadAverage?.map(value => value.toFixed(2)).join(' / ') || '—'}</Usage></Col>
          <Col span={12}><Usage title="内存使用率" value={data.memory?.percent} icon={<DatabaseOutlined />}>已用 {bytes(data.memory?.used)} / 总量 {bytes(data.memory?.total)} · 可用 {bytes(data.memory?.available)}</Usage></Col>
          {data.disks?.map(disk => <Col span={12} key={disk.label}><Usage title={disk.label} value={disk.percent} icon={<DatabaseOutlined />}>{disk.available ? <>已用 {bytes(disk.used)} / 总量 {bytes(disk.total)} · 剩余 {bytes(disk.free)}<br /><Text code style={{ overflowWrap: 'anywhere' }}>{disk.path}</Text></> : '磁盘数据暂不可用'}</Usage></Col>)}
        </Row>
        <Descriptions size="small" column={2} style={{ marginTop: 20 }}>
          <Descriptions.Item label="系统运行时间">{uptime(data.uptimeSeconds)}</Descriptions.Item>
          <Descriptions.Item label="后端运行时间">{uptime(data.process?.uptimeSeconds)}</Descriptions.Item>
          <Descriptions.Item label="后端常驻内存">{bytes(data.process?.rss)}</Descriptions.Item>
          <Descriptions.Item label="交换空间">{bytes(data.swap?.used)} / {bytes(data.swap?.total)}</Descriptions.Item>
          <Descriptions.Item label="网络接收速率">{data.network?.receivePerSecond == null ? '等待下次采样' : `${bytes(data.network.receivePerSecond)}/s`}</Descriptions.Item>
          <Descriptions.Item label="网络发送速率">{data.network?.sendPerSecond == null ? '等待下次采样' : `${bytes(data.network.sendPerSecond)}/s`}</Descriptions.Item>
          {data.container?.cpuLimit != null && <Descriptions.Item label="容器 CPU 限制">{data.container.cpuLimit} 核</Descriptions.Item>}
          {data.container?.memory && <Descriptions.Item label="容器内存">{bytes(data.container.memory.used)} / {bytes(data.container.memory.total)}（{percent(data.container.memory.percent)}）</Descriptions.Item>}
        </Descriptions>
      </>}
    </Card>
    {data && <Card title="近期资源使用趋势" extra={<Segmented aria-label="服务器趋势指标" value={metric} onChange={setMetric} options={[{ label: 'CPU', value: 'cpu' }, { label: '内存', value: 'memory' }, { label: '媒体磁盘', value: 'disk' }]} />}>
      <AdminTelemetryChart key={metric} points={(data.history || []).map(point => ({ ...point, label: new Date(point.at).toLocaleTimeString('zh-CN', { hour12: false }) }))} valueKey={metric} labelKey="label" label={{ cpu: 'CPU 使用率', memory: '内存使用率', disk: '媒体磁盘使用率' }[metric]} format={percent} line fixedMax={100} />
      <Paragraph type="secondary" style={{ marginTop: 16, marginBottom: 0 }}>保留本服务最近 120 次采样，服务重启后清空。暂停刷新或离开页面会停止本页面的采样请求。</Paragraph>
    </Card>}
  </Space>
}
