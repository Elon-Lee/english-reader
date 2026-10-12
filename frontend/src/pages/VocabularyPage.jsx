import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Button, Card, Col, Empty, Input, List, Pagination, Row, Segmented, Space, Statistic, Tag, Typography } from 'antd'
import { CustomerServiceOutlined, PauseOutlined, PlayCircleOutlined } from '@ant-design/icons'

import { postJson } from '../api/client'
import { DEFAULT_PREFERENCES } from '../config/preferences'

const { Paragraph, Text, Title } = Typography

function dueTime(payload) {
  const time = new Date(payload?.due_at || payload?.dueAt || 0).getTime()
  return Number.isFinite(time) ? time : 0
}

export default function VocabularyPage({ vocabulary, allBooks, selectScreen, preferences, onRefresh, messageApi }) {
  const settings = { ...DEFAULT_PREFERENCES, ...(preferences || {}) }
  const [filter, setFilter] = useState('today')
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)
  const [mode, setMode] = useState('review')
  const [layout, setLayout] = useState('list')
  const [dictationIndex, setDictationIndex] = useState(-1)
  const [dictationRunning, setDictationRunning] = useState(false)
  const dictationTimer = useRef(null)
  const dictationRunningRef = useRef(false)
  const now = Date.now()

  const filtered = useMemo(() => (vocabulary || []).filter(item => {
    const payload = item.payload || {}
    const matches = `${payload.word || payload.form || ''} ${payload.meaning || ''} ${payload.context || ''}`.toLowerCase().includes(query.toLowerCase())
    if (!matches) return false
    if (filter === 'today') return !dueTime(payload) || dueTime(payload) <= now
    if (filter === 'mastered') return ['good', 'easy'].includes(payload.rating)
    if (filter === 'difficult') return ['again', 'hard', 'unknown'].includes(payload.rating || 'unknown')
    return true
  }).sort((a, b) => dueTime(a.payload) - dueTime(b.payload)), [filter, now, query, vocabulary])
  const pageSize = Number(settings.reviewPageSize) || 10
  const visible = filtered.slice((page - 1) * pageSize, page * pageSize)

  useEffect(() => { setPage(1) }, [filter, mode, query])
  useEffect(() => () => { clearTimeout(dictationTimer.current); speechSynthesis.cancel() }, [])

  const rate = async (item, rating) => {
    const intervals = { again: 1, hard: 2, good: 4, easy: 8 }
    const days = intervals[rating]
    try {
      await postJson('/api/workspace/vocabulary', {
        bookId: item.bookId,
        sentenceId: item.sentenceId,
        wordIndex: item.wordIndex,
        payload: { ...(item.payload || {}), rating, interval_days: days, due_at: new Date(Date.now() + days * 86400000).toISOString(), reviews: Number(item.payload?.reviews || 0) + 1, last_reviewed_at: new Date().toISOString() },
      })
      await postJson('/api/workspace/activity', {
        bookId: item.bookId,
        readingSeconds: 0,
        sentences: 0,
        reviews: 1,
        lastSentenceId: item.sentenceId,
        idempotencyKey: `vocab-review-${item.id}-${crypto.randomUUID?.() || Date.now()}`,
      })
      await onRefresh?.()
      messageApi.success('复习结果已记录')
    } catch (error) { messageApi.error(error.message) }
  }

  const speak = (item, onEnd) => {
    speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(item.payload?.word || item.payload?.form || '')
    utterance.lang = 'en-US'
    utterance.rate = .78
    utterance.onend = onEnd
    utterance.onerror = onEnd
    speechSynthesis.speak(utterance)
  }

  const playDictationWord = (index, repeat = 0) => {
    if (!dictationRunningRef.current || index >= filtered.length) {
      dictationRunningRef.current = false
      setDictationRunning(false)
      return
    }
    setDictationIndex(index)
    speak(filtered[index], () => {
      if (repeat + 1 < Number(settings.manualRepeatCount)) {
        dictationTimer.current = setTimeout(() => playDictationWord(index, repeat + 1), 280)
      } else {
        dictationTimer.current = setTimeout(() => playDictationWord(index + 1, 0), Number(settings.manualPauseSeconds) * 1000)
      }
    })
  }

  const startDictation = () => {
    if (!filtered.length) return
    dictationRunningRef.current = true
    setDictationRunning(true)
    setTimeout(() => playDictationWord(dictationIndex >= 0 ? dictationIndex : 0, 0), 0)
  }

  const pauseDictation = () => {
    clearTimeout(dictationTimer.current)
    speechSynthesis.cancel()
    dictationRunningRef.current = false
    setDictationRunning(false)
  }

  const list = <List dataSource={visible} locale={{ emptyText: <Empty description="当前筛选条件下没有生词" /> }} renderItem={item => {
    const payload = item.payload || {}
    const book = allBooks.find(bookItem => bookItem.id === item.bookId)
    return <List.Item className="vocab-review-item" actions={mode === 'review' ? [['again', '忘记'], ['hard', '困难'], ['good', '记得'], ['easy', '简单']].map(([value, label]) => <Button key={value} size="small" onClick={() => rate(item, value)}>{label}</Button>) : [<Button key="listen" icon={<CustomerServiceOutlined />} onClick={() => speak(item)}>发音</Button>] }><List.Item.Meta title={<Space><Text strong className="vocab-word">{payload.word || payload.form || '未命名单词'}</Text><Tag color={payload.rating === 'easy' ? 'success' : payload.rating === 'again' ? 'error' : 'default'}>{payload.rating || '待复习'}</Tag></Space>} description={<div className="vocab-description"><Text>{payload.meaning || '尚未填写释义'}</Text>{payload.context && <Paragraph ellipsis={{ rows: 2 }}>“{payload.context}”</Paragraph>}<Text type="secondary">{book?.title || item.bookId} · 下次复习 {payload.due_at ? new Date(payload.due_at).toLocaleString('zh-CN') : '现在'}</Text></div>} /></List.Item>
  }} />
  const cards = <Row gutter={[16, 16]}>{visible.map(item => {
    const payload = item.payload || {}
    const book = allBooks.find(bookItem => bookItem.id === item.bookId)
    return <Col span={8} key={item.id}><Card className="vocab-tile" title={<Space><Text className="vocab-word">{payload.word || payload.form || '未命名单词'}</Text><Tag>{payload.rating || '待复习'}</Tag></Space>} extra={<Button type="text" icon={<CustomerServiceOutlined />} onClick={() => speak(item)} />}><Paragraph className="vocab-tile-meaning">{payload.meaning || '尚未填写释义'}</Paragraph>{payload.context && <Paragraph ellipsis={{ rows: 3 }}>“{payload.context}”</Paragraph>}<Text type="secondary">{book?.title || item.bookId}</Text>{mode === 'review' && <div className="vocab-tile-actions">{[['again', '忘记'], ['hard', '困难'], ['good', '记得'], ['easy', '简单']].map(([value, label]) => <Button key={value} size="small" onClick={() => rate(item, value)}>{label}</Button>)}</div>}</Card></Col>
  })}{!visible.length && <Col span={24}><Empty description="当前筛选条件下没有生词" /></Col>}</Row>

  return <div className="page-stack"><div className="page-intro"><div><Text className="eyebrow">VOCABULARY REVIEW</Text><Title level={1}>生词复习</Title><Paragraph>基于真实阅读语境进行间隔复习，评分会更新下次复习时间并写入学习记录。</Paragraph></div><Button onClick={() => selectScreen('library')}>回到书架</Button></div><Row gutter={[16, 16]}><Col span={8}><Card><Statistic title="全部生词" value={vocabulary.length} suffix="个" /></Card></Col><Col span={8}><Card><Statistic title="今日到期" value={vocabulary.filter(item => !dueTime(item.payload) || dueTime(item.payload) <= now).length} suffix="个" /></Card></Col><Col span={8}><Card><Statistic title="来源读物" value={new Set(vocabulary.map(item => item.bookId)).size} suffix="本" /></Card></Col></Row><Card className="filter-card"><Space wrap><Segmented value={mode} onChange={setMode} options={[{ label: '单词复习', value: 'review' }, { label: '听写模式', value: 'dictation' }]} /><Segmented value={layout} onChange={setLayout} options={[{ label: '列表', value: 'list' }, { label: '卡片平铺', value: 'grid' }]} /><Segmented value={filter} onChange={setFilter} options={[{ label: '今日到期', value: 'today' }, { label: '困难词', value: 'difficult' }, { label: '已掌握', value: 'mastered' }, { label: '全部', value: 'all' }]} /><Input.Search allowClear value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索单词、释义或语境" style={{ width: 260 }} /></Space></Card>{mode === 'dictation' && <Card className="dictation-controller"><Space><Button type="primary" icon={<PlayCircleOutlined />} disabled={dictationRunning || !filtered.length} onClick={startDictation}>开始听写</Button><Button icon={<PauseOutlined />} disabled={!dictationRunning} onClick={pauseDictation}>暂停</Button><Button onClick={() => { pauseDictation(); setDictationIndex(Math.max(-1, dictationIndex - 1)) }}>上一个</Button><Button onClick={() => { pauseDictation(); setDictationIndex(Math.min(filtered.length - 1, dictationIndex + 1)) }}>下一个</Button></Space><Text type="secondary">每词朗读 {settings.manualRepeatCount} 遍，词间停顿 {settings.manualPauseSeconds} 秒。当前：{dictationIndex >= 0 ? `${dictationIndex + 1} / ${filtered.length}` : '未开始'}</Text></Card>}<Card title={mode === 'review' ? '复习队列' : '听写词表'}>{layout === 'grid' ? cards : list}{filtered.length > pageSize && <div className="list-pagination"><Pagination current={page} pageSize={pageSize} total={filtered.length} showSizeChanger={false} showTotal={total => `共 ${total} 个`} onChange={setPage} /></div>}</Card></div>
}
