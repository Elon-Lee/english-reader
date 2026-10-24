import Cover from '../components/BookCover'
import React, { useState } from 'react'
import { Alert, Button, Card, Empty, Form, Modal, Progress, Select, Space, Tag, Typography } from 'antd'
import { ArrowRightOutlined, BookOutlined, CheckCircleOutlined, PlusOutlined, ReadOutlined, SettingOutlined } from '@ant-design/icons'
import { continueReadingBook, displayDate, learningDuration, openReview } from '../utils/presentation.mjs'
import { postJson } from '../api/client'
import LearningJourney from '../components/LearningJourney'

const { Paragraph, Text, Title } = Typography

export default function WorkspacePage({ allBooks, selectScreen, openReader, openImport, learning, onRefresh, messageApi }) {
  const [planOpen, setPlanOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')
  const [form] = Form.useForm()
  const { today, week, review, plan, days, learningStreak } = learning
  const continueBook = continueReadingBook(allBooks)
  const position = continueBook?.readingProgress?.sentencePosition
  const others = [...allBooks].filter(book => book.shelfState !== 'later' && book.canRead !== false && book.id !== continueBook?.id)
    .sort((a, b) => (Date.parse(b.readingProgress?.updatedAt) || 0) - (Date.parse(a.readingProgress?.updatedAt) || 0)).slice(0, 2)
  const readingDone = today.readingSeconds >= plan.readingMinutes * 60
  const reviewTarget = Math.min(plan.reviewWords, review.stats.total)
  const reviewDone = reviewTarget > 0 && today.reviewedWords >= reviewTarget && !review.active
  const complete = readingDone && (reviewDone || !reviewTarget)
  const reviewAction = () => openReview({ mode: review.active ? 'resume' : '', size: plan.reviewWords, scope: review.stats.due ? 'due' : 'all' })
  const readAction = () => continueBook ? openReader(continueBook) : selectScreen('catalog')
  const primaryAction = review.active || (!reviewDone && review.stats.due) ? reviewAction : readAction
  const primaryLabel = review.active ? '继续未完成的复习' : !reviewDone && review.stats.due ? '先复习，再继续听读' : continueBook ? '开始今天的听读' : '选一篇，开始学习'
  const changePlan = () => { form.setFieldsValue(plan); setSaveError(''); setPlanOpen(true) }
  const savePlan = async values => {
    if (saving) return
    setSaving(true); setSaveError('')
    try {
      await postJson('/api/workspace/learning/plan', values)
      await onRefresh()
      setPlanOpen(false); messageApi.success('学习计划已保存')
    } catch (error) { setSaveError(error.message) }
    finally { setSaving(false) }
  }
  const dayMap = new Map(days.map(day => [day.day, day.payload]))
  const weekDays = Array.from({ length: 7 }, (_, index) => {
    const date = new Date(week.start + 'T12:00:00Z'); date.setUTCDate(date.getUTCDate() + index)
    const key = date.toISOString().slice(0, 10), payload = dayMap.get(key) || {}
    const hasActivity = ['reading_seconds', 'sentences', 'reviews', 'shadow_attempts'].some(key => Number(payload[key]) > 0)
    return { key, hasActivity, payload, future: key > today.day }
  })
  return <div className="page-stack learning-workspace workspace-loop">
    <div className="page-intro"><div><Text className="eyebrow">{today.day} · 你的学习空间</Text><Title level={1}>{complete ? '今天的积累，已经留下来了' : '今天，从一小段开始'}</Title><Paragraph>接着听读，巩固生词，让每次学习都有收获。</Paragraph></div><Button icon={<PlusOutlined />} onClick={openImport}>导入材料</Button></div>
    <LearningJourney continueBook={continueBook} selectScreen={selectScreen} openReader={openReader} />
    <Card className="workspace-plan-card"><div className="workspace-plan-heading"><div><Text className="card-kicker">今日计划</Text><Title level={2}>{complete ? '今日计划已完成，按自己的节奏继续' : '一段听读，一轮回忆'}</Title><Paragraph>目标可以调整，成果按实际保存的学习记录计算。</Paragraph></div><Button type="text" icon={<SettingOutlined />} onClick={changePlan}>调整计划</Button></div>
      <div className="workspace-plan-tasks"><div><span className={readingDone ? 'task-state done' : 'task-state'}>{readingDone ? <CheckCircleOutlined /> : <ReadOutlined />}</span><div><Text strong>听读 {plan.readingMinutes} 分钟</Text><Text type="secondary">已保存 {learningDuration(today.readingSeconds)}</Text></div><Tag color={readingDone ? 'green' : undefined}>{readingDone ? '已完成' : '进行中'}</Tag></div>
        <div><span className={reviewDone ? 'task-state done' : 'task-state'}>{reviewDone ? <CheckCircleOutlined /> : <BookOutlined />}</span><div><Text strong>{reviewTarget ? '巩固 ' + reviewTarget + ' 个生词' : '从阅读中收藏生词'}</Text><Text type="secondary">{review.active ? '有一轮未完成，随时接着练' : reviewTarget ? '今日已练习 ' + today.reviewedWords + ' 词 · 按词条去重' : '有了生词，就能开始第一轮复习'}</Text></div><Tag color={reviewDone ? 'green' : undefined}>{reviewDone ? '已完成' : review.active ? '待继续' : reviewTarget ? '待巩固' : '待积累'}</Tag></div></div>
      <div className="workspace-plan-actions"><Button type="primary" size="large" icon={<ArrowRightOutlined />} onClick={primaryAction}>{complete ? '继续积累' : primaryLabel}</Button><Text type="secondary">听读时长是学习目标，可随时保存并休息。</Text></div>
    </Card>
    <div className="workspace-study-grid">
      <Card className="hero-card"><div className="hero-card-content"><div className="hero-card-copy"><Text className="card-kicker">{position ? '继续上次听读' : '你的下一段阅读'}</Text><Title level={2}>{continueBook?.title || '找到一篇想读懂的内容'}</Title><Paragraph>{continueBook?.subtitle || (continueBook ? continueBook.source : '先试读，再把合适的内容加入书架。')}</Paragraph>
        {continueBook && <div className="continue-progress"><Text>{continueBook.readingProgress?.completedAt ? '已读完，也可以再读一次' : position ? '上次停在第 ' + position + ' / ' + continueBook.sentenceCount + ' 句' : '还未开始阅读'}</Text><Progress percent={continueBook.progress} showInfo={false} strokeColor="#2f6f50" /></div>}
        <Space wrap><Button type="primary" onClick={readAction}>{continueBook ? '继续听读' : '去书城试读'} <ArrowRightOutlined /></Button><Button onClick={() => selectScreen('library')}>换一篇</Button></Space></div>{continueBook && <Cover book={continueBook} large />}</div></Card>
      <Card className="workspace-review-card"><Text className="card-kicker">复习安排</Text><Title level={2}>{review.active ? '把这一轮接着练完' : review.stats.due ? review.stats.due + ' 个词，等你再回忆一次' : '当前没有到期词'}</Title><Paragraph>{review.active ? '已练习 ' + review.active.completed + ' / ' + review.active.total + ' 词，评分已自动保存。' : review.stats.due ? '先回忆，再看答案；薄弱词会在本轮再练。' : review.stats.nextDueAt ? '下次复习：' + displayDate(review.stats.nextDueAt, true) : '阅读时收藏并补充释义，就能开始复习。'}</Paragraph>
        <Button block type={review.active ? 'primary' : 'default'} onClick={reviewAction}>{review.active ? '继续本轮复习' : review.stats.due ? '开始一轮 · 最多 ' + plan.reviewWords + ' 词' : review.stats.total ? '提前巩固一轮' : '查看生词复习'}</Button>
        {review.latest && <Button type="link" onClick={() => openReview({ mode: 'summary' })}>查看上次复习回顾 <ArrowRightOutlined /></Button>}</Card>
    </div>
    <Card className="workspace-results-card" title="今天，每一点积累都算数" extra={<Button type="link" onClick={() => selectScreen('stats')}>查看学习记录</Button>}><div className="workspace-result-grid"><div><b>{learningDuration(today.readingSeconds)}</b><span>已保存听读</span></div><div><b>{today.reviewedWords}<small> 词</small></b><span>实际复习 · 按词条去重</span></div><div><b>{today.newWords}<small> 词</small></b><span>新收藏生词</span></div><div><b>{learningStreak}<small> 天</small></b><span>连续学习 · 听读或练习</span></div></div><Text type="secondary">阅读位置自动保留；听读结束时点击“保存本次学习”，时长才会计入成果。</Text></Card>
    <Card className="weekly-learning-card"><div><Text className="card-kicker">本周节奏</Text><Title level={3}>{Math.floor(week.readingSeconds / 60)} / {plan.weeklyMinutes} <small>分钟听读</small></Title><Text type="secondary">勾选表示当天有听读或练习记录，签到单独记在成长奖励。</Text></div><div className="weekly-learning-progress" data-exceeded={week.readingSeconds >= plan.weeklyMinutes * 60 ? 'true' : 'false'}><Progress percent={Math.min(100, Math.floor(week.readingSeconds / (plan.weeklyMinutes * 60) * 100))} showInfo={false} strokeColor="#2f6f50" /><div className="weekly-streak-info" style={{display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 10, fontSize: 12, color: '#657064'}}><span>本周 {weekDays.filter(d => d.hasActivity && !d.future).length} / 7 天有学习记录</span></div><div className="streak-days">{weekDays.map((day, index) => <span tabIndex={0} role="img" aria-label={day.key + (day.future ? ' 尚未到来' : day.hasActivity ? ' 有学习记录' : ' 暂无学习记录')} title={day.key + ' · 听读 ' + learningDuration(Number(day.payload.reading_seconds) || 0) + ' · 复习 ' + (day.payload.reviews || 0) + ' 次'} className={day.hasActivity ? 'done' : day.future ? 'future' : ''} key={day.key}>{day.hasActivity ? <CheckCircleOutlined /> : ['一', '二', '三', '四', '五', '六', '日'][index]}</span>)}</div><Button type="link" onClick={changePlan}>调整每周目标</Button></div></Card>
    <div className="section-header"><Title level={3}>下一篇，继续读懂</Title><Button type="link" onClick={() => selectScreen('catalog')}>去书城发现内容</Button></div>
    <div className="workspace-next-grid">{others.length ? others.map(book => <Card className="workspace-next-book" key={book.id}><Text type="secondary">{book.source} · {book.readingProgress?.sentencePosition ? '读至第 ' + book.readingProgress.sentencePosition + ' 句' : '还未开始'}</Text><Title level={4}>{book.title}</Title>{book.readingProgress?.sentencePosition && <Progress percent={book.progress} showInfo={false} strokeColor="#2f6f50" size="small" style={{marginBottom: 12}} />}<Button type="default" icon={<ArrowRightOutlined />} onClick={() => openReader(book)}>打开读物</Button></Card>) : <Card><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="去书城找一篇感兴趣的内容,也可以导入自己的材料。"><Button onClick={() => selectScreen('catalog')}>浏览书城</Button></Empty></Card>}</div>
    <Modal title="调整学习计划" open={planOpen} onCancel={() => !saving && setPlanOpen(false)} onOk={() => form.submit()} confirmLoading={saving} okText="保存计划" cancelText="取消"><Paragraph type="secondary">先从容易坚持的目标开始。这是参考计划，不限制学习时长或复习次数。</Paragraph>{saveError && <Alert type="error" showIcon message={saveError} />}<Form form={form} layout="vertical" onFinish={savePlan}><Form.Item name="readingMinutes" label="每日听读目标"><Select disabled={saving} options={[5,10,15,20,30].map(value => ({value,label:value + ' 分钟'}))} /></Form.Item><Form.Item name="reviewWords" label="每日复习目标／每轮词数"><Select disabled={saving} options={[5,10,20].map(value => ({value,label:value + ' 词'}))} /></Form.Item><Form.Item name="weeklyMinutes" label="每周听读目标"><Select disabled={saving} options={[30,60,90,120,180,240,300].map(value => ({value,label:value + ' 分钟'}))} /></Form.Item></Form></Modal>
  </div>
}
