import React, { useEffect, useState } from 'react'
import { Alert, Button, Card, Modal, Space, Spin, Switch, Typography } from 'antd'
import { getJson, postJson } from '../api/client'

export default function AuthSecuritySettings({ messageApi }) {
  const [config, setConfig] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const load = async () => {
    setLoading(true)
    try { setConfig(await getJson('/api/admin/auth-config')); setError('') }
    catch (failure) { setError(failure.message || '配置加载失败') }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])
  const update = async enabled => {
    setLoading(true)
    try {
      setConfig(await postJson('/api/admin/auth-config', { captchaEnabled: enabled }))
      setError('')
      messageApi.success(enabled ? '验证码已开启' : '验证码已关闭')
    } catch (failure) { setError(failure.message || '保存失败') }
    finally { setLoading(false) }
  }
  const change = enabled => {
    if (enabled) { update(true); return }
    Modal.confirm({ title: '确认关闭验证码？', content: '关闭后，登录、注册和找回密码将直接进行。', okText: '关闭验证码', onOk: () => update(false) })
  }
  return <Card title="认证安全"><Space direction="vertical" size={16} style={{ width: '100%' }}>
    {error && <Alert type="error" showIcon message={error} action={<Button onClick={load}>重新加载</Button>} />}
    <Spin spinning={loading}><Space><Typography.Text>启用旋转验证码</Typography.Text><Switch checked={config?.captchaEnabled === true} disabled={!config || loading} onChange={change} /></Space></Spin>
    <Typography.Paragraph type="secondary">开启后，登录、注册、换设备登录和找回密码都需要先完成旋转验证。开关保存后即时生效，账号和邮箱验证方式保持不变。</Typography.Paragraph>
  </Space></Card>
}
