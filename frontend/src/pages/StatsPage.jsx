import React, { useMemo, useState } from 'react'
import { Button, Card, Col, Modal, Popover, Row, Segmented, Space, Statistic, Tooltip, Typography } from 'antd'
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

function Heatmap({ learningDays, range, allBooks }) {
  const [selectedDay, setSelectedDay] = useState(null)
  const [dragStart, setDragStart] = useState(null)
  const [dragEnd, setDragEnd] = useState(null)
  const [isDragging, setIsDragging] = useState(false)
  const [rangeAnalysis, setRangeAnalysis] = useState(null)

  const map = useMemo(() => new Map(learningDays.map(item => [item.day, item.payload || item])), [learningDays])
  const { start, end } = bounds(range)
  const leading = (start.getDay() + 6) % 7
  const cells = Array.from({ length: leading }, (_, index) => ({ empty: true, key: `empty-${index}` }))
  for (let day = new Date(start); day <= end; day.setDate(day.getDate() + 1)) {
    const key = dateKey(day)
    const payload = map.get(key) || {}
    cells.push({ key, payload, level: heatLevel(payload) })
  }

  // 计算里程碑
  const milestones = useMemo(() => {
    const activeDays = learningDays.filter(d =>
      ['reading_seconds', 'sentences', 'reviews', 'shadow_attempts'].some(key => Number(d.payload?.[key]) > 0)
    ).sort((a, b) => a.day.localeCompare(b.day))

    if (activeDays.length === 0) return []

    const marks = []
    const firstDay = activeDays[0]?.day

    // 第 1 天
    if (firstDay) {
      marks.push({ day: firstDay, label: '第 1 天', type: 'first' })
    }

    // 连续 7 天
    let currentStreak = 1
    let streakStart = firstDay
    for (let i = 1; i < activeDays.length; i++) {
      const prevDate = new Date(activeDays[i - 1].day)
      const currDate = new Date(activeDays[i].day)
      const dayDiff = Math.round((currDate - prevDate) / (1000 * 60 * 60 * 24))

      if (dayDiff === 1) {
        currentStreak++
        if (currentStreak === 7) {
          marks.push({ day: activeDays[i].day, label: '连续 7 天', type: 'streak' })
        } else if (currentStreak === 30) {
          marks.push({ day: activeDays[i].day, label: '连续 30 天', type: 'streak' })
        } else if (currentStreak === 100) {
          marks.push({ day: activeDays[i].day, label: '连续 100 天', type: 'streak' })
        }
      } else {
        currentStreak = 1
        streakStart = activeDays[i].day
      }
    }

    // 只保留在当前视图范围内的里程碑
    return marks.filter(m => {
      const mDate = new Date(m.day)
      return mDate >= start && mDate <= end
    })
  }, [learningDays, start, end])

  const getDayDetails = (dayKey) => {
    const dayData = learningDays.find(d => d.day === dayKey)
    if (!dayData?.payload) return null

    const minutes = Math.round(Number(dayData.payload.reading_seconds || 0) / 60)
    const sentences = Number(dayData.payload.sentences || 0)
    const reviews = Number(dayData.payload.reviews || 0)
    const lookups = Number(dayData.payload.lookups || 0)

    return { dayKey, minutes, sentences, reviews, lookups }
  }

  const handleCellClick = (cell) => {
    if (isDragging) return
    if (cell.empty || cell.level === 0) return
    const details = getDayDetails(cell.key)
    if (details) setSelectedDay(details)
  }

  // 拖选相关处理
  const handleMouseDown = (cell) => {
    if (cell.empty) return
    setIsDragging(true)
    setDragStart(cell.key)
    setDragEnd(cell.key)
  }

  const handleMouseEnter = (cell) => {
    if (isDragging && !cell.empty) {
      setDragEnd(cell.key)
    }
  }

  const handleMouseUp = () => {
    if (isDragging && dragStart && dragEnd) {
      // 计算范围分析
      const startDate = new Date(dragStart)
      const endDate = new Date(dragEnd)
      const [rangeStart, rangeEnd] = startDate <= endDate ? [dragStart, dragEnd] : [dragEnd, dragStart]

      const rangeDays = learningDays.filter(d => d.day >= rangeStart && d.day <= rangeEnd)
      const totalMinutes = Math.round(rangeDays.reduce((sum, d) => sum + Number(d.payload?.reading_seconds || 0), 0) / 60)
      const totalSentences = rangeDays.reduce((sum, d) => sum + Number(d.payload?.sentences || 0), 0)
      const totalWords = rangeDays.reduce((sum, d) => sum + Number(d.payload?.lookups || 0), 0)
      const activeDays = rangeDays.filter(d =>
        ['reading_seconds', 'sentences', 'reviews', 'shadow_attempts'].some(key => Number(d.payload?.[key]) > 0)
      ).length

      const dayCount = Math.round((new Date(rangeEnd) - new Date(rangeStart)) / (1000 * 60 * 60 * 24)) + 1

      setRangeAnalysis({
        start: rangeStart,
        end: rangeEnd,
        dayCount,
        activeDays,
        totalMinutes,
        totalSentences,
        totalWords,
        avgMinutes: activeDays > 0 ? Math.round(totalMinutes / activeDays) : 0
      })
    }
    setIsDragging(false)
    setDragStart(null)
    setDragEnd(null)
  }

  // 判断某个格子是否在拖选范围内
  const isInDragRange = (cellKey) => {
    if (!isDragging || !dragStart || !dragEnd) return false
    const startDate = new Date(dragStart)
    const endDate = new Date(dragEnd)
    const cellDate = new Date(cellKey)
    const [rangeStart, rangeEnd] = startDate <= endDate ? [startDate, endDate] : [endDate, startDate]
    return cellDate >= rangeStart && cellDate <= rangeEnd
  }

  return <>
    {/* 里程碑提示 */}
    {milestones.length > 0 && (
      <div className="heatmap-milestones">
        {milestones.map((m, i) => (
          <div key={i} className={`milestone milestone-${m.type}`}>
            <span className="milestone-icon">🎯</span>
            <Text className="milestone-label">{m.label}</Text>
            <Text type="secondary" className="milestone-date">({m.day})</Text>
          </div>
        ))}
      </div>
    )}

    <div
      className={`study-heatmap-modern range-${range}`}
      onMouseLeave={handleMouseUp}
      onMouseUp={handleMouseUp}
    >
      {cells.map(cell => cell.empty ? <i key={cell.key} className="heatmap-empty" /> :
        <i
          key={cell.key}
          tabIndex={cell.level > 0 ? 0 : -1}
          role={cell.level > 0 ? "button" : "img"}
          aria-label={`${cell.key} · 听读 ${Math.round(Number(cell.payload.reading_seconds || 0) / 60)} 分钟 · ${Number(cell.payload.sentences || 0)} 句次 · ${Number(cell.payload.reviews || 0)} 次复习`}
          className={`heat-level-${cell.level} ${cell.level > 0 ? 'clickable' : ''} ${isInDragRange(cell.key) ? 'in-drag-range' : ''}`}
          onClick={() => handleCellClick(cell)}
          onMouseDown={() => handleMouseDown(cell)}
          onMouseEnter={() => handleMouseEnter(cell)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              handleCellClick(cell)
            }
          }}
          title={`${cell.key} · ${Math.round(Number(cell.payload.reading_seconds || 0) / 60)} 分钟 · ${Number(cell.payload.sentences || 0)} 句 · ${Number(cell.payload.reviews || 0)} 次复习`}
        />
      )}
    </div>
    <div className="heatmap-footer"><Text type="secondary">{dateKey(start)} 至 {dateKey(end)} · {cells.filter(item => !item.empty).length} 天</Text><div className="heatmap-legend"><span>少</span>{[0, 1, 2, 3, 4].map(level => <i key={level} className={`heat-level-${level}`} />)}<span>多</span></div></div>

    {/* 单日详情 Modal */}
    <Modal
      open={!!selectedDay}
      onCancel={() => setSelectedDay(null)}
      footer={null}
      width={480}
      title={selectedDay ? `${selectedDay.dayKey} 学习详情` : ''}
    >
      {selectedDay && (
        <div className="day-detail-modal">
          <Row gutter={[12, 12]}>
            <Col span={12}>
              <Card size="small">
                <Statistic title="投入时长" value={selectedDay.minutes} suffix="分钟" />
              </Card>
            </Col>
            <Col span={12}>
              <Card size="small">
                <Statistic title="学习句次" value={selectedDay.sentences} suffix="句" />
              </Card>
            </Col>
            <Col span={12}>
              <Card size="small">
                <Statistic title="新增生词" value={selectedDay.lookups} suffix="个" />
              </Card>
            </Col>
            <Col span={12}>
              <Card size="small">
                <Statistic title="完成复习" value={selectedDay.reviews} suffix="次" />
              </Card>
            </Col>
          </Row>
          <Paragraph type="secondary" style={{ marginTop: 16, marginBottom: 0, fontSize: 12 }}>
            点击热力图的任意一天,查看当天的学习投入详情
          </Paragraph>
        </div>
      )}
    </Modal>

    {/* 范围分析 Modal */}
    <Modal
      open={!!rangeAnalysis}
      onCancel={() => setRangeAnalysis(null)}
      footer={null}
      width={560}
      title={rangeAnalysis ? `${rangeAnalysis.start} 至 ${rangeAnalysis.end} 范围分析` : ''}
    >
      {rangeAnalysis && (
        <div className="range-analysis-modal">
          <Row gutter={[16, 16]}>
            <Col span={12}>
              <Card size="small">
                <Statistic
                  title="时间跨度"
                  value={rangeAnalysis.dayCount}
                  suffix="天"
                  prefix={<Text type="secondary">共</Text>}
                />
              </Card>
            </Col>
            <Col span={12}>
              <Card size="small">
                <Statistic
                  title="活跃天数"
                  value={rangeAnalysis.activeDays}
                  suffix="天"
                  prefix={<Text type="secondary">学习</Text>}
                />
              </Card>
            </Col>
            <Col span={12}>
              <Card size="small">
                <Statistic title="累计投入" value={rangeAnalysis.totalMinutes} suffix="分钟" />
              </Card>
            </Col>
            <Col span={12}>
              <Card size="small">
                <Statistic title="平均投入" value={rangeAnalysis.avgMinutes} suffix="分钟/天" />
              </Card>
            </Col>
            <Col span={12}>
              <Card size="small">
                <Statistic title="学习句次" value={rangeAnalysis.totalSentences} suffix="句" />
              </Card>
            </Col>
            <Col span={12}>
              <Card size="small">
                <Statistic title="新增生词" value={rangeAnalysis.totalWords} suffix="个" />
              </Card>
            </Col>
          </Row>
          <Paragraph type="secondary" style={{ marginTop: 16, marginBottom: 0, fontSize: 12 }}>
            在热力图上按住鼠标拖动,可以选择一个日期范围查看该时段的学习统计
          </Paragraph>
        </div>
      )}
    </Modal>
  </>
}

