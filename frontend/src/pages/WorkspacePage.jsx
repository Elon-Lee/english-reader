import Cover from '../components/BookCover'
import React, { useMemo } from 'react'
import { Button, Card, Col, Progress, Row, Space, Statistic, Typography } from 'antd'
import { BookOutlined, PlusOutlined, ReadOutlined } from '@ant-design/icons'
import { displayDate, isReviewDue } from '../utils/presentation.mjs'
import LearningJourney from '../components/LearningJourney'

const { Paragraph, Text, Title } = Typography
const localDate = date => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(date)

function weekState(learningDays) {
  const todayKey = localDate(new Date())
  const monday = new Date(`${todayKey}T12:00:00+08:00`)
  monday.setUTCDate(monday.getUTCDate() - ((monday.getUTCDay() + 6) % 7))
  const activity = new Map(learningDays.map(item => [item.day, item.payload || {}]))
  return Array.from({ length: 7 }, (_, index) => {
    const date = new Date(monday); date.setUTCDate(monday.getUTCDate() + index)
    const key = localDate(date), payload = activity.get(key) || {}
    return { key, completed: Number(payload.reading_seconds || 0) > 0 || Number(payload.sentences || 0) > 0 || Number(payload.reviews || 0) > 0, future: key > todayKey }
  })
}

export default function WorkspacePage({ allBooks, selectScreen, openReader, openImport, learningDays, rewardStatus, vocabulary = [] }) {
  const week = useMemo(() => weekState(learningDays), [learningDays])
  const weekKeys = new Set(week.map(item => item.key))
  const minutes = Math.floor(learningDays.filter(item => weekKeys.has(item.day)).reduce((sum, day) => sum + Number(day.payload?.reading_seconds || 0), 0) / 60)
  const streak = Number(rewardStatus?.streak || 0)
  const goalPercent = Math.min(100, Math.round(minutes / 120 * 100))
  const activeBooks = allBooks.filter(book => book.shelfState !== 'later')
  const recent = [...activeBooks].filter(book => book.readingProgress?.updatedAt).sort((a, b) => new Date(b.readingProgress.updatedAt) - new Date(a.readingProgress.updatedAt))
  const continueBook = recent.find(book => !book.readingProgress?.completedAt) || activeBooks.find(book => !book.readingProgress?.completedAt) || activeBooks[0]
  const position = continueBook?.readingProgress?.sentencePosition
  const due = vocabulary.filter(item => isReviewDue(item)).length
  const others = activeBooks.filter(book => book.id !== continueBook?.id).sort((a, b) => (new Date(b.readingProgress?.updatedAt).getTime() || 0) - (new Date(a.readingProgress?.updatedAt).getTime() || 0)).slice(0, 3)
  return <div className="page-stack learning-workspace">
    <div className="page-intro"><div><Text className="eyebrow">{displayDate(new Date())} · 你的学习空间</Text><Title level={1}>{recent.length ? '接着上次，读懂下一句' : '从一篇感兴趣的内容开始'}</Title><Paragraph>原声听读、语境理解和生词复习，都从这里继续。</Paragraph></div><Button icon={<PlusOutlined />} onClick={openImport}>导入材料</Button></div>
    <LearningJourney continueBook={continueBook} selectScreen={selectScreen} openReader={openReader} />
    <Row gutter={[20, 20]}>
      <Col span={16}><Card className="hero-card"><div className="hero-card-content"><div className="hero-card-copy">
        <Text className="card-kicker">{continueBook ? position ? '继续上次学习' : continueBook.readingProgress?.completedAt ? '再次阅读' : '从这篇开始' : '开始你的第一次学习'}</Text>
        <Title level={2}>{continueBook?.title || '挑选读物，或者带上自己的材料'}</Title>
        <Paragraph>{continueBook?.subtitle || (continueBook ? continueBook.source : '去书城试读官方内容，或导入自己的文章、音频和视频。')}</Paragraph>
        {continueBook && <div className="continue-progress"><Text>{continueBook.readingProgress?.completedAt ? '已完成阅读' : position ? `上次停在第 ${position} / ${continueBook.sentenceCount} 句` : '还未开始阅读'}</Text>{position > 0 && <Progress percent={continueBook.progress} strokeColor="#2f6f50" showInfo={false} />}</div>}
        <Space wrap><Button type="primary" size="large" onClick={() => continueBook ? openReader(continueBook) : selectScreen('catalog')}>{continueBook ? position ? '继续学习' : continueBook.readingProgress?.completedAt ? '再次阅读' : '开始阅读' : '去书城挑选'} →</Button><Button size="large" onClick={() => continueBook ? selectScreen('library') : openImport()}>{continueBook ? '我的书架' : '导入自己的材料'}</Button></Space>
      </div>{continueBook && <Cover book={continueBook} large />}</div></Card></Col>
      <Col span={8}><Card className="daily-review-card"><div className="action-icon"><ReadOutlined /></div><Text className="card-kicker">生词复习</Text><Statistic title="当前待复习" value={due} suffix="个" /><Paragraph>{due ? '回到当时的语境，把读过的词记得更牢。' : vocabulary.length ? '到期生词已复习完，去读一段新内容吧。' : '阅读时收藏不熟悉的单词，在这里安排复习。'}</Paragraph><Button block onClick={() => selectScreen(due || vocabulary.length ? 'vocab' : 'catalog')}>{due ? '开始复习' : vocabulary.length ? '查看全部生词' : '去阅读，积累生词'}</Button></Card></Col>
    </Row>
    <Card className="weekly-learning-card"><div><Text className="card-kicker">本周积累</Text><Title level={3}>{minutes} <small>分钟听读</small></Title><Text type="secondary">{minutes >= 120 ? '已达到本周参考目标' : `距离每周 120 分钟参考目标还差 ${120 - minutes} 分钟`}{streak > 0 ? ` · 连续学习 ${streak} 天` : ''}</Text></div><div className="weekly-learning-progress"><Progress percent={goalPercent} showInfo={false} strokeColor="#2f6f50" /><div className="streak-days">{week.map((item, index) => <span className={item.completed ? 'done' : item.future ? 'future' : ''} key={item.key} title={`${item.key} ${item.completed ? '已学习' : item.future ? '尚未到来' : '暂无学习记录'}`}>{item.completed ? '✓' : ['一', '二', '三', '四', '五', '六', '日'][index]}</span>)}</div><Button type="link" onClick={() => selectScreen('stats')}>查看学习记录 →</Button></div></Card>
    <div className="section-header"><Title level={3}>书架中的其他读物</Title><Button type="link" onClick={() => selectScreen('library')}>查看全部</Button></div>
    {others.length ? <Row gutter={[16, 16]}>{others.map(book => <Col span={8} key={book.id}><Card className="book-card workspace-book-card"><Text type="secondary">{book.source}</Text><Title level={4}>{book.title}</Title><Text type="secondary">{book.readingProgress?.completedAt ? '已读完' : book.readingProgress?.sentencePosition ? `读至第 ${book.readingProgress.sentencePosition} 句` : '待开始'}</Text><Button type="link" onClick={() => openReader(book)}>打开读物 →</Button></Card></Col>)}</Row> : <Card className="workspace-discover"><BookOutlined /><div><Text strong>{continueBook ? '为下一次学习找一篇好内容' : '你的书架还空着'}</Text><Paragraph>先试读，再把适合自己的官方材料加入书架。</Paragraph></div><Button onClick={() => selectScreen('catalog')}>浏览书城</Button></Card>}
  </div>
}
