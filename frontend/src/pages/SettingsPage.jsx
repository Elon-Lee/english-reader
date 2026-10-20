import React, { useEffect } from 'react'
import {
  Button,
  Card,
  Col,
  Descriptions,
  Divider,
  Form,
  InputNumber,
  List,
  Row,
  Segmented,
  Select,
  Space,
  Switch,
  Tag,
  Typography,
} from 'antd'

import { DEFAULT_PREFERENCES, KEY_OPTIONS } from '../config/preferences'

const { Paragraph, Text, Title } = Typography

function PageIntro() {
  return <div className="page-intro"><div><Text className="eyebrow">WORKSPACE SETTINGS</Text><Title level={1}>系统设置</Title><Paragraph>账号安全、阅读器行为、复习节奏和设备均保存在当前账号。</Paragraph></div></div>
}

export default function SettingsPage({ currentUser, devices, preferences, deletionStatus, onRevokeOwnDevice, onSavePreferences, onLogout, onRequestDeletion, onCancelDeletion, messageApi }) {
  const [form] = Form.useForm()
  useEffect(() => { form.setFieldsValue({ ...DEFAULT_PREFERENCES, ...(preferences || {}) }) }, [form, preferences])

  const submit = values => {
    const shortcuts = [values.shortcutPrevious, values.shortcutRepeat, values.shortcutNext, values.shortcutPlay]
    if (new Set(shortcuts).size !== shortcuts.length) {
      messageApi.error('四个阅读快捷键不能重复')
      return
    }
    onSavePreferences(values)
  }

  return <div className="page-stack settings-page">
    <PageIntro />
    <Row gutter={[20, 20]}>
      <Col xs={24} xl={16}>
        <Card title="阅读器偏好">
          <Form form={form} layout="vertical" onFinish={submit} initialValues={DEFAULT_PREFERENCES}>
            <Row gutter={16}>
              <Col span={12}><Form.Item label="默认学习空间" name="focusMode" getValueProps={value => ({ value: value ? 'focus' : 'normal' })} normalize={value => value === 'focus'}><Segmented block options={[{ label: '普通模式', value: 'normal' }, { label: '专注模式', value: 'focus' }]} /></Form.Item></Col>
              <Col span={12}><Form.Item label="正文布局" name="readerLayout"><Segmented block options={[{ label: '左右布局', value: 'side' }, { label: '上下布局', value: 'stack' }]} /></Form.Item></Col>
              <Col span={12}><Form.Item label="界面密度" name="density"><Segmented block options={[{ label: '舒适', value: 'comfortable' }, { label: '紧凑', value: 'compact' }]} /></Form.Item></Col>
              <Col span={12}><Form.Item label="默认播放速度" name="playbackRate"><Select options={[.5, .75, 1, 1.25, 1.5, 2].map(value => ({ value, label: `${value}×` }))} /></Form.Item></Col>
              <Col span={8}><Form.Item label="护眼模式" name="eyeComfort" valuePropName="checked"><Switch /></Form.Item></Col>
              <Col span={8}><Text type="secondary">两种模式均可查词、分析句法与跟读。</Text></Col>
              <Col span={8}><Form.Item label="句末自动暂停" name="sentenceAutoPause" valuePropName="checked"><Switch /></Form.Item></Col>
            </Row>

            <Divider orientation="left">阅读快捷键</Divider>
            <Row gutter={16}>
              <Col span={6}><Form.Item label="上一句" name="shortcutPrevious"><Select options={KEY_OPTIONS} /></Form.Item></Col>
              <Col span={6}><Form.Item label="复读当前句" name="shortcutRepeat"><Select options={KEY_OPTIONS} /></Form.Item></Col>
              <Col span={6}><Form.Item label="下一句" name="shortcutNext"><Select options={KEY_OPTIONS} /></Form.Item></Col>
              <Col span={6}><Form.Item label="播放 / 暂停" name="shortcutPlay"><Select options={KEY_OPTIONS} /></Form.Item></Col>
            </Row>

            <Divider orientation="left">复习与同步</Divider>
            <Row gutter={16}>
              <Col span={8}><Form.Item label="单词工具栏停留（秒）" name="wordTipSeconds"><InputNumber min={.5} max={10} step={.5} style={{ width: '100%' }} /></Form.Item></Col>
              <Col span={8}><Form.Item label="生词每页数量" name="reviewPageSize"><InputNumber min={5} max={50} step={5} style={{ width: '100%' }} /></Form.Item></Col>
              <Col span={8}><Form.Item label="热力图范围" name="heatmapRange"><Select options={[{ value: 'month', label: '最近一个月' }, { value: 'quarter', label: '最近三个月' }, { value: 'year', label: '最近一年' }]} /></Form.Item></Col>
              <Col span={8}><Form.Item label="听写朗读次数" name="manualRepeatCount"><InputNumber min={1} max={10} style={{ width: '100%' }} /></Form.Item></Col>
              <Col span={8}><Form.Item label="听写词间停顿（秒）" name="manualPauseSeconds"><InputNumber min={.5} max={10} step={.5} style={{ width: '100%' }} /></Form.Item></Col>
              <Col span={8}><Form.Item label="单词高亮提前量（毫秒）" name="highlightLeadMs"><InputNumber min={-300} max={600} step={20} style={{ width: '100%' }} /></Form.Item></Col>
              <Col span={12}><Form.Item label="学习提醒" name="reminder"><Select options={[{ value: 'off', label: '关闭' }, { value: 'daily', label: '每天 20:00' }, { value: 'weekdays', label: '工作日 20:00' }]} /></Form.Item></Col>
            </Row>
            <Button type="primary" size="large" htmlType="submit">保存全部阅读设置</Button>
          </Form>
        </Card>
      </Col>
      <Col xs={24} xl={8}>
        <Card title="账户与安全">
          <Descriptions column={1} size="small">
            <Descriptions.Item label="登录邮箱">{currentUser?.email || '当前会话未读取'}</Descriptions.Item>
            <Descriptions.Item label="账号角色">{currentUser?.isAdmin ? '平台管理员' : '普通会员'}</Descriptions.Item>
            <Descriptions.Item label="登录保护"><Tag color="success">已开启</Tag></Descriptions.Item>
            <Descriptions.Item label="已连接设备">{devices?.length || 0} 台</Descriptions.Item>
          </Descriptions>
          <List size="small" dataSource={devices || []} locale={{ emptyText: '暂无设备信息' }} renderItem={device => <List.Item actions={!device.revoked ? [<Button key="revoke" size="small" danger onClick={() => onRevokeOwnDevice?.(device.id)}>撤销</Button>] : []}><List.Item.Meta title={device.label || '未命名设备'} description={device.userAgent || '未知客户端'} /><Tag color={device.revoked ? 'default' : 'success'}>{device.revoked ? '已撤销' : '活跃'}</Tag></List.Item>} />
        </Card>
        <Card title="危险区域" className="danger-card">
          <Text type="secondary">导出数据或申请删除账户。操作前会要求二次确认。</Text>
          <Space direction="vertical" style={{ width: '100%', marginTop: 16 }}>
            <Button block onClick={() => { location.href = '/api/account/export' }}>导出账户数据</Button>
            <Button block danger onClick={onLogout}>退出登录</Button>
            {deletionStatus?.status === 'requested' ? <><Text type="warning">计划删除时间：{new Date(deletionStatus.scheduledFor).toLocaleString('zh-CN')}</Text><Button block onClick={onCancelDeletion}>取消注销申请</Button></> : <Button block danger onClick={onRequestDeletion}>申请注销账户</Button>}
          </Space>
        </Card>
      </Col>
    </Row>
  </div>
}
