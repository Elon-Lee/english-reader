import React, { useMemo, useState } from 'react'
import { Button, Card, Col, Row, Segmented, Space, Statistic, Tooltip, Typography } from 'antd'
import { continueReadingBook } from '../utils/presentation.mjs'

const { Paragraph, Text, Title } = Typography

function dateKey(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function bounds(range) {
  const end = new Date()
  end.setHours(0, 0, 0, 0)
  const start = new Date(end)
  if (range === 'week') start.setDate(end.getDate() - ((end.getDay() + 6) % 7))
  else if (range === 'month') start.setDate(1)
  else start.setDate(end.getDate() - 364 - ((end.getDay() + 6) % 7))
  return { start, end }
}

function heatLevel(payload = {}) {
  const score = Number(payload.reading_seconds || 0) / 300 + Number(payload.lookups || 0) / 5 + Number(payload.reviews || 0) / 3 + Number(payload.sentences || 0) / 10
  if (score <= 0) return 0
  if (score < 1) return 1
  if (score < 3) return 2
  if (score < 6) return 3
  return 4
}

function Heatmap({ learningDays, range }) {
  const map = useMemo(() => new Map(learningDays.map(item => [item.day, item.payload || item])), [learningDays])
  const { start, end } = bounds(range)
  const leading = (start.getDay() + 6) % 7
  const cells = Array.from({ length: leading }, (_, index) => ({ empty: true, key: `empty-${index}` }))
  for (let day = new Date(start); day <= end; day.setDate(day.getDate() + 1)) {
    const key = dateKey(day)
    const payload = map.get(key) || {}
    cells.push({ key, payload, level: heatLevel(payload) })
  }
  return <>
    <div className={`study-heatmap-modern range-${range}`}>
      {cells.map(cell => cell.empty ? <i key={cell.key} className="heatmap-empty" /> : <Tooltip key={cell.key} title={`${cell.key} · ${Math.round(Number(cell.payload.reading_seconds || 0) / 60)} 分钟 · ${Number(cell.payload.sentences || 0)} 句 · ${Number(cell.payload.reviews || 0)} 次复习`}><i tabIndex={0} role="img" aria-label={`${cell.key} · 听读 ${Math.round(Number(cell.payload.reading_seconds || 0) / 60)} 分钟 · ${Number(cell.payload.sentences || 0)} 句次 · ${Number(cell.payload.reviews || 0)} 次复习`} className={`heat-level-${cell.level}`} /></Tooltip>)}
    </div>
    <div className="heatmap-footer"><Text type="secondary">{dateKey(start)} 至 {dateKey(end)} · {cells.filter(item => !item.empty).length} 天</Text><div className="heatmap-legend"><span>少</span>{[0, 1, 2, 3, 4].map(level => <i key={level} className={`heat-level-${level}`} />)}<span>多</span></div></div>
  </>
}

export default function StatsPage({ allBooks, learningDays, learning, openReader }) {
  const [range, setRange] = useState('year')
  const readingSeconds = learningDays.reduce((sum, item) => sum + Number(item.payload?.reading_seconds || 0), 0)
  const dayCount = learningDays.filter(day => ['reading_seconds', 'sentences', 'reviews', 'shadow_attempts'].some(key => Number(day.payload?.[key]) > 0)).length
  const totalSentences = learningDays.reduce((sum, day) => sum + Number(day.payload?.sentences || 0), 0)
  const due = learning.review.stats.due
  const continueBook = continueReadingBook(allBooks)

  return <div className="page-stack">
    <div className="page-intro"><div><Text className="eyebrow">LEARNING INSIGHTS</Text><Title level={1}>学习记录</Title><Paragraph>按周、月、年查看真实学习密度和累计成果。</Paragraph></div><Button onClick={() => { location.href = '/api/account/export' }}>导出个人数据</Button></div>
    <Row gutter={[16, 16]}>
      <Col span={6}><Card><Statistic title="学习天数" value={dayCount} suffix="天" /></Card></Col>
      <Col span={6}><Card><Statistic title="累计听读" value={Math.round(readingSeconds / 60)} suffix="分钟" /></Card></Col>
      <Col span={6}><Card><Statistic title="累计记录句次" value={totalSentences} suffix="句次" /></Card></Col>
      <Col span={6}><Card><Statistic title="待复习生词" value={due} suffix="个" /></Card></Col>
    </Row>
    {continueBook && <Card className="stats-next-step"><div><Text className="eyebrow">NEXT STEP</Text><Title level={3}>继续：{continueBook.title}</Title><Paragraph>保持今天的学习节奏，回到上次阅读位置。</Paragraph></div><Button type="primary" onClick={() => openReader(continueBook)}>继续阅读 →</Button></Card>}
    <Card title="学习热力图" extra={<Segmented value={range} onChange={setRange} options={[{ label: '周', value: 'week' }, { label: '月', value: 'month' }, { label: '年', value: 'year' }]} />}>
      <Heatmap learningDays={learningDays} range={range} />
    </Card>
  </div>
}