function WeeklyTrend({ learningDays }) {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const weekStart = new Date(today)
  weekStart.setDate(today.getDate() - today.getDay())

  const weekData = Array.from({ length: 7 }, (_, i) => {
    const day = new Date(weekStart)
    day.setDate(weekStart.getDate() + i)
    const key = dateKey(day)
    const dayData = learningDays.find(d => d.day === key)
    const isToday = dateKey(today) === key
    const minutes = Math.round(Number(dayData?.payload?.reading_seconds || 0) / 60)
    return { day: ['日', '一', '二', '三', '四', '五', '六'][i], minutes, isToday }
  })

  const maxMinutes = Math.max(...weekData.map(d => d.minutes), 1)

  return <div className="stats-weekly-trend">
    {weekData.map((d, i) => (
      <div key={i} className="trend-bar">
        <div className={`bar-fill ${d.isToday ? 'today' : ''}`} style={{ height: `${(d.minutes / maxMinutes) * 100}%` }} />
        <Text className="bar-label">{d.day}</Text>
      </div>
    ))}
  </div>
}

export default function StatsPage({ allBooks, learningDays, learning, openReader }) {
  const [range, setRange] = useState('year')
  const [compareMode, setCompareMode] = useState(false)

  // 计算总体统计
  const readingSeconds = learningDays.reduce((sum, item) => sum + Number(item.payload?.reading_seconds || 0), 0)
  const dayCount = learningDays.filter(day => ['reading_seconds', 'sentences', 'reviews', 'shadow_attempts'].some(key => Number(day.payload?.[key]) > 0)).length
  const totalSentences = learningDays.reduce((sum, day) => sum + Number(day.payload?.sentences || 0), 0)
  const totalWords = learningDays.reduce((sum, day) => sum + Number(day.payload?.lookups || 0), 0)
  const totalReviews = learningDays.reduce((sum, day) => sum + Number(day.payload?.reviews || 0), 0)
  const due = learning.review.stats.due
  const continueBook = continueReadingBook(allBooks)

  // 计算本周统计
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const weekStart = new Date(today)
  weekStart.setDate(today.getDate() - today.getDay())
  const weekKeys = Array.from({ length: 7 }, (_, i) => {
    const day = new Date(weekStart)
    day.setDate(weekStart.getDate() + i)
    return dateKey(day)
  })
  const thisWeekDays = learningDays.filter(d => weekKeys.includes(d.day))
  const weekMinutes = Math.round(thisWeekDays.reduce((sum, d) => sum + Number(d.payload?.reading_seconds || 0), 0) / 60)
  const weekWords = thisWeekDays.reduce((sum, d) => sum + Number(d.payload?.lookups || 0), 0)

  // 计算上周统计用于对比
  const lastWeekStart = new Date(weekStart)
  lastWeekStart.setDate(weekStart.getDate() - 7)
  const lastWeekKeys = Array.from({ length: 7 }, (_, i) => {
    const day = new Date(lastWeekStart)
    day.setDate(lastWeekStart.getDate() + i)
    return dateKey(day)
  })
  const lastWeekDays = learningDays.filter(d => lastWeekKeys.includes(d.day))
  const lastWeekMinutes = Math.round(lastWeekDays.reduce((sum, d) => sum + Number(d.payload?.reading_seconds || 0), 0) / 60)
  const weekComparison = weekMinutes - lastWeekMinutes

  const todayKey = dateKey(today)
  const todayData = learningDays.find(d => d.day === todayKey)
  const todayReviews = Number(todayData?.payload?.reviews || 0)

  // 生成动态身份标题
  const getIdentityTitle = () => {
    if (dayCount >= 30) return '持续学习者'
    if (dayCount >= 7) return '学习习惯正在养成'
    if (dayCount >= 3) return '学习之路已开启'
    return '开始学习之旅'
  }

  // 计算学习节奏洞察
  const getInsights = useMemo(() => {
    if (learningDays.length < 7) return []

    const insights = []
    const activeDays = learningDays.filter(d =>
      ['reading_seconds', 'sentences', 'reviews', 'shadow_attempts'].some(key => Number(d.payload?.[key]) > 0)
    )

    // 计算最长连续学习天数
    let maxStreak = 0
    let currentStreak = 1
    const sortedDays = [...activeDays].sort((a, b) => a.day.localeCompare(b.day))
    for (let i = 1; i < sortedDays.length; i++) {
      const prevDate = new Date(sortedDays[i - 1].day)
      const currDate = new Date(sortedDays[i].day)
      const dayDiff = Math.round((currDate - prevDate) / (1000 * 60 * 60 * 24))
      if (dayDiff === 1) {
        currentStreak++
      } else {
        maxStreak = Math.max(maxStreak, currentStreak)
        currentStreak = 1
      }
    }
    maxStreak = Math.max(maxStreak, currentStreak)

    if (maxStreak >= 7) {
      insights.push({ type: 'streak', text: `最长连续学习 ${maxStreak} 天,保持规律是学习的关键` })
    }

    // 计算平均每天学习时长
    if (activeDays.length >= 7) {
      const avgMinutes = Math.round(readingSeconds / 60 / activeDays.length)
      if (avgMinutes >= 20) {
        insights.push({ type: 'time', text: `平均每次投入 ${avgMinutes} 分钟,深度学习习惯已养成` })
      } else if (avgMinutes >= 10) {
        insights.push({ type: 'time', text: `平均每次投入 ${avgMinutes} 分钟,保持这个节奏` })
      }
    }

    // 计算最活跃的星期几(需要至少4周数据)
    if (activeDays.length >= 28) {
      const weekdayCounts = [0, 0, 0, 0, 0, 0, 0]
      activeDays.forEach(d => {
        const date = new Date(d.day)
        const weekday = date.getDay()
        weekdayCounts[weekday]++
      })
      const maxCount = Math.max(...weekdayCounts)
      const mostActiveDay = weekdayCounts.indexOf(maxCount)
      const dayNames = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
      if (maxCount >= 4) {
        insights.push({ type: 'pattern', text: `${dayNames[mostActiveDay]}是你最活跃的学习日,规律作息助力坚持` })
      }
    }

    // 计算近期趋势(最近两周对比)
    if (activeDays.length >= 14) {
      const recentTwoWeeks = activeDays.filter(d => {
        const date = new Date(d.day)
        const daysAgo = Math.round((today - date) / (1000 * 60 * 60 * 24))
        return daysAgo <= 14
      })
      const lastWeek = recentTwoWeeks.filter(d => {
        const date = new Date(d.day)
        const daysAgo = Math.round((today - date) / (1000 * 60 * 60 * 24))
        return daysAgo <= 7
      })
      const weekBefore = recentTwoWeeks.filter(d => {
        const date = new Date(d.day)
        const daysAgo = Math.round((today - date) / (1000 * 60 * 60 * 24))
        return daysAgo > 7 && daysAgo <= 14
      })
      const lastWeekMinutes = lastWeek.reduce((sum, d) => sum + Number(d.payload?.reading_seconds || 0), 0) / 60
      const weekBeforeMinutes = weekBefore.reduce((sum, d) => sum + Number(d.payload?.reading_seconds || 0), 0) / 60
      if (lastWeekMinutes > weekBeforeMinutes * 1.2) {
        insights.push({ type: 'trend', text: '最近一周投入明显增加,保持这个势头 📈' })
      }
    }

    return insights
  }, [learningDays, dayCount, readingSeconds, today])

  return <div className="page-stack">
    <div className="page-intro">
      <div>
        <Text className="eyebrow">LEARNING INSIGHTS</Text>
        <Title level={1}>学习记录</Title>
        <Paragraph>查看学习节奏,了解自己的成长轨迹</Paragraph>
      </div>
      <Button onClick={() => { location.href = '/api/account/export' }}>下载学习报告</Button>
    </div>

    <div className="stats-page">
      {/* 英雄卡：学习身份认同 */}
      <Card className="stats-hero-card">
      <div className="stats-hero-content">
        <div className="hero-identity">
          <Title level={2}>{getIdentityTitle()}</Title>
          <Text className="hero-summary">已坚持 <strong>{dayCount}</strong> 天 · 累计 <strong>{Math.round(readingSeconds / 60)}</strong> 分钟原音</Text>
        </div>
        <WeeklyTrend learningDays={learningDays} />
      </div>
    </Card>

    {/* 三栏关键指标 */}
    <Row gutter={[16, 16]} className="stats-metrics-row">
      <Col span={8}>
        <Card className="metric-card">
          <Statistic title="听读投入" value={Math.round(readingSeconds / 60)} suffix="分钟" />
          {weekMinutes > 0 && <Text type="secondary" className="metric-delta">本周 +{weekMinutes} 分钟</Text>}
        </Card>
      </Col>
      <Col span={8}>
        <Card className="metric-card">
          <Statistic title="生词积累" value={totalWords} suffix="个新词" />
          {weekWords > 0 && <Text type="secondary" className="metric-delta">本周 +{weekWords} 个</Text>}
        </Card>
      </Col>
      <Col span={8}>
        <Card className="metric-card">
          <Statistic title="等你复习" value={due} suffix="个" />
          {todayReviews > 0 && <Text type="secondary" className="metric-delta">今天 ↓{todayReviews} 个</Text>}
        </Card>
      </Col>
    </Row>

    {/* 热力图 */}
    <Card
      title="学习热力图"
      extra={
        <Space>
          <Segmented
            size="small"
            value={compareMode ? 'compare' : 'standard'}
            onChange={(val) => setCompareMode(val === 'compare')}
            options={[
              { label: '标准视图', value: 'standard' },
              { label: '对比视图', value: 'compare' }
            ]}
          />
          <Segmented
            value={range}
            onChange={setRange}
            options={[
              { label: '周', value: 'week' },
              { label: '月', value: 'month' },
              { label: '年', value: 'year' }
            ]}
          />
        </Space>
      }
    >
      {compareMode && range === 'week' && weekComparison !== 0 && (
        <div className="heatmap-comparison-hint">
          <Text type="secondary">
            本周 vs 上周: {weekComparison > 0 ? `增加 ${weekComparison} 分钟` : `减少 ${Math.abs(weekComparison)} 分钟`}
            {weekComparison > 0 ? ' 📈' : ' 📉'}
          </Text>
        </div>
      )}
      <Heatmap learningDays={learningDays} range={range} allBooks={allBooks} compareMode={compareMode} />
    </Card>

    {/* 学习节奏洞察 + 继续学习 */}
    {/* 继续学习 */}
    {continueBook && (
      <Card title="继续学习" className="stats-continue-card">
        <div className="stats-next-step">
          <div className="stats-continue-content">
            <Text className="eyebrow">CONTINUE LEARNING</Text>
            <Title level={4} style={{ margin: '8px 0' }}>{continueBook.title}</Title>
            <div className="continue-meta">
              {continueBook.readingProgress?.progress !== undefined && (
                <Text type="secondary">已读 {Math.round(continueBook.readingProgress.progress * 100)}%</Text>
              )}
              {continueBook.duration && continueBook.readingProgress?.progress !== undefined && (
                <>
                  <Text type="secondary">·</Text>
                  <Text type="secondary">
                    预计 {Math.round(continueBook.duration * (1 - continueBook.readingProgress.progress) / 60)} 分钟读完
                  </Text>
                </>
              )}
            </div>
            <Paragraph className="continue-hint">回到上次停下的地方,保持学习节奏</Paragraph>
          </div>
          <Button type="primary" onClick={() => openReader(continueBook)}>继续阅读 →</Button>
        </div>
      </Card>
    )}

    {/* 学习洞察 */}
    {getInsights.length > 0 && (
      <Card title="学习洞察" className="stats-insights-card">
        <div className="insights-list">
          {getInsights.map((insight, i) => (
            <div key={i} className={`insight-item insight-${insight.type}`}>
              <span className="insight-icon">
                {insight.type === 'streak' && '🔥'}
                {insight.type === 'time' && '⏱️'}
                {insight.type === 'pattern' && '📅'}
                {insight.type === 'trend' && '📊'}
              </span>
              <Text>{insight.text}</Text>
            </div>
          ))}
        </div>
      </Card>
    )}
    </div>
  </div>
}
