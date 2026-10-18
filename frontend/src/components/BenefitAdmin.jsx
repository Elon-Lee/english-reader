import React, { useState } from 'react'
import { Button, Card, Col, Drawer, Empty, Form, Input, List, Row, Space, Switch, Tag, Typography } from 'antd'
import { PlusOutlined } from '@ant-design/icons'

const { Paragraph, Text, Title } = Typography

export default function BenefitAdmin({ entitlements = { builtIn: [], configured: [] }, onCreate, onUpdate }) {
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form] = Form.useForm()
  const create = () => { setEditing(null); form.resetFields(); form.setFieldsValue({ active: true }); setOpen(true) }
  const edit = item => { setEditing(item); form.setFieldsValue({ name: item.name, description: item.description, defaultText: item.defaultText, active: item.active }); setOpen(true) }
  const submit = async values => {
    if (editing) await onUpdate?.(editing.id, values)
    else await onCreate?.(values)
    form.resetFields(); setOpen(false); setEditing(null)
  }
  return <div className="benefit-admin-stack">
    <Card title={<div><Title level={3}>内置项</Title><Paragraph>由系统代码实际校验和扣减，套餐只能勾选这些真实产品功能，并配置每个周期的使用限制。视频画质由当前会员等级自动控制：免费版仅流畅，付费版可切换高清。</Paragraph></div>}>
      <Row gutter={[16, 16]}>{(entitlements.builtIn || []).map(item => <Col xs={24} lg={12} key={item.key}><Card size="small" className="benefit-definition-card"><Space direction="vertical" size={8}><Space><Text strong>{item.name}</Text><Tag color="success">系统受控</Tag>{item.required && <Tag color="blue">必选</Tag>}</Space><Text type="secondary">{item.control}</Text><Text>默认限制：<b>{item.defaultLimit} {item.unit}</b></Text><Text code>{item.key}</Text></Space></Card></Col>)}</Row>
    </Card>
    <Card title={<div><Title level={3}>配置项</Title><Paragraph>运营手工维护的附加权益，只用于套餐展示，不参与系统次数或容量控制。</Paragraph></div>} extra={<Button type="primary" icon={<PlusOutlined />} onClick={create}>新增配置项</Button>}>
      <List dataSource={entitlements.configured || []} locale={{ emptyText: <Empty description="暂无配置权益" /> }} renderItem={item => <List.Item actions={[<Button key="edit" onClick={() => edit(item)}>编辑</Button>]}><List.Item.Meta title={<Space><Text strong>{item.name}</Text><Tag color={item.active ? 'success' : 'default'}>{item.active ? '启用' : '停用'}</Tag></Space>} description={<Space direction="vertical" size={2}><Text>{item.defaultText}</Text><Text type="secondary">{item.description || '无补充说明'}</Text><Text code>{item.code}</Text></Space>} /></List.Item>} />
    </Card>
    <Drawer width={560} title={editing ? '编辑配置权益' : '新增配置权益'} open={open} onClose={() => setOpen(false)} extra={<Space><Button onClick={() => setOpen(false)}>取消</Button><Button type="primary" onClick={() => form.submit()}>保存</Button></Space>}><Form form={form} layout="vertical" onFinish={submit}>{!editing && <Form.Item label="唯一标识" name="code" rules={[{ required: true }]} extra="仅小写字母、数字和连字符，创建后不可修改。"><Input placeholder="support-7x8" /></Form.Item>}<Form.Item label="权益名称" name="name" rules={[{ required: true }]}><Input placeholder="7×8 小时客服支持" /></Form.Item><Form.Item label="套餐展示文案" name="defaultText" rules={[{ required: true }]}><Input placeholder="7×8 小时客服支持" /></Form.Item><Form.Item label="内部说明" name="description"><Input.TextArea rows={4} /></Form.Item><Form.Item label="启用" name="active" valuePropName="checked"><Switch /></Form.Item></Form></Drawer>
  </div>
}
