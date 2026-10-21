import React, { useEffect, useState } from 'react'
import { Alert, Button, Card, Col, Empty, Row, Segmented, Skeleton, Space, Table, Typography } from 'antd'
import { getJson } from '../api/client'

const { Paragraph, Text } = Typography
const percent = (value, total) => total ? `${(value / total * 100).toFixed(1)}%` : '—'

export default function JourneyReport() {
  const [days, setDays] = useState(30)
  const [revision, setRevision] = useState(0)
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    setLoading(true); setError(''); setReport(null)
    getJson(`/api/admin/journey-report?days=${days}`).then(value => { if (active) setReport(value) })
      .catch(failure => { if (active) setError(failure.message || '请稍后重试') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [days, revision])
  const l = report?.learning, p = report?.purchase
  const columns = [{ title: '阶段', dataIndex: 'label' }, { title: '人数', dataIndex: 'count', width: 90 }, { title: '占起始人数', dataIndex: 'rate', width: 120 }]
  const learningRows = l ? [
    ['registered', '创建账号', l.registered], ['verified', '完成邮箱验证', l.verified],
    ['reading', '保存首次听读记录', l.reading], ['saved_word', '听读并保存生词', l.saved_word],
  ].map(([key, label, count]) => ({ key, label, count, rate: percent(count, l.registered) })) : []
  const purchaseRows = p ? [
    ['selected', '选择付费方案', p.selected], ['departed', '点击前往云猫', p.departed], ['redeemed', '之后成功兑换', p.redeemed],
  ].map(([key, label, count]) => ({ key, label, count, rate: percent(count, p.selected) })) : []
  return <Space direction="vertical" size={20} style={{ width: '100%' }}>
    <div className="journey-report-toolbar"><Text strong>查看真实学习与购买转化</Text><Space><Segmented value={days} onChange={setDays} options={[7, 30, 90].map(value => ({ label: `${value} 天`, value }))} /><Button onClick={() => setRevision(value => value + 1)} loading={loading}>刷新</Button></Space></div>
    {loading ? <Skeleton active paragraph={{ rows: 6 }} /> : error ? <Alert type="error" showIcon message="转化数据暂时无法加载" description={error} action={<Button onClick={() => setRevision(value => value + 1)}>重试</Button>} /> : report && <>
      <Row gutter={[20, 20]}><Col span={12}><Card title="首次学习">{l.registered ? <Table columns={columns} dataSource={learningRows} pagination={false} size="small" /> : <Empty description="观察期内暂无新注册账号" />}
        <div className="journey-retention"><Text strong>完成首次学习次日留存</Text><Paragraph>{l.returned} / {l.return_eligible} 人 · {percent(l.returned, l.return_eligible)}</Paragraph><Text type="secondary">以听读记录和首个生词都保存完成的日期为起点。分母为次日已完整结束的账号，分子为次日再次保存听读记录的账号。观察时间不足时不计为流失。</Text></div>
      </Card></Col><Col span={12}><Card title="购买到兑换">{p.selected ? <Table columns={columns} dataSource={purchaseRows} pagination={false} size="small" /> : <Empty description="观察期内暂无付费方案选择记录" />}<Paragraph type="secondary" className="journey-report-note">兑换以拾页服务端开通记录为准，包含该账号前往云猫后完成的兑换。外部支付成功、失败及云猫订单金额未接入，无法据此计算支付成功率。</Paragraph></Card></Col></Row>
    </>}
  </Space>
}
