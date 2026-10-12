import React, { useState } from 'react'
import { Button, Card, Col, Empty, List, Pagination, Row, Space, Tag, Typography } from 'antd'

const { Paragraph, Text, Title } = Typography

export default function RewardsPage({ rewardStatus, rewardsCatalog, rewardsLedger, onCheckIn, onRedeemReward }) {
  const [page, setPage] = useState(1)
  const pageSize = 8
  const ledger = rewardsLedger || []
  const visible = ledger.slice((page - 1) * pageSize, page * pageSize)
  return <div className="page-stack">
    <div className="page-intro"><div><Text className="eyebrow">GROWTH REWARDS</Text><Title level={1}>成长奖励</Title><Paragraph>签到、阅读和复习产生真实成长值，可兑换账号权益。</Paragraph></div><Button type="primary" onClick={onCheckIn} disabled={rewardStatus?.checkedIn}>{rewardStatus?.checkedIn ? '今日已签到' : '今日签到'}</Button></div>
    <Row gutter={[16, 16]}>
      <Col span={8}><Card><Text type="secondary">成长值</Text><Title level={2}>{rewardStatus?.balance ?? '—'} 点</Title><Text>本月获得 {rewardStatus?.monthEarned ?? '—'} 点</Text></Card></Col>
      <Col span={8}><Card><Text type="secondary">连续学习</Text><Title level={2}>{rewardStatus?.streak ?? 0} 天</Title><Text>{rewardStatus?.checkedIn ? '今日已完成签到' : '今日尚未签到'}</Text></Card></Col>
      <Col span={8}><Card><Text type="secondary">邀请额度</Text><Title level={2}>{rewardStatus?.inviteAllowance ?? 0} 个</Title><Text>可用邀请名额</Text></Card></Col>
    </Row>
    <Row gutter={[20, 20]}>
      <Col span={12}><Card title="可兑换奖励"><List dataSource={rewardsCatalog} locale={{ emptyText: '暂无可兑换奖励' }} renderItem={item => <List.Item actions={[<Button key="redeem" size="small" onClick={() => onRedeemReward?.(item.code)} disabled={(rewardStatus?.balance || 0) < item.costPoints}>兑换</Button>]}><List.Item.Meta title={item.title} description={`${item.description || '暂无说明'} · ${item.costPoints} 点`} /></List.Item>} /></Card></Col>
      <Col span={12}><Card title="成长记录" extra={<Text type="secondary">共 {ledger.length} 条</Text>}><List dataSource={visible} locale={{ emptyText: <Empty description="暂无成长记录" /> }} renderItem={item => <List.Item><List.Item.Meta title={<Space>{item.eventType}<Tag>{item.day || '活动'}</Tag></Space>} description={item.createdAt ? new Date(item.createdAt).toLocaleString('zh-CN') : item.day} /><Text type={item.points > 0 ? 'success' : 'secondary'}>{item.points > 0 ? `+${item.points}` : item.points} 点</Text></List.Item>} />{ledger.length > pageSize && <Pagination current={page} pageSize={pageSize} total={ledger.length} showSizeChanger={false} onChange={setPage} />}</Card></Col>
    </Row>
  </div>
}
