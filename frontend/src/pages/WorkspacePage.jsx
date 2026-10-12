import React, { useMemo } from 'react'
import { Button, Card, Col, Progress, Row, Space, Statistic, Typography } from 'antd'
import { CloudUploadOutlined, CustomerServiceOutlined, PlusOutlined, ReadOutlined } from '@ant-design/icons'

const { Paragraph, Text, Title } = Typography

function dateKey(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function weekState(learningDays) {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const monday = new Date(today)
  monday.setDate(today.getDate() - ((today.getDay() + 6) % 7))
  const activity = new Map(learningDays.map(item => [item.day, item.payload || {}]))
  return Array.from({ length: 7 }, (_, index) => {
    const date = new Date(monday)
    date.setDate(monday.getDate() + index)
    const payload = activity.get(dateKey(date)) || {}
    return { date, completed: Number(payload.reading_seconds || 0) > 0 || Number(payload.sentences || 0) > 0 || Number(payload.reviews || 0) > 0, future: date > today }
  })
}

function Cover({ book, large = false }) {
  return <div className={`book-cover ${large ? 'book-cover-large' : ''}`} style={{ '--cover': book.accent || '#dce9d8' }}><span>{book.cover || String(book.title || '书').slice(0, 2).toUpperCase()}</span><small>{book.title}</small></div>
}

function Action({ icon, title, copy, action, onClick }) {
  return <Col span={8}><Card className="action-card"><div className="action-icon">{icon}</div><Title level={4}>{title}</Title><Paragraph>{copy}</Paragraph><Button type="link" onClick={onClick}>{action} →</Button></Card></Col>
}

export default function WorkspacePage({ allBooks, selectScreen, openReader, openImport, learningDays, rewardStatus }) {
  const week = useMemo(() => weekState(learningDays), [learningDays])
  const weekKeys = new Set(week.map(item => dateKey(item.date)))
  const minutes = learningDays.filter(item => weekKeys.has(item.day)).reduce((sum, day) => sum + Number(day.payload?.reading_seconds || 0) / 60, 0)
  const streak = Number(rewardStatus?.streak || 0)
  const goalPercent = Math.min(100, Math.round(minutes / 120 * 100))
  const continueBook = allBooks.find(book => book.progress > 0 && book.progress < 100) || allBooks[0]
  return <div className="page-stack">
    <div className="page-intro"><div><Text className="eyebrow">GOOD MORNING · {new Date().toLocaleDateString('zh-CN')}</Text><Title level={1}>继续你的英语阅读</Title><Paragraph>把碎片时间变成可积累的理解力。今天完成 12 分钟学习，就能保持连续记录。</Paragraph></div><Button type="primary" size="large" icon={<PlusOutlined />} onClick={openImport}>导入新读物</Button></div>
    <Row gutter={[20, 20]}>
      <Col span={16}><Card className="hero-card"><div className="hero-card-content"><div className="hero-card-copy"><Text className="card-kicker">继续学习</Text><Title level={2}>{continueBook?.title || '还没有读物'}</Title><Paragraph>{continueBook?.subtitle || '导入第一本读物，开始你的学习记录。'}</Paragraph><Space><Button type="primary" onClick={() => continueBook ? openReader(continueBook) : openImport()}>{continueBook ? '继续阅读' : '导入读物'} →</Button><Button onClick={() => selectScreen('library')}>查看书架</Button></Space></div>{continueBook && <Cover book={continueBook} large />}</div></Card></Col>
      <Col span={8}><Card className="streak-card"><Text className="card-kicker">本周学习目标</Text><Statistic value={goalPercent} suffix="%" valueStyle={{ color: '#17392b', fontSize: 42, fontWeight: 700 }} /><Progress percent={goalPercent} showInfo={false} strokeColor="#f08b67" trailColor="#f7e3da" /><Text type="secondary">{Math.max(0, 120 - Math.round(minutes))} 分钟达到本周目标 · 当前连续 {streak} 天</Text><div className="streak-days">{week.map((item, index) => <span className={item.completed ? 'done' : item.future ? 'future' : ''} key={dateKey(item.date)} title={`${dateKey(item.date)}${item.completed ? ' 已完成学习' : ' 未完成学习'}`}>{item.completed ? '✓' : ['一', '二', '三', '四', '五', '六', '日'][index]}</span>)}</div></Card></Col>
    </Row>
    <div className="section-header"><Title level={3}>你的阅读进度</Title><Button type="link" onClick={() => selectScreen('library')}>查看全部</Button></div>
    <Row gutter={[16, 16]}>{allBooks.slice(0, 3).map(book => <Col span={8} key={book.id}><Card hoverable className="book-card" onClick={() => openReader(book)}><Title level={4}>{book.title}</Title><Text type="secondary">{book.subtitle}</Text><Progress percent={book.progress || 0} strokeColor="#2f6f50" /></Card></Col>)}</Row>
    <div className="section-header"><Title level={3}>今天可以做什么</Title></div>
    <Row gutter={[16, 16]}><Action icon={<ReadOutlined />} title="完成一次精读" copy="选一段未读内容，跟读并标记 3 个新词。" action="开始阅读" onClick={() => selectScreen('library')} /><Action icon={<CustomerServiceOutlined />} title="复习生词" copy="查看真实复习队列和学习活动。" action="去复习" onClick={() => selectScreen('vocab')} /><Action icon={<CloudUploadOutlined />} title="导入个人内容" copy="支持 TXT、Markdown、PDF、MP3 与视频。" action="开始导入" onClick={openImport} /></Row>
  </div>
}
