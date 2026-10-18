import React, { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Col, Descriptions, Empty, Form, Input, InputNumber, List, Modal, Progress, Row, Select, Space, Switch, Table, Tabs, Tag, Typography } from 'antd'
import { CloudServerOutlined, DatabaseOutlined, ReloadOutlined, SafetyCertificateOutlined } from '@ant-design/icons'

import { getJson, postJson } from '../api/client'
import PageSkeleton from '../components/PageSkeleton'

const { Paragraph, Text, Title } = Typography

export default function PlatformOperationsPage({ messageApi }) {
  const [initialLoading, setInitialLoading] = useState(true)
  const [platformConfig, setPlatformConfig] = useState(null)
  const [deploy, setDeploy] = useState({ targets: [], jobs: [], status: {} })
  const [selectedTarget, setSelectedTarget] = useState(null)
  const [releases, setReleases] = useState([])
  const [contentReleases, setContentReleases] = useState([])
  const [busy, setBusy] = useState(false)
  const [nodeOpen, setNodeOpen] = useState(false)
  const [nodeForm] = Form.useForm()
  const [aiForm] = Form.useForm()

  const loadPlatform = async ({ initial = false } = {}) => {
    if (initial) setInitialLoading(true)
    try {
    const [configData, deploymentData] = await Promise.all([
      getJson('/api/admin/platform-config', null),
      getJson('/api/deployment/config', { targets: [], jobs: [], status: {} }),
    ])
    setPlatformConfig(configData)
    setDeploy(deploymentData || { targets: [], jobs: [], status: {} })
    const targetId = selectedTarget || deploymentData?.targets?.[0]?.id || null
    if (!selectedTarget && targetId) setSelectedTarget(targetId)
    if (targetId) {
      const [code, content] = await Promise.all([
        getJson(`/api/deployment/releases?targetId=${targetId}`, { releases: [] }),
        getJson(`/api/deployment/content-releases?targetId=${targetId}`, { releases: [] }),
      ])
      setReleases(code.releases || [])
      setContentReleases(content.releases || [])
    } else {
      setReleases([])
      setContentReleases([])
    }
    } finally {
      if (initial) setInitialLoading(false)
    }
  }

  useEffect(() => { loadPlatform({ initial: true }) }, [])
  useEffect(() => { if (platformConfig?.dioco) aiForm.setFieldsValue({ email: platformConfig.dioco.email || '', upstream: platformConfig.dioco.upstream || 'https://api-cdn-plus.dioco.io', token: '' }) }, [aiForm, platformConfig])
  useEffect(() => {
    if (!(deploy.jobs || []).some(job => ['queued', 'running'].includes(job.status))) return undefined
    const timer = setInterval(loadPlatform, 2000)
    return () => clearInterval(timer)
  }, [deploy.jobs])
  useEffect(() => {
    if (!selectedTarget) { setReleases([]); setContentReleases([]); return }
    Promise.all([
      getJson(`/api/deployment/releases?targetId=${selectedTarget}`, { releases: [] }),
      getJson(`/api/deployment/content-releases?targetId=${selectedTarget}`, { releases: [] }),
    ]).then(([code, content]) => { setReleases(code.releases || []); setContentReleases(content.releases || []) })
  }, [selectedTarget])

  const target = useMemo(() => deploy.targets.find(item => item.id === selectedTarget), [deploy.targets, selectedTarget])
  const refresh = async () => { setBusy(true); try { await loadPlatform(); messageApi.success('运营数据已刷新') } finally { setBusy(false) } }

  const cleanupAccounts = () => Modal.confirm({ title: '执行到期账户清理？', content: '仅处理已经超过宽限期的注销申请，并写入审计记录。', okText: '执行清理', okButtonProps: { danger: true }, onOk: async () => { const result = await postJson('/api/admin/account-deletions/cleanup', {}); messageApi.success(`账户清理完成：${result.completed || result.deleted || 0} 个`) } })

  const openNode = item => {
    nodeForm.setFieldsValue(item ? { id: item.id, name: item.name, host: item.host, port: item.port, username: item.username, remoteRoot: item.remote_root, servicePort: 5173, installRecording: Boolean(item.install_recording), useHttps: Boolean(item.use_https), password: '' } : { name: '生产节点', port: 22, username: 'root', remoteRoot: '/srv/shiyue', servicePort: 5173, installRecording: true, useHttps: true })
    setNodeOpen(true)
  }
  const saveNode = async values => { try { const result = await postJson('/api/deployment/config', values); setNodeOpen(false); setSelectedTarget(result.target.id); await loadPlatform(); messageApi.success('部署节点已保存') } catch (error) { messageApi.error(error.message); throw error } }
  const saveAiConfig = async values => { try { const result = await postJson('/api/admin/platform-config', values); setPlatformConfig(result); aiForm.setFieldValue('token', ''); messageApi.success('AI 服务配置已保存并立即生效') } catch (error) { messageApi.error(error.message); throw error } }
  const startJob = (action, payload = {}, danger = false) => {
    if (!selectedTarget) { messageApi.warning('请先选择部署节点'); return }
    const labels = { test: '连接测试', sync: '上传待审核内容', deploy: '首次部署', upgrade: '程序升级', cleanup: '远程清理' }
    Modal.confirm({ title: `确认启动${labels[action] || action}？`, content: action === 'sync' ? `目标节点：${target?.name || selectedTarget}。上传的新增或变更内容将设为未审核，请登录线上运营后台审核后发布到首页书城。` : `目标节点：${target?.name || selectedTarget}。发布来源是当前本机工作区；升级会备份远程数据库、执行并核验 SQL migrations 与基础数据，再验收候选版本后切换线上服务。`, okText: '启动任务', okButtonProps: { danger }, onOk: async () => { const endpoint = action === 'upgrade' ? 'saas-upgrade' : action; const result = await postJson(`/api/deployment/${endpoint}`, { targetId: selectedTarget, ...payload }); messageApi.success(`任务 #${result.jobId} 已启动`); await loadPlatform() } })
  }
  const rollback = (kind, releaseId) => {
    if (!releaseId) return
    const endpoint = kind === 'code' ? 'rollback' : 'content-rollback'
    Modal.confirm({ title: `回滚到 ${releaseId}？`, content: '该操作会切换远程线上版本，请确认已完成备份。', okText: '确认回滚', okButtonProps: { danger: true }, onOk: async () => { const result = await postJson(`/api/deployment/${endpoint}`, { targetId: selectedTarget, releaseId }); messageApi.success(`回滚任务 #${result.jobId} 已启动`); await loadPlatform() } })
  }

  const jobColumns = [
    { title: '任务', dataIndex: 'kind' }, { title: '节点', dataIndex: 'target_id' }, { title: '状态', dataIndex: 'status', render: value => <Tag color={value === 'complete' ? 'success' : value === 'failed' ? 'error' : 'processing'}>{value}</Tag> }, { title: '进度', render: (_, row) => <Progress percent={row.progress || 0} size="small" status={row.status === 'failed' ? 'exception' : undefined} /> }, { title: '步骤', dataIndex: 'step' }, { title: '失败原因', dataIndex: 'error', render: value => value ? <Text type="danger">{value}</Text> : '—' },
  ]

  const items = [
    { key: 'deployment', label: '部署节点', children: <Space direction="vertical" size={18} style={{ width: '100%' }}><Card title="节点与版本" extra={<Button type="primary" onClick={() => openNode(null)}>新增节点</Button>}><Row gutter={16}><Col span={8}><Select value={selectedTarget} onChange={setSelectedTarget} placeholder="选择部署节点" style={{ width: '100%' }} options={deploy.targets.map(item => ({ value: item.id, label: `${item.name} · ${item.host}` }))} /></Col><Col span={16}><Space wrap><Button disabled={!target} onClick={() => openNode(target)}>编辑节点</Button><Button disabled={!target} onClick={() => startJob('test')}>测试连接</Button><Button disabled={!target} onClick={() => startJob('sync')}>上传待审核内容</Button><Button disabled={!target} onClick={() => startJob('deploy')}>首次部署</Button><Button disabled={!target} onClick={() => startJob('upgrade')}>程序升级</Button><Button disabled={!target} onClick={() => startJob('cleanup', { retentionDays: 30 }, true)}>清理旧版本</Button></Space></Col></Row>{target && <Descriptions bordered size="small" column={3} style={{ marginTop: 18 }}><Descriptions.Item label="地址">{target.username}@{target.host}:{target.port}</Descriptions.Item><Descriptions.Item label="远程目录">{target.remote_root}</Descriptions.Item><Descriptions.Item label="服务端口">{target.service_port}</Descriptions.Item><Descriptions.Item label="认证">{target.passwordConfigured ? '已配置' : '未配置'}</Descriptions.Item><Descriptions.Item label="远程当前代码版本">{releases.find(item => item.status === 'current')?.releaseId || '无法读取'}</Descriptions.Item><Descriptions.Item label="内容版本">{deploy.status?.contentVersion || '—'}</Descriptions.Item></Descriptions>}</Card><Row gutter={16}><Col span={12}><Card title="代码回滚"><Select placeholder="选择历史代码版本" style={{ width: '100%' }} onChange={value => rollback('code', value)} options={releases.filter(item => item.status !== 'current').map(item => ({ value: item.releaseId, label: item.releaseId }))} /></Card></Col><Col span={12}><Card title="内容回滚"><Select placeholder="选择历史内容版本" style={{ width: '100%' }} onChange={value => rollback('content', value)} options={contentReleases.filter(item => item.status !== 'current').map(item => ({ value: item.releaseId, label: item.releaseId }))} /></Card></Col></Row><Card title="部署任务"><Table rowKey="id" columns={jobColumns} dataSource={deploy.jobs || []} pagination={{ pageSize: 8 }} scroll={{ x: 900 }} /></Card></Space> },
    { key: 'config', label: '平台配置', children: <Row gutter={16}><Col span={12}><Card title="AI 服务" extra={platformConfig?.dioco?.configured ? <Tag color="success">已配置 {platformConfig.dioco.tokenMask}</Tag> : <Tag color="warning">未配置</Tag>}><Form form={aiForm} layout="vertical" onFinish={saveAiConfig}><Form.Item label="服务邮箱" name="email" rules={[{ required: true, type: 'email', message: '请输入有效服务邮箱' }]}><Input /></Form.Item><Form.Item label="Dioco Token" name="token" extra="留空保持现有 Token；浏览器不会读取已保存的完整值。"><Input.Password placeholder={platformConfig?.dioco?.configured ? '已保存，留空保持不变' : '输入平台 Token'} /></Form.Item><Form.Item label="API 地址" name="upstream" rules={[{ required: true, type: 'url', message: '请输入有效 API 地址' }]}><Input /></Form.Item><Space><Button type="primary" htmlType="submit">保存并启用</Button>{platformConfig?.dioco?.configured && <Button danger onClick={() => Modal.confirm({ title: '清除 AI Token？', content: '清除后词汇语境和 AI 句法服务将停止工作。', okButtonProps: { danger: true }, onOk: async () => saveAiConfig({ ...aiForm.getFieldsValue(), clearToken: true }) })}>清除 Token</Button>}</Space></Form><Alert style={{ marginTop: 18 }} type="info" showIcon message="超级管理员配置保存在 PostgreSQL platform_settings 中，AI 请求即时读取，无需重启或修改 environment。" /></Card></Col><Col span={12}><Card title="运维原则"><Button danger onClick={cleanupAccounts} style={{ marginBottom: 16 }}>清理到期注销账户</Button><List dataSource={['所有高风险操作要求二次确认', '部署与内容回滚均产生任务记录', '媒体删除先标记，再执行可审计清理', '到期账户清理由管理员显式触发']} renderItem={item => <List.Item><SafetyCertificateOutlined style={{ color: '#2f6f50', marginRight: 8 }} />{item}</List.Item>} /></Card></Col></Row> },
  ]

  if (initialLoading) return <PageSkeleton />
  return <div className="page-stack"><div className="page-intro"><div><Text className="eyebrow">PLATFORM OPERATIONS</Text><Title level={1}>平台与部署</Title><Paragraph>管理平台配置和远程部署。内容审核及媒体资产请前往运营后台。</Paragraph></div><Button icon={<ReloadOutlined />} loading={busy} onClick={refresh}>刷新</Button></div><Tabs size="large" items={items} /><Modal title={nodeForm.getFieldValue('id') ? '编辑部署节点' : '新增部署节点'} open={nodeOpen} onCancel={() => setNodeOpen(false)} onOk={() => nodeForm.submit()} okText="保存节点"><Form form={nodeForm} layout="vertical" onFinish={saveNode}><Form.Item name="id" hidden><Input /></Form.Item><Row gutter={12}><Col span={12}><Form.Item label="节点名称" name="name" rules={[{ required: true }]}><Input /></Form.Item></Col><Col span={12}><Form.Item label="SSH 地址" name="host" rules={[{ required: true }]}><Input /></Form.Item></Col><Col span={8}><Form.Item label="SSH 端口" name="port"><InputNumber min={1} max={65535} style={{ width: '100%' }} /></Form.Item></Col><Col span={8}><Form.Item label="用户名" name="username"><Input /></Form.Item></Col><Col span={8}><Form.Item label="公网前台端口" name="servicePort"><InputNumber value={5173} disabled style={{ width: '100%' }} /></Form.Item></Col></Row><Form.Item label="远程目录" name="remoteRoot" rules={[{ required: true }]}><Input /></Form.Item><Form.Item label="SSH 密码（留空保持原配置）" name="password"><Input.Password /></Form.Item><Space><Form.Item label="启用 HTTPS" name="useHttps" valuePropName="checked"><Switch /></Form.Item><Form.Item label="安装录音能力" name="installRecording" valuePropName="checked"><Switch /></Form.Item></Space></Form></Modal></div>
}
