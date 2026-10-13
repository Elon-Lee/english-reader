import React, { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Col, Descriptions, Empty, Form, Input, InputNumber, List, Modal, Progress, Row, Select, Space, Switch, Table, Tabs, Tag, Typography } from 'antd'
import { CloudServerOutlined, DatabaseOutlined, ReloadOutlined, SafetyCertificateOutlined } from '@ant-design/icons'

import { deleteJson, getJson, postJson } from '../api/client'
import PageSkeleton from '../components/PageSkeleton'

const { Paragraph, Text, Title } = Typography

export default function PlatformOperationsPage({ messageApi }) {
  const [initialLoading, setInitialLoading] = useState(true)
  const [catalog, setCatalog] = useState([])
  const [assets, setAssets] = useState([])
  const [assetTotal, setAssetTotal] = useState(0)
  const [platformConfig, setPlatformConfig] = useState(null)
  const [deploy, setDeploy] = useState({ targets: [], jobs: [], status: {} })
  const [selectedTarget, setSelectedTarget] = useState(null)
  const [releases, setReleases] = useState([])
  const [contentReleases, setContentReleases] = useState([])
  const [busy, setBusy] = useState(false)
  const [nodeOpen, setNodeOpen] = useState(false)
  const [nodeForm] = Form.useForm()
  const [reviewForm] = Form.useForm()
  const [aiForm] = Form.useForm()

  const loadPlatform = async ({ initial = false } = {}) => {
    if (initial) setInitialLoading(true)
    try {
    const [catalogData, assetData, configData, deploymentData] = await Promise.all([
      getJson('/api/admin/catalog/sources', { sources: [] }),
      getJson('/api/admin/media-assets?limit=50', { assets: [], total: 0 }),
      getJson('/api/admin/platform-config', null),
      getJson('/api/deployment/config', { targets: [], jobs: [], status: {} }),
    ])
    setCatalog(catalogData.sources || [])
    setAssets(assetData.assets || [])
    setAssetTotal(assetData.total || 0)
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

  const reviewCatalog = async values => {
    try {
      await postJson('/api/admin/catalog/books', values)
      reviewForm.resetFields()
      await loadPlatform()
      messageApi.success('书城审核状态已更新')
    } catch (error) { messageApi.error(error.message) }
  }

  const removeAsset = asset => Modal.confirm({ title: '标记删除该媒体资产？', content: asset.storagePath, okText: '标记删除', okButtonProps: { danger: true }, onOk: async () => { await deleteJson(`/api/media/${encodeURIComponent(asset.id)}`); await loadPlatform(); messageApi.success('媒体资产已进入待清理状态') } })
  const purgeAssets = dryRun => Modal.confirm({ title: dryRun ? '扫描待清理媒体？' : '执行媒体文件清理？', content: dryRun ? '只生成待清理清单，不移动文件。' : '文件会移动到本地媒体回收目录，该动作会写入审计记录。', okText: dryRun ? '开始扫描' : '执行清理', okButtonProps: { danger: !dryRun }, onOk: async () => { const result = await postJson('/api/admin/media-assets/purge', { dryRun }); messageApi.success(`${dryRun ? '扫描' : '清理'}完成：${result.files?.length || 0} 个文件`) } })
  const cleanupAccounts = () => Modal.confirm({ title: '执行到期账户清理？', content: '仅处理已经超过宽限期的注销申请，并写入审计记录。', okText: '执行清理', okButtonProps: { danger: true }, onOk: async () => { const result = await postJson('/api/admin/account-deletions/cleanup', {}); messageApi.success(`账户清理完成：${result.completed || result.deleted || 0} 个`) } })

  const openNode = item => {
    nodeForm.setFieldsValue(item ? { id: item.id, name: item.name, host: item.host, port: item.port, username: item.username, remoteRoot: item.remote_root, servicePort: item.service_port, installRecording: Boolean(item.install_recording), useHttps: Boolean(item.use_https), password: '' } : { name: '生产节点', port: 22, username: 'root', remoteRoot: '/srv/shiyue', servicePort: 8765, installRecording: true, useHttps: true })
    setNodeOpen(true)
  }
  const saveNode = async values => { try { const result = await postJson('/api/deployment/config', values); setNodeOpen(false); setSelectedTarget(result.target.id); await loadPlatform(); messageApi.success('部署节点已保存') } catch (error) { messageApi.error(error.message); throw error } }
  const saveAiConfig = async values => { try { const result = await postJson('/api/admin/platform-config', values); setPlatformConfig(result); aiForm.setFieldValue('token', ''); messageApi.success('AI 服务配置已保存并立即生效') } catch (error) { messageApi.error(error.message); throw error } }
  const startJob = (action, payload = {}, danger = false) => {
    if (!selectedTarget) { messageApi.warning('请先选择部署节点'); return }
    const labels = { test: '连接测试', sync: '资源同步', deploy: '首次部署', upgrade: '程序升级', cleanup: '远程清理' }
    Modal.confirm({ title: `确认启动${labels[action] || action}？`, content: `目标节点：${target?.name || selectedTarget}。任务启动后可在下方查看状态。`, okText: '启动任务', okButtonProps: { danger }, onOk: async () => { const result = await postJson(`/api/deployment/${action}`, { targetId: selectedTarget, ...payload }); messageApi.success(`任务 #${result.jobId} 已启动`); await loadPlatform() } })
  }
  const rollback = (kind, releaseId) => {
    if (!releaseId) return
    const endpoint = kind === 'code' ? 'rollback' : 'content-rollback'
    Modal.confirm({ title: `回滚到 ${releaseId}？`, content: '该操作会切换远程线上版本，请确认已完成备份。', okText: '确认回滚', okButtonProps: { danger: true }, onOk: async () => { const result = await postJson(`/api/deployment/${endpoint}`, { targetId: selectedTarget, releaseId }); messageApi.success(`回滚任务 #${result.jobId} 已启动`); await loadPlatform() } })
  }

  const catalogColumns = [
    { title: '内容', dataIndex: 'title', render: (value, row) => <Space direction="vertical" size={0}><Text strong>{value}</Text><Text type="secondary">{row.englishTitle || row.sourceBookId}</Text></Space> },
    { title: '类型', dataIndex: 'resourceType', render: value => <Tag>{value}</Tag> },
    { title: '版权', dataIndex: 'rightsStatus', render: value => <Tag color={['licensed', 'public_domain'].includes(value) ? 'success' : 'warning'}>{value}</Tag> },
    { title: '发布', dataIndex: 'publicationStatus', render: value => <Tag color={value === 'published' ? 'success' : 'default'}>{value}</Tag> },
    { title: '操作', render: (_, row) => <Button size="small" onClick={() => { reviewForm.setFieldsValue({ sourceBookId: row.sourceBookId, rightsStatus: row.rightsStatus === 'private' ? 'licensed' : row.rightsStatus, publicationStatus: row.publicationStatus, title: row.title, englishTitle: row.englishTitle, series: row.series, level: row.level, resourceType: row.resourceType }); Modal.confirm({ width: 620, title: `审核《${row.title}》`, content: <Form form={reviewForm} layout="vertical" onFinish={reviewCatalog}><Form.Item name="sourceBookId" hidden><Input /></Form.Item><Row gutter={12}><Col span={12}><Form.Item label="版权状态" name="rightsStatus" rules={[{ required: true }]}><Select options={[{ value: 'licensed', label: '已授权' }, { value: 'public_domain', label: '公版' }, { value: 'private', label: '仅私人' }, { value: 'prohibited', label: '禁止发布' }]} /></Form.Item></Col><Col span={12}><Form.Item label="发布状态" name="publicationStatus" rules={[{ required: true }]}><Select options={[{ value: 'draft', label: '草稿' }, { value: 'published', label: '已发布' }, { value: 'archived', label: '已下架' }]} /></Form.Item></Col></Row><Form.Item label="中文标题" name="title"><Input /></Form.Item><Form.Item label="英文标题" name="englishTitle"><Input /></Form.Item><Row gutter={12}><Col span={8}><Form.Item label="系列" name="series"><Input /></Form.Item></Col><Col span={8}><Form.Item label="等级" name="level"><Input /></Form.Item></Col><Col span={8}><Form.Item label="资源类型" name="resourceType"><Input /></Form.Item></Col></Row></Form>, onOk: () => reviewForm.submit() }) }}>审核</Button> },
  ]
  const assetColumns = [
    { title: '资产', dataIndex: 'storagePath', ellipsis: true, render: (value, row) => <Space direction="vertical" size={0}><Text code>{value}</Text><Text type="secondary">{row.contentType}</Text></Space> },
    { title: '范围', dataIndex: 'scope', render: value => <Tag color={value === 'official' ? 'gold' : 'green'}>{value}</Tag> },
    { title: '大小', render: (_, row) => `${((row.originalBytes + row.generatedBytes) / 1024 / 1024).toFixed(1)} MB` },
    { title: '状态', dataIndex: 'status', render: value => <Tag color={value === 'active' ? 'success' : 'default'}>{value}</Tag> },
    { title: '操作', render: (_, row) => <Button size="small" danger disabled={row.status !== 'active'} onClick={() => removeAsset(row)}>标记删除</Button> },
  ]
  const jobColumns = [
    { title: '任务', dataIndex: 'kind' }, { title: '节点', dataIndex: 'target_id' }, { title: '状态', dataIndex: 'status', render: value => <Tag color={value === 'complete' ? 'success' : value === 'failed' ? 'error' : 'processing'}>{value}</Tag> }, { title: '进度', render: (_, row) => <Progress percent={row.progress || 0} size="small" status={row.status === 'failed' ? 'exception' : undefined} /> }, { title: '步骤', dataIndex: 'step' },
  ]

  const items = [
    { key: 'catalog', label: '内容审核', children: <Card title="书城内容源" extra={<Text type="secondary">{catalog.length} 条</Text>}><Table rowKey="sourceBookId" columns={catalogColumns} dataSource={catalog} pagination={{ pageSize: 10 }} scroll={{ x: 900 }} /></Card> },
    { key: 'media', label: '媒体资产', children: <Space direction="vertical" size={18} style={{ width: '100%' }}><Row gutter={16}><Col span={8}><Card><Descriptions column={1}><Descriptions.Item label="资产总数">{assetTotal}</Descriptions.Item><Descriptions.Item label="当前列表">{assets.length}</Descriptions.Item></Descriptions></Card></Col><Col span={16}><Card><Space><Button icon={<DatabaseOutlined />} onClick={() => purgeAssets(true)}>扫描待清理文件</Button><Button danger onClick={() => purgeAssets(false)}>执行文件清理</Button><Button danger onClick={cleanupAccounts}>清理到期注销账户</Button></Space></Card></Col></Row><Card><Table rowKey="id" columns={assetColumns} dataSource={assets} pagination={{ pageSize: 10 }} scroll={{ x: 900 }} /></Card></Space> },
    { key: 'deployment', label: '部署节点', children: <Space direction="vertical" size={18} style={{ width: '100%' }}><Card title="节点与版本" extra={<Button type="primary" onClick={() => openNode(null)}>新增节点</Button>}><Row gutter={16}><Col span={8}><Select value={selectedTarget} onChange={setSelectedTarget} placeholder="选择部署节点" style={{ width: '100%' }} options={deploy.targets.map(item => ({ value: item.id, label: `${item.name} · ${item.host}` }))} /></Col><Col span={16}><Space wrap><Button disabled={!target} onClick={() => openNode(target)}>编辑节点</Button><Button disabled={!target} onClick={() => startJob('test')}>测试连接</Button><Button disabled={!target} onClick={() => startJob('sync')}>同步资源</Button><Button disabled={!target} onClick={() => startJob('deploy')}>首次部署</Button><Button disabled={!target} onClick={() => startJob('upgrade')}>程序升级</Button><Button disabled={!target} onClick={() => startJob('cleanup', { retentionDays: 30 }, true)}>清理旧版本</Button></Space></Col></Row>{target && <Descriptions bordered size="small" column={3} style={{ marginTop: 18 }}><Descriptions.Item label="地址">{target.username}@{target.host}:{target.port}</Descriptions.Item><Descriptions.Item label="远程目录">{target.remote_root}</Descriptions.Item><Descriptions.Item label="服务端口">{target.service_port}</Descriptions.Item><Descriptions.Item label="认证">{target.passwordConfigured ? '已配置' : '未配置'}</Descriptions.Item><Descriptions.Item label="代码版本">{deploy.status?.codeVersion || '—'}</Descriptions.Item><Descriptions.Item label="内容版本">{deploy.status?.contentVersion || '—'}</Descriptions.Item></Descriptions>}</Card><Row gutter={16}><Col span={12}><Card title="代码回滚"><Select placeholder="选择历史代码版本" style={{ width: '100%' }} onChange={value => rollback('code', value)} options={releases.filter(item => item.status !== 'current').map(item => ({ value: item.releaseId, label: item.releaseId }))} /></Card></Col><Col span={12}><Card title="内容回滚"><Select placeholder="选择历史内容版本" style={{ width: '100%' }} onChange={value => rollback('content', value)} options={contentReleases.filter(item => item.status !== 'current').map(item => ({ value: item.releaseId, label: item.releaseId }))} /></Card></Col></Row><Card title="部署任务"><Table rowKey="id" columns={jobColumns} dataSource={deploy.jobs || []} pagination={{ pageSize: 8 }} scroll={{ x: 900 }} /></Card></Space> },
    { key: 'config', label: '平台配置', children: <Row gutter={16}><Col span={12}><Card title="AI 服务" extra={platformConfig?.dioco?.configured ? <Tag color="success">已配置 {platformConfig.dioco.tokenMask}</Tag> : <Tag color="warning">未配置</Tag>}><Form form={aiForm} layout="vertical" onFinish={saveAiConfig}><Form.Item label="服务邮箱" name="email" rules={[{ required: true, type: 'email', message: '请输入有效服务邮箱' }]}><Input /></Form.Item><Form.Item label="Dioco Token" name="token" extra="留空保持现有 Token；浏览器不会读取已保存的完整值。"><Input.Password placeholder={platformConfig?.dioco?.configured ? '已保存，留空保持不变' : '输入平台 Token'} /></Form.Item><Form.Item label="API 地址" name="upstream" rules={[{ required: true, type: 'url', message: '请输入有效 API 地址' }]}><Input /></Form.Item><Space><Button type="primary" htmlType="submit">保存并启用</Button>{platformConfig?.dioco?.configured && <Button danger onClick={() => Modal.confirm({ title: '清除 AI Token？', content: '清除后词汇语境和 AI 句法服务将停止工作。', okButtonProps: { danger: true }, onOk: async () => saveAiConfig({ ...aiForm.getFieldsValue(), clearToken: true }) })}>清除 Token</Button>}</Space></Form><Alert style={{ marginTop: 18 }} type="info" showIcon message="超级管理员配置保存在 PostgreSQL platform_settings 中，AI 请求即时读取，无需重启或修改 environment。" /></Card></Col><Col span={12}><Card title="运维原则"><List dataSource={['所有高风险操作要求二次确认', '部署与内容回滚均产生任务记录', '媒体删除先标记，再执行可审计清理', '到期账户清理由管理员显式触发']} renderItem={item => <List.Item><SafetyCertificateOutlined style={{ color: '#2f6f50', marginRight: 8 }} />{item}</List.Item>} /></Card></Col></Row> },
  ]

  if (initialLoading) return <PageSkeleton />
  return <div className="page-stack"><div className="page-intro"><div><Text className="eyebrow">PLATFORM OPERATIONS</Text><Title level={1}>平台与部署</Title><Paragraph>内容审核、媒体生命周期、账户清理和远程部署全部在 React 管理台完成。</Paragraph></div><Button icon={<ReloadOutlined />} loading={busy} onClick={refresh}>刷新</Button></div><Tabs size="large" items={items} /><Modal title={nodeForm.getFieldValue('id') ? '编辑部署节点' : '新增部署节点'} open={nodeOpen} onCancel={() => setNodeOpen(false)} onOk={() => nodeForm.submit()} okText="保存节点"><Form form={nodeForm} layout="vertical" onFinish={saveNode}><Form.Item name="id" hidden><Input /></Form.Item><Row gutter={12}><Col span={12}><Form.Item label="节点名称" name="name" rules={[{ required: true }]}><Input /></Form.Item></Col><Col span={12}><Form.Item label="SSH 地址" name="host" rules={[{ required: true }]}><Input /></Form.Item></Col><Col span={8}><Form.Item label="SSH 端口" name="port"><InputNumber min={1} max={65535} style={{ width: '100%' }} /></Form.Item></Col><Col span={8}><Form.Item label="用户名" name="username"><Input /></Form.Item></Col><Col span={8}><Form.Item label="服务端口" name="servicePort"><InputNumber min={1} max={65535} style={{ width: '100%' }} /></Form.Item></Col></Row><Form.Item label="远程目录" name="remoteRoot" rules={[{ required: true }]}><Input /></Form.Item><Form.Item label="SSH 密码（留空保持原配置）" name="password"><Input.Password /></Form.Item><Space><Form.Item label="启用 HTTPS" name="useHttps" valuePropName="checked"><Switch /></Form.Item><Form.Item label="安装录音能力" name="installRecording" valuePropName="checked"><Switch /></Form.Item></Space></Form></Modal></div>
}
