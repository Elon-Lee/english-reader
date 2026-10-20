import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Alert, Button, Card, Empty, Input, List, Pagination, Progress, Segmented, Select, Skeleton, Space, Tag, Typography } from 'antd'
import { ArrowLeftOutlined, ArrowRightOutlined, BookOutlined, CheckCircleOutlined, ClockCircleOutlined, EyeOutlined, FlagOutlined, ReadOutlined, ReloadOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { getJson, postJson } from '../api/client'
import { displayDate, isReviewDue } from '../utils/presentation.mjs'

const { Paragraph, Text, Title } = Typography
const ratings = [
  { value: 'again', label: '忘记', detail: '10 分钟后再复习', className: 'again' },
  { value: 'hard', label: '模糊', detail: '明天再复习', className: 'hard' },
  { value: 'good', label: '记得', detail: '延长复习间隔', className: 'good' },
  { value: 'easy', label: '轻松', detail: '更久以后再复习', className: 'easy' },
]
const ratingNames = { again: '需巩固', hard: '需巩固', good: '最近记得', easy: '最近记得', unknown: '待学习' }
const wordOf = item => item?.payload?.word || item?.payload?.form || '未命名单词'
const makeKey = () => crypto.randomUUID()

function returnToSource(item) {
  const url = new URL(location.href)
  url.search = new URLSearchParams({ screen: 'reader', reader: item.official ? 'official' : 'workspace', id: item.bookId, sentence: item.sentenceId }).toString()
  location.href = url.toString()
}

function WordRows({ items, showMeaning = false }) {
  return <List className="review-word-list" dataSource={items} renderItem={item => <List.Item actions={[
    <Button key="source" type="text" onClick={() => returnToSource(item)} icon={<ArrowRightOutlined />}>回原文</Button>,
  ]}><List.Item.Meta title={<Space><Text strong>{wordOf(item)}</Text><Tag>{ratingNames[item.payload?.rating] || '待学习'}</Tag></Space>}
    description={<><span className="review-source-name">{item.bookTitle}</span>{showMeaning && <div className="review-notebook-meaning">{item.payload?.meaning || '暂无释义，回原文补充后再复习'}</div>}</>} />
    <Text className="review-next-date" type="secondary">{isReviewDue(item) ? '现在可复习' : `下次 ${displayDate(item.payload?.due_at || item.payload?.dueAt)}`}</Text>
  </List.Item>} />
}

function RecallCard({ session, busy, pending, error, onAnswer, onRetry, onSync, onPause }) {
  const [revealed, setRevealed] = useState(false)
  const [hinted, setHinted] = useState(false)
  const revealRef = useRef(null)
  const answerRef = useRef(null)
  const item = session.current?.item
  const payload = item?.payload || {}
  const available = Boolean(item && String(payload.meaning || '').trim())
  useEffect(() => { revealRef.current?.focus() }, [])
  useEffect(() => { if (revealed) answerRef.current?.focus() }, [revealed])
  return <div className="review-practice">
    <div className="review-practice-top"><Button icon={<ArrowLeftOutlined />} disabled={busy || pending} onClick={onPause}>暂停并返回</Button><Text type="secondary" role="status">每次评分自动保存 · 可随时回来继续</Text></div>
    <div className="review-practice-progress"><div><Text strong>{session.current?.repeated ? '薄弱词巩固' : '词义回忆'}</Text><Text type="secondary">已练习 {session.completed} / {session.total} 个词{session.skipped ? ` · 已跳过 ${session.skipped} 词` : ''}{session.attemptTotal > session.total ? ` · 含 ${session.attemptTotal - session.total} 道巩固题` : ''}</Text></div><Progress percent={Math.round(session.step / session.attemptTotal * 100)} showInfo={false} strokeColor="#2f6f50" /></div>
    <Card className="review-recall-card">
      <div className="review-recall-eyebrow"><Tag color="green">{session.current?.repeated ? '再回忆一次' : '先回忆，再看答案'}</Tag><span>第 {session.step + 1} / {session.attemptTotal} 题</span></div>
      {item ? <>
        <Text className="review-card-source"><BookOutlined /> {item.bookTitle}</Text>
        <Title level={2} className="review-target-word">{wordOf(item)}</Title>
        <Paragraph className="review-recall-prompt">还记得它在阅读中的意思吗？</Paragraph>
        {!revealed && <div className="review-hint-area">{hinted ? <blockquote>{payload.context || '这条生词没有保存原句。'}</blockquote> : <Button type="text" icon={<EyeOutlined />} disabled={!payload.context} onClick={() => setHinted(true)}>看原句提示</Button>}</div>}
        {revealed ? <div className="review-answer" role="region" aria-label="单词答案"><Text className="card-kicker">语境释义</Text><Paragraph className="review-answer-meaning">{payload.meaning || '暂无释义，请回原文补充。'}</Paragraph>{payload.context && <blockquote>{payload.context}</blockquote>}{payload.note && <Paragraph type="secondary">我的笔记：{payload.note}</Paragraph>}<Button type="link" onClick={() => returnToSource(item)}>回原文查看上下文 <ArrowRightOutlined /></Button></div> : <Button ref={revealRef} type="primary" size="large" className="review-reveal-button" onClick={() => setRevealed(true)}>显示答案 <span className="review-key-hint">Enter</span></Button>}
      </> : <Empty description="这条生词的来源已不可访问，跳过后可继续本轮复习。" />}
      {error && <Alert className="review-submit-error" type="error" showIcon message={error} action={<Space>{pending && <Button size="small" onClick={onRetry} loading={busy}>重试保存</Button>}<Button size="small" disabled={busy} onClick={onSync}>同步进度</Button></Space>} />}
      {revealed && available && <div className="review-rating-section"><Text type="secondary">按刚才的回忆选择；这是自评，不是答题正确率。</Text><div className="review-rating-grid">{ratings.map((rating, index) => <Button ref={index === 0 ? answerRef : undefined} key={rating.value} className={`review-rating ${rating.className}`} loading={busy && pending?.rating === rating.value} disabled={busy || Boolean(pending)} onClick={() => onAnswer(rating.value, hinted)}><b>{rating.label}</b><span>{hinted || session.current?.repeated ? rating.value === 'again' ? '10 分钟后再复习' : '明天再复习' : rating.detail}</span></Button>)}</div></div>}
      <div className="review-card-footer"><Text type="secondary">{hinted ? '本题使用过原句提示' : '先给自己一点独立回忆的时间'}</Text><Button type="text" disabled={busy || Boolean(pending)} onClick={() => onAnswer('skip', hinted)}>{available ? '暂时跳过' : '跳过，继续下一词'}</Button></div>
    </Card>
    <Paragraph className="review-practice-note"><CheckCircleOutlined /> 忘记或模糊的词会在本轮末尾再练一次；仍需巩固也可以完成本轮。</Paragraph>
  </div>
}

export default function VocabularyPage({ selectScreen }) {
  const entry = useRef(new URLSearchParams(location.search))
  const selectedIds = useRef([...new Set((entry.current.get('words') || '').split(',').filter(value => /^\d+$/.test(value)).map(Number))].slice(0, 100))
  const [data, setData] = useState(null)
  const [loadError, setLoadError] = useState('')
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('today')
  const [view, setView] = useState('home')
  const [session, setSession] = useState(null)
  const [size, setSize] = useState([5, 10, 20].includes(Number(entry.current.get('size'))) ? Number(entry.current.get('size')) : 10)
  const [scope, setScope] = useState(selectedIds.current.length ? 'selected' : ['due', 'difficult', 'all'].includes(entry.current.get('scope')) ? entry.current.get('scope') : 'due')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [pending, setPending] = useState(null)
  const [query, setQuery] = useState('')
  const [source, setSource] = useState('all')
  const [filter, setFilter] = useState('all')
  const [page, setPage] = useState(1)
  const requestRef = useRef(null)
  const startRef = useRef(null)
  const alive = useRef(true)
  const loadSequence = useRef(0)
  const load = useCallback(async () => {
    const sequence = ++loadSequence.current
    const next = await getJson('/api/workspace/review')
    if (alive.current && sequence === loadSequence.current) { setData(next); setLoadError('') }
    return next
  }, [])
  useEffect(() => {
    alive.current = true
    load().then(next => {
      if (!alive.current) return
      const session = entry.current.get('review') === 'summary' ? next.latest : entry.current.get('review') === 'resume' ? next.active : null
      if (session) { setSession(session); setView(session.status === 'active' ? 'practice' : 'summary') }
    }).catch(e => { if (alive.current) setLoadError(e.message) }).finally(() => { if (alive.current) setLoading(false) })
    return () => { alive.current = false }
  }, [load])
  useEffect(() => { setPage(1) }, [query, source, filter])
  const begin = async (startScope = scope) => {
    if (requestRef.current) return
    requestRef.current = true
    setBusy(true); setError('')
    if (!startRef.current || startRef.current.scope !== startScope || startRef.current.size !== size) startRef.current = { size, scope: startScope, ...(startScope === 'selected' ? { vocabularyIds: selectedIds.current } : {}), idempotencyKey: makeKey() }
    try {
      const result = await postJson('/api/workspace/review/start', startRef.current)
      if (!alive.current) return
      startRef.current = null
      setSession(result.session); setView(result.session.status === 'completed' ? 'summary' : 'practice')
      setData(previous => ({ ...previous, active: result.session.status === 'active' ? result.session : null }))
    } catch (e) { if (alive.current) setError(e.message) }
    finally { requestRef.current = null; if (alive.current) setBusy(false) }
  }
  const submit = async attempt => {
    if (requestRef.current) return
    requestRef.current = true
    setBusy(true); setError(''); setPending(attempt)
    try {
      const result = await postJson('/api/workspace/review/answer', attempt)
      if (!alive.current) return
      setSession(result.session); setPending(null)
      setData(previous => ({ ...previous, active: result.session.status === 'active' ? result.session : null }))
      if (result.session.status === 'completed') setView('summary')
      load().catch(e => { if (alive.current) setLoadError(`成绩已保存，统计暂未刷新：${e.message}`) })
    } catch (e) { if (alive.current) setError(e.message) }
    finally { requestRef.current = null; if (alive.current) setBusy(false) }
  }
  const sync = async () => {
    if (requestRef.current) return
    setBusy(true)
    try {
      const next = await load()
      setPending(null); setError(''); setSession(next.active || next.latest)
      setView(next.active ? 'practice' : next.latest ? 'summary' : 'home')
    } catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }
  if (loading) return <Skeleton active paragraph={{ rows: 10 }} />
  if (!data) return <Alert type="error" showIcon message="复习计划暂时无法加载" description={loadError} action={<Button onClick={() => { setLoading(true); load().catch(e => setLoadError(e.message)).finally(() => setLoading(false)) }}>重试</Button>} />

  const { stats, items } = data
  const due = items.filter(item => isReviewDue(item))
  const difficult = items.filter(item => ['again', 'hard'].includes(item.payload?.rating))
  const selected = items.filter(item => selectedIds.current.includes(item.id))
  const candidates = scope === 'selected' ? selected : scope === 'due' ? due : scope === 'difficult' ? difficult : items
  const sources = [...new Map(items.map(item => [item.bookId, item])).values()]
  const preview = [...(due.length ? due : items)].sort((a, b) => new Date(a.payload?.due_at || 0) - new Date(b.payload?.due_at || 0)).slice(0, 5)
  const filtered = items.filter(item => (source === 'all' || item.bookId === source) && (filter === 'all' || filter === 'due' && isReviewDue(item) || filter === 'difficult' && ['again', 'hard'].includes(item.payload?.rating)) && `${wordOf(item)} ${item.payload?.meaning || ''} ${item.payload?.context || ''}`.toLowerCase().includes(query.toLowerCase()))

  if (view === 'practice' && session?.current) return <RecallCard key={`${session.id}-${session.step}`} session={session} busy={busy} pending={pending} error={error} onAnswer={(rating, hinted) => submit({ sessionId: session.id, step: session.step, rating, hinted, attemptKey: makeKey() })} onRetry={() => pending && submit(pending)} onSync={sync} onPause={() => { setView('home'); setError('') }} />

  if (view === 'summary' && session) return <div className="page-stack review-summary">
    <Button type="text" icon={<ArrowLeftOutlined />} className="review-back-home" onClick={() => { setView('home'); setError('') }}>返回今日复习</Button>
    <Card className="review-summary-hero"><CheckCircleOutlined className="review-summary-icon" /><Text className="eyebrow">SESSION COMPLETE</Text><Title level={1}>{session.completed ? '这一轮，积累已保存' : '这一轮已结束'}</Title><Paragraph>{session.completed ? '已安排后续复习。' : '跳过的词未计入学习成果，可在下一轮继续。'}{session.weakCount ? '还有一些词需要慢慢巩固，下一次继续。' : '带着刚刚复习的词，回到阅读中再遇见它们。'}</Paragraph><div className="review-summary-stats"><div><b>{session.completed}</b><span>实际练习 / 词</span></div><div><b>{session.firstRemembered}</b><span>首次独立自评记得</span></div><div><b>{session.reinforced}</b><span>经巩固后记得</span></div><div><b>{session.weakCount}</b><span>仍需巩固 / 词</span></div></div><Space><Button type="primary" size="large" icon={<ReadOutlined />} onClick={() => selectScreen('workspace')}>回学习空间，查看成果</Button><Button size="large" onClick={() => { setView('home'); setTab('today') }}>查看下一轮安排</Button></Space><Text className="review-summary-footnote">{session.skipped ? `另有 ${session.skipped} 词跳过，未计入练习成果。` : '以上为回忆自评，不代表客观正确率或长期掌握。'}{session.nextDueAt ? ` 最近一次安排：${displayDate(session.nextDueAt, true)}` : ''}</Text></Card>
    {!!session.weakWords.length && <Card title="这一轮值得再看一眼的词" extra={<Text type="secondary">回原文，在语境中巩固</Text>}><WordRows items={session.weakWords.map(entry => entry.item)} showMeaning /></Card>}
    {loadError && <Alert type="warning" message={loadError} action={<Button onClick={() => load().catch(e => setLoadError(e.message))}>刷新统计</Button>} />}
  </div>

  return <div className="page-stack vocabulary-page">
    <div className="page-intro"><div><Text className="eyebrow">WORDS INTO KNOWLEDGE</Text><Title level={1}>让读过的词，真正留下来</Title><Paragraph>回到熟悉的语境，用一小轮复习，把生词变成自己的积累。</Paragraph></div><Button icon={<BookOutlined />} onClick={() => selectScreen('library')}>回到书架</Button></div>
    <div className="review-nav"><Segmented aria-label="生词页面" value={tab} onChange={setTab} options={[{ value: 'today', label: '今日复习' }, { value: 'notebook', label: `我的生词本 · ${stats.total}` }]} /><Text type="secondary">收藏于阅读，巩固于复习</Text></div>
    {scope === 'selected' && <Alert type={selected.length ? 'info' : 'warning'} showIcon message={selected.length ? '本轮将练习刚才阅读中新收藏的 ' + selected.length + ' 个词。' : '这批生词已不可访问，请切换复习范围。'} />}{loadError && <Alert type="warning" showIcon message={loadError} action={<Button onClick={() => load().catch(e => setLoadError(e.message))}>刷新</Button>} />}
    {tab === 'today' ? <>
      <div className="review-overview-grid">
        <Card className="review-today-hero"><div className="review-hero-label"><span><FlagOutlined /> 今天的一小步</span><Tag>{data.active ? '有一轮等待继续' : stats.due ? '复习计划已就绪' : stats.total ? '按自己的节奏来' : '从第一篇阅读开始'}</Tag></div>
          <Title level={2}>{data.active ? '接着上次的进度，再记牢一点' : stats.due ? '今天，让这些词再熟悉一点' : stats.total ? '当前没有到期词，积累还在继续' : '读到不熟悉的词，就把它留下'}</Title>
          <div className="review-due-count"><b>{data.active ? data.active.completed : stats.due}</b><span>{data.active ? `/ ${data.active.total} 词已练习` : '个词等待复习'}</span></div>
          <Paragraph>{data.active ? '每次评分都已保存，回来就能继续。' : stats.due ? `包含 ${stats.new} 个待学新词。先回忆，再看答案，薄弱词会在本轮再次出现。` : stats.total ? `${stats.total} 个生词已在你的词本中。${stats.nextDueAt ? `下一次复习：${displayDate(stats.nextDueAt, true)}。` : ''}也可以提前巩固一轮。` : '在阅读器里收藏生词并补充释义，这里会为你安排后续复习。'}</Paragraph>
          {stats.total > 0 && !data.active && <div className="review-plan-controls"><label>每轮词数 <Segmented aria-label="每轮词数" disabled={busy} value={size} onChange={setSize} options={[5, 10, 20].map(value => ({ value, label: `${value} 词` }))} /></label><Select aria-label="复习范围" value={scope} disabled={busy} onChange={setScope} options={[...(selectedIds.current.length ? [{ value: 'selected', label: `本次新词 · ${selected.length}` }] : []), { value: 'due', label: `到期优先 · ${due.length}` }, { value: 'difficult', label: `薄弱词 · ${difficult.length}` }, { value: 'all', label: `全部生词 · ${items.length}` }]} /></div>}
          <div className="review-hero-actions">{data.active ? <Button type="primary" size="large" icon={<ArrowRightOutlined />} onClick={() => { setSession(data.active); setView('practice'); setError('') }}>继续上次复习</Button> : !stats.total ? <Button type="primary" size="large" icon={<ReadOutlined />} onClick={() => selectScreen('catalog')}>去阅读，收藏第一个生词</Button> : <Button type="primary" size="large" loading={busy} disabled={!candidates.length && !(scope === 'due' && !due.length)} onClick={() => begin(scope === 'due' && !due.length ? 'all' : scope)} icon={<ArrowRightOutlined />}>{scope === 'due' && !due.length ? '提前巩固一轮' : `开始本轮复习 · ${Math.min(size, candidates.length)} 词`}</Button>}<Text>{data.active ? '刷新或离开页面，进度仍会保留' : '小步完成，不必一次清空词本'}</Text></div>
          {error && <Alert type="error" showIcon message={error} />}
          <div className="review-method-strip"><span><EyeOutlined /> 独立回忆</span><ArrowRightOutlined /><span><CheckCircleOutlined /> 对照释义</span><ArrowRightOutlined /><span><ReloadOutlined /> 薄弱词再练</span></div>
        </Card>
        <Card className="review-week-card"><div className="review-section-label"><ThunderboltOutlined /><Text strong>每一点积累，都算数</Text></div><div className="review-week-metric"><b>{stats.todayReviewed}<small> 词</small></b><span>今日已复习 · 按词条去重</span></div><div className="review-week-pair"><div><b>{stats.reviewDays}<small> / 7 天</small></b><span>近 7 天复习</span></div><div><b>{stats.total}<small> 词</small></b><span>生词积累</span></div></div><Paragraph>从这一版开始记录复习会话。旧版学习记录仍保留，不补算历史成绩。</Paragraph><Button type="text" onClick={() => selectScreen('stats')}>查看学习记录 <ArrowRightOutlined /></Button></Card>
      </div>
      <div className="review-detail-grid"><Card title={due.length ? '从这些词开始' : '你的下一次复习'} extra={<Button type="link" onClick={() => setTab('notebook')}>查看生词本 <ArrowRightOutlined /></Button>}>
        {preview.length ? <WordRows items={preview} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="你的第一批生词，将从阅读中来到这里。"><Button onClick={() => selectScreen('catalog')}>去书城找一篇读物</Button></Empty>}
      </Card><Card className="review-guide-card" title="让每轮复习更有效"><div className="review-guide-step"><span>01</span><div><b>先想一想，再揭晓</b><p>先回忆词义，想不起来也没关系；需要时再看原句提示。</p></div></div><div className="review-guide-step"><span>02</span><div><b>诚实自评，安排下一次</b><p>忘记的词稍后再练，记得的词逐步拉长间隔。</p></div></div><div className="review-guide-step"><span>03</span><div><b>回到原文，再遇见它</b><p>复习结束后继续阅读，让单词和真实语境重新连起来。</p></div></div><div className="review-guide-bottom"><ClockCircleOutlined /> 一小轮完成，也值得被记录。</div></Card></div>
      {data.latest && <Card className="review-last-session"><div><CheckCircleOutlined /><div><Text strong>上一次的积累已保存</Text><Paragraph>{displayDate(data.latest.updatedAt, true)} · 练习 {data.latest.completed} 词 · 仍需巩固 {data.latest.weakCount} 词</Paragraph></div></div><Button onClick={() => { setSession(data.latest); setView('summary') }}>查看本轮回顾</Button></Card>}
    </> : <Card className="review-notebook" title="我的生词本" extra={<Text type="secondary">保留每次阅读的语境</Text>}><div className="review-notebook-filters"><Input.Search aria-label="搜索生词" allowClear placeholder="搜索单词、释义或原句" value={query} onChange={event => setQuery(event.target.value)} /><Select aria-label="按来源筛选" value={source} onChange={setSource} options={[{ value: 'all', label: '全部来源' }, ...sources.map(item => ({ value: item.bookId, label: item.bookTitle }))]} /><Segmented aria-label="生词状态" value={filter} onChange={setFilter} options={[{ value: 'all', label: '全部' }, { value: 'due', label: '待复习' }, { value: 'difficult', label: '需巩固' }]} /></div>{filtered.length ? <><WordRows items={filtered.slice((page - 1) * 10, page * 10)} showMeaning /><Pagination className="review-pagination" current={page} pageSize={10} total={filtered.length} showSizeChanger={false} onChange={setPage} showTotal={total => `共 ${total} 个词条`} /></> : <Empty description="当前条件下没有生词"><Button onClick={() => { setQuery(''); setSource('all'); setFilter('all') }}>清除筛选</Button></Empty>}</Card>}
  </div>
}
