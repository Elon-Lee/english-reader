import React, { useEffect } from 'react'
import {
  Button,
  Card,
  Col,
  Descriptions,
  Divider,
  Form,
  List,
  Row,
  Select,
  Space,
  Switch,
  Tag,
  Typography,
} from 'antd'

import { DEFAULT_PREFERENCES, KEY_OPTIONS } from '../config/preferences'
import ReaderFlowControl from '../components/ReaderFlowControl'
import SettingsRadioGroup from '../components/SettingsRadioGroup'

const { Paragraph, Text, Title } = Typography

function PageIntro() {
  return <div className="page-intro"><div><Text className="eyebrow">WORKSPACE SETTINGS</Text><Title level={1}>系统设置</Title><Paragraph>阅读偏好、登录设备和账户数据由当前账号管理。</Paragraph></div></div>
}

export default function SettingsPage({ currentUser, devices, preferences, deletionStatus, onRevokeOwnDevice, onSavePreferences, onPreferencesChange, onLogout, onRequestDeletion, onCancelDeletion, messageApi }) {
  const [form] = Form.useForm()
  const currentDeviceKnown = (devices || []).some(device => device.current)
  useEffect(() => { form.setFieldsValue({ ...DEFAULT_PREFERENCES, ...(preferences || {}) }) }, [form, preferences])

  const submit = values => {
    const shortcuts = [values.shortcutPrevious, values.shortcutRepeat, values.shortcutNext, values.shortcutPlay]
    if (new Set(shortcuts).size !== shortcuts.length) {
      messageApi.error('四个阅读快捷键不能重复')
      return
    }
    onSavePreferences(values)
  }

  const chooseTheme = async theme => {
    const previousTheme = preferences?.theme || DEFAULT_PREFERENCES.theme
    if (previousTheme === theme) return
    onPreferencesChange?.({ theme })
    try { await onSavePreferences({ theme }) }
    catch { onPreferencesChange?.({ theme: previousTheme }) }
  }

  return <div className="page-stack settings-page">
    <PageIntro />
    <Card className="theme-picker-card" title="界面主题" extra={<Text type="secondary">仅调整学习中心外观</Text>}>
      <div className="theme-picker-options" role="group" aria-label="选择界面主题">
        {[
          { id: 'pine', name: '松林绿', note: '自然沉静', colors: ['#f6f5f1', '#285c45', '#e7efe8'] },
          { id: 'mist', name: '雾蓝', note: '清晰理性', colors: ['#f2f5f7', '#426b84', '#e1ebf1'] },
          { id: 'iris', name: '鸢尾紫', note: '柔和知性', colors: ['#f5f3f8', '#71638d', '#ebe6f2'] },
        ].map(option => <button key={option.id} type="button" className={`theme-choice ${preferences?.theme === option.id ? 'selected' : ''}`} style={{ '--choice-accent': option.colors[1] }} aria-pressed={preferences?.theme === option.id} onClick={() => chooseTheme(option.id)}>
          <span className="theme-choice-preview" style={{ '--preview-bg': option.colors[0], '--preview-accent': option.colors[1], '--preview-selected': option.colors[2] }}><i /><i /><i /></span>
          <span className="theme-choice-copy"><strong>{option.name}</strong><small>{option.note}</small></span>
          {preferences?.theme === option.id && <Tag color="success">当前</Tag>}
        </button>)}
      </div>
      <Text className="theme-picker-note" type="secondary">阅读器的护眼模式仍单独控制正文底色，不受界面主题影响。</Text>
    </Card>
    <Row gutter={[20, 20]}>
      <Col xs={24} xl={16}>
        <Card className="reader-preferences-card" title="阅读器偏好">
          <Form form={form} layout="vertical" onFinish={submit} initialValues={DEFAULT_PREFERENCES}>
            <Row gutter={[12, 0]} className="settings-option-grid">
              <Col span={12}><Form.Item label="默认学习空间" name="focusMode" getValueProps={value => ({ value: value ? 'focus' : 'normal' })} normalize={value => value === 'focus'}><SettingsRadioGroup label="默认学习空间" options={[{ label: '普通模式', value: 'normal' }, { label: '专注模式', value: 'focus' }]} /></Form.Item></Col>
              <Col span={12}><Form.Item label="正文布局" name="readerLayout"><SettingsRadioGroup label="正文布局" options={[{ label: '左右布局', value: 'side' }, { label: '上下布局', value: 'stack' }]} /></Form.Item></Col>
              <Col span={12}><Form.Item label="阅读推进方式" name="readerFlowMode"><ReaderFlowControl /></Form.Item></Col>
              <Col span={12}><Form.Item label="界面密度" name="density"><SettingsRadioGroup label="界面密度" options={[{ label: '舒适', value: 'comfortable' }, { label: '紧凑', value: 'compact' }]} /></Form.Item></Col>
              <Col span={12}><Form.Item label="默认播放速度" name="playbackRate"><Select options={[.5, .75, 1, 1.25, 1.5, 2].map(value => ({ value, label: `${value}×` }))} /></Form.Item></Col>
            </Row>

            <Divider orientation="left">阅读行为</Divider>
            <div className="settings-behavior-grid">
              <div className="settings-switch-row"><label htmlFor="eyeComfort">护眼模式</label><Form.Item noStyle name="eyeComfort" valuePropName="checked"><Switch /></Form.Item></div>
              <div className="settings-switch-row"><label htmlFor="sentenceAutoPause">句末自动暂停</label><Form.Item noStyle name="sentenceAutoPause" valuePropName="checked"><Switch /></Form.Item></div>
            </div>

            <Divider orientation="left">阅读快捷键</Divider>
            <Row gutter={12} className="settings-shortcut-grid">
              <Col span={6}><Form.Item label="上一句" name="shortcutPrevious"><Select options={KEY_OPTIONS} /></Form.Item></Col>
              <Col span={6}><Form.Item label="复读当前句" name="shortcutRepeat"><Select options={KEY_OPTIONS} /></Form.Item></Col>
              <Col span={6}><Form.Item label="下一句" name="shortcutNext"><Select options={KEY_OPTIONS} /></Form.Item></Col>
              <Col span={6}><Form.Item label="播放 / 暂停" name="shortcutPlay"><Select options={KEY_OPTIONS} /></Form.Item></Col>
            </Row>

            <Button type="primary" htmlType="submit">保存阅读设置</Button>
          </Form>
        </Card>
      </Col>
      <Col xs={24} xl={8}>
        <Card title="账户与安全">
          <Descriptions column={1} size="small">
            <Descriptions.Item label="登录邮箱">{currentUser?.email || '当前会话未读取'}</Descriptions.Item>
            <Descriptions.Item label="账号角色">{currentUser?.isAdmin ? '平台管理员' : '普通会员'}</Descriptions.Item>
            <Descriptions.Item label="已连接设备">{devices?.length || 0} 台</Descriptions.Item>
          </Descriptions>
          {!currentDeviceKnown && devices?.length > 0 && <Text type="warning" style={{ display: 'block', marginBottom: 8 }}>当前设备状态待确认，暂不可撤销设备。</Text>}
          <List size="small" dataSource={devices || []} locale={{ emptyText: '暂无设备信息' }} renderItem={device => <List.Item actions={currentDeviceKnown && !device.current ? [<Button key="revoke" size="small" danger onClick={() => onRevokeOwnDevice?.(device.id)}>撤销</Button>] : []}><List.Item.Meta title={<Space>{device.label || '未命名设备'}{device.current ? <Tag color="success">当前设备</Tag> : currentDeviceKnown ? <Tag>已连接</Tag> : <Tag color="warning">状态待确认</Tag>}</Space>} description={device.userAgent || '未知客户端'} /></List.Item>} />
        </Card>
        <Card title="危险区域" className="danger-card">
          <Text type="secondary">导出会下载当前账号数据。注销申请会退出登录，并在 30 天宽限期后清理账户；期间重新登录可取消。</Text>
          <div className="settings-account-actions">
            <Button block onClick={() => { location.href = '/api/account/export' }}>导出账户数据</Button>
            <Button block danger onClick={onLogout}>退出登录</Button>
            {deletionStatus?.status === 'requested' ? <><Text type="warning">计划删除时间：{new Date(deletionStatus.scheduledFor).toLocaleString('zh-CN')}</Text><Button block onClick={onCancelDeletion}>取消注销申请</Button></> : <Button block danger onClick={onRequestDeletion}>申请注销账户</Button>}
          </div>
        </Card>
      </Col>
    </Row>
  </div>
}
