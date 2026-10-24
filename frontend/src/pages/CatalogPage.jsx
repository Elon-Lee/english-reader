import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { handleMembershipLimit } from '../api/membershipLimit'
import { Alert, Button, Card, Empty, Input, Modal, Pagination, Segmented, Skeleton, Space, Tag, Tooltip, Typography } from 'antd'
import { AppstoreOutlined, BarsOutlined, BookOutlined, CloseOutlined, FilterOutlined, SearchOutlined } from '@ant-design/icons'

import { getJson, postJson } from '../api/client'
import PageSkeleton from '../components/PageSkeleton'
import BookCover from '../components/BookCover'
import { bookDescription, resourceNames } from '../utils/presentation.mjs'
import { bookLevels } from '../utils/levels.mjs'

const { Paragraph, Text, Title } = Typography
const PAGE_SIZE = 12
const LEVEL_ORDER = [...bookLevels.map(level => level.value), '__ungraded__']
const LEVEL_LABELS = Object.fromEntries(bookLevels.map(level => [level.value, level.label]))
const UNITS = ['book', 'audio', 'video', 'youtube']

const emptyFilters = { q: '', level: [], duration: [], series: [], tag: [], resourceType: [], hideInLibrary: false }
const readState = params => ({
  q: params.get('q') || '',
  level: params.getAll('level').flatMap(value => value.split(',')).filter(Boolean),
  duration: params.getAll('duration').flatMap(value => value.split(',')).filter(Boolean),
  series: params.getAll('series').flatMap(value => value.split(',')).filter(Boolean),
  tag: params.getAll('tag').flatMap(value => value.split(',')).filter(Boolean),
  resourceType: params.getAll('resourceType').flatMap(value => value.split(',')).filter(Boolean),
  hideInLibrary: params.get('hideInLibrary') === '1',
})

export default function CatalogPage({ catalogBooks, openReader, selectScreen, onRefresh, messageApi }) {
  const [filters, setFilters] = useState(() => readState(new URLSearchParams(location.search)))
  const [sort, setSort] = useState(() => new URLSearchParams(location.search).get('sort') || 'featured')
  const [view, setView] = useState(() => localStorage.getItem('shiyue-catalog-view') || 'grid')
  const [page, setPage] = useState(() => Math.max(1, Number(new URLSearchParams(location.search).get('page')) || 1))
  const [result, setResult] = useState({ books: catalogBooks || [], total: catalogBooks?.length || 0, facets: null })
  const [loading, setLoading] = useState(!catalogBooks?.length)
  const [refreshing, setRefreshing] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [revision, setRevision] = useState(0)
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detail, setDetail] = useState(null)
  const [pendingBookId, setPendingBookId] = useState('')
  const actionPending = useRef(false)
  const catalogRequest = useRef(0)
  const detailRequest = useRef(0)
  const firstLoad = useRef(true)
  const [draftQuery, setDraftQuery] = useState(filters.q)

  const activeCount = filters.level.length + filters.duration.length + filters.series.length + filters.tag.length + filters.resourceType.length + (filters.hideInLibrary ? 1 : 0)

  const persistUrl = useCallback((next, nextSort, nextPage) => {
    const params = new URLSearchParams(location.search)
    ;['q', 'level', 'duration', 'series', 'tag', 'resourceType', 'hideInLibrary', 'page'].forEach(key => params.delete(key))
    if (next.q.trim()) params.set('q', next.q.trim())
    ;['level', 'duration', 'series', 'tag', 'resourceType'].forEach(key => next[key].forEach(value => params.append(key, value)))
    if (next.hideInLibrary) params.set('hideInLibrary', '1')
    if (nextSort !== 'featured') params.set('sort', nextSort)
    if (nextPage > 1) params.set('page', String(nextPage))
    history.replaceState(null, '', `${location.pathname}?${params.toString()}`)
  }, [])

  useEffect(() => {
    // Prefetched books render immediately, but the first page is still fetched for
    // facet counts — without them the level/duration/topic rows cannot render at all.
    if (firstLoad.current) {
      firstLoad.current = false
      if (catalogBooks?.length) setLoading(false)
    }
    const requestId = ++catalogRequest.current
    const timer = setTimeout(async () => {
      // Keep the current grid visible while refetching; only the first load shows skeletons.
      setLoading(current => current || !result.books.length)
      setRefreshing(true); setLoadError('')
      const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String((page - 1) * PAGE_SIZE), sort })
      if (filters.q.trim()) params.set('q', filters.q.trim())
      ;['level', 'duration', 'series', 'tag', 'resourceType'].forEach(key => filters[key].forEach(value => params.append(key, value)))
      if (filters.hideInLibrary) params.set('hideInLibrary', '1')
      try {
        const data = await getJson(`/api/catalog?${params.toString()}`)
        if (requestId !== catalogRequest.current) return
        setResult({ books: data.books || [], total: data.total || 0, facets: data.facets || null })
      } catch (error) {
        if (requestId === catalogRequest.current) setLoadError(error.message || '书城加载失败')
      } finally {
        if (requestId === catalogRequest.current) { setLoading(false); setRefreshing(false) }
      }
    }, filters.q ? 300 : 0)
    return () => { clearTimeout(timer); catalogRequest.current += 1 }
  }, [filters, sort, page, revision, catalogBooks])

  useEffect(() => { persistUrl(filters, sort, page) }, [filters, sort, page, persistUrl])
  useEffect(() => { setDraftQuery(filters.q) }, [filters.q])
  useEffect(() => { localStorage.setItem('shiyue-catalog-view', view) }, [view])

  const update = patch => { setPage(1); setFilters(current => ({ ...current, ...patch })) }
  const toggle = (key, value) => update({ [key]: filters[key].includes(value) ? filters[key].filter(item => item !== value) : [...filters[key], value] })
  const resetAll = () => { setPage(1); setFilters({ ...emptyFilters }); setSort('featured') }

  const levelOptions = useMemo(() => {
    const rows = result.facets?.levels || []
    return [...rows]
      .map(row => ({ ...row, label: row.value === '__ungraded__' ? '未分级' : LEVEL_LABELS[row.value] || row.value }))
      .sort((a, b) => LEVEL_ORDER.indexOf(a.value) - LEVEL_ORDER.indexOf(b.value))
  }, [result.facets])
  const durationOptions = result.facets?.durations || []
  const seriesOptions = result.facets?.series || []
  const tagOptions = result.facets?.tags || []
  const typeOptions = result.facets?.resourceTypes || []

  const openDetail = async book => {
    const requestId = ++detailRequest.current
    setDetailOpen(true); setDetailLoading(true); setDetail(null)
    try {
      const data = await getJson(`/api/catalog/books/${encodeURIComponent(book.id)}`)
      if (requestId === detailRequest.current) setDetail(data.book)
    } catch (error) { if (requestId === detailRequest.current) setDetail({ ...book, error: error.message }) }
    finally { if (requestId === detailRequest.current) setDetailLoading(false) }
  }

  const performAction = async (book, readAfter = false) => {
    if (actionPending.current) return
    actionPending.current = true
    setPendingBookId(book.id)
    try {
      if (!book.inLibrary) await postJson('/api/library/items', { bookId: book.id, shelfState: 'active' })
      catalogRequest.current += 1
      setLoading(false)
      setResult(current => ({ ...current, books: current.books.map(item => item.id === book.id ? { ...item, inLibrary: true } : item) }))
      setDetail(current => current?.id === book.id ? { ...current, inLibrary: true } : current)
      await onRefresh?.()
      messageApi.success('已加入我的书架')
      if (readAfter) openReader({ ...book, source: '官方读物', inLibrary: true })
      else {
        const data = await getJson(`/api/catalog/books/${encodeURIComponent(book.id)}`, null)
        if (data?.book) setDetail(data.book)
      }
    } catch (error) {
      if (!handleMembershipLimit(error, { onClose: () => setDetailOpen(false), onContinue: () => performAction(book, readAfter) })) messageApi.error(error.message || '书架操作失败')
    } finally {
      actionPending.current = false
      setPendingBookId('')
    }
  }

  const retry = () => setRevision(value => value + 1)
  const onboarding = new URLSearchParams(location.search).get('onboarding') === '1'
  if (loading && !result.books.length && !result.facets && !loadError) return <PageSkeleton />

  const chips = [
    ...filters.level.map(value => ({ key: `level:${value}`, label: value === '__ungraded__' ? '未分级' : LEVEL_LABELS[value] || value, clear: () => toggle('level', value) })),
    ...filters.duration.map(value => ({ key: `duration:${value}`, label: durationOptions.find(item => item.value === value)?.label || value, clear: () => toggle('duration', value) })),
    ...filters.series.map(value => ({ key: `series:${value}`, label: seriesOptions.find(item => item.value === value)?.title || value, clear: () => toggle('series', value) })),
    ...filters.tag.map(value => ({ key: `tag:${value}`, label: tagOptions.find(item => item.value === value)?.title || value, clear: () => toggle('tag', value) })),
    ...filters.resourceType.map(value => ({ key: `type:${value}`, label: resourceNames[value] || value, clear: () => toggle('resourceType', value) })),
    ...(filters.hideInLibrary ? [{ key: 'hide', label: '隐藏已在书架', clear: () => update({ hideInLibrary: false }) }] : []),
  ]
  const moreCount = filters.series.length + filters.tag.length + filters.resourceType.length + (filters.hideInLibrary ? 1 : 0)

  return <div className="page-stack catalog-page">
    {onboarding && <Alert type="info" showIcon message="先挑一篇能理解大意的短内容" description="按难度和时长挑一篇适合现在的内容。先试读前 10%，合适再加入书架。" closable />}

    <div className="catalog-head">
      <div><Title level={1}>书城</Title><Paragraph>挑一篇今天读得完的内容。按难度、时长和主题缩小范围，先试读再决定。</Paragraph></div>
      <Button icon={<BookOutlined />} onClick={() => selectScreen('library')}>我的书架</Button>
    </div>

    <div className="catalog-search">
      <Input size="large" allowClear value={draftQuery} prefix={<SearchOutlined />} placeholder="搜索标题、频道、主题或简介" aria-label="搜索读物"
        onChange={event => setDraftQuery(event.target.value)}
        onPressEnter={() => update({ q: draftQuery })}
        onBlur={() => { if (draftQuery !== filters.q) update({ q: draftQuery }) }} />
      <Button size="large" type="primary" onClick={() => update({ q: draftQuery })}>搜索</Button>
    </div>

    <div className="catalog-facets">
      <FilterRow label="难度" options={levelOptions} selected={filters.level} onToggle={value => toggle('level', value)} />
      <FilterRow label="时长" options={durationOptions} selected={filters.duration} onToggle={value => toggle('duration', value)} />
      <FilterRow label="系列" options={seriesOptions} selected={filters.series} onToggle={value => toggle('series', value)} />
      <FilterRow label="主题" options={tagOptions} selected={filters.tag} onToggle={value => toggle('tag', value)} />
      {typeOptions.length > 1 && <FilterRow label="形式" options={typeOptions.map(item => ({ ...item, label: resourceNames[item.value] || item.value }))} selected={filters.resourceType} onToggle={value => toggle('resourceType', value)} />}
      <div className="catalog-filter-row catalog-filter-extra">
        <span className="catalog-filter-name"><FilterOutlined /> 其他</span>
        <div className="catalog-filter-values">
          <button type="button" aria-pressed={filters.hideInLibrary} className={`catalog-chip${filters.hideInLibrary ? ' is-selected' : ''}`} onClick={() => update({ hideInLibrary: !filters.hideInLibrary })}>隐藏已在书架</button>
          {moreCount > 0 && <button type="button" className="catalog-chip is-ghost" onClick={() => update({ series: [], tag: [], resourceType: [], hideInLibrary: false })}>清除其他条件（{moreCount}）</button>}
        </div>
      </div>
    </div>

    <div className="catalog-result-bar">
      <div className="catalog-result-count">
        <Text strong>{result.total}</Text><Text type="secondary">{filters.q ? ` 个结果匹配“${filters.q}”` : ' 篇读物'}</Text>
        {refreshing && <Text type="secondary" className="catalog-refreshing">更新中…</Text>}
        {chips.length > 0 && <span className="catalog-active-chips">{chips.map(chip => <button key={chip.key} type="button" className="catalog-active-chip" onClick={chip.clear}>{chip.label}<CloseOutlined /></button>)}<button type="button" className="catalog-clear-all" onClick={resetAll}>清除全部</button></span>}
      </div>
      <Space size={10}>
        <Segmented size="small" value={sort} onChange={value => { setPage(1); setSort(value) }} options={[{ value: 'featured', label: '精选' }, { value: 'newest', label: '最新' }, { value: 'duration', label: '时长短→长' }]} />
        <Segmented size="small" value={view} onChange={setView} aria-label="结果布局" options={[{ value: 'grid', icon: <AppstoreOutlined /> }, { value: 'list', icon: <BarsOutlined /> }]} />
      </Space>
    </div>

    {loadError ? <Alert showIcon type="error" message="书城暂时无法加载" description={loadError} action={<Button onClick={retry}>重试</Button>} />
      : loading ? <div className={`catalog-results is-loading ${view}`}>{Array.from({ length: 6 }).map((_, index) => <Card key={index} className="catalog-tile"><Skeleton active title paragraph={{ rows: 4 }} /></Card>)}</div>
      : result.books.length === 0 ? <Card className="catalog-empty"><Empty description={chips.length ? '没有同时满足这些条件的读物' : '书城暂时还没有已发布的读物'}>
        {chips.length > 0 && <div className="catalog-empty-hints">
          <Text type="secondary">去掉一个条件通常就能找到内容：</Text>
          {[['level', levelOptions, '难度'], ['duration', durationOptions, '时长'], ['tag', tagOptions, '主题'], ['series', seriesOptions, '系列']]
            .filter(([key]) => filters[key].length)
            .map(([key, , name]) => <Button key={key} size="small" onClick={() => update({ [key]: [] })}>清除{name}条件</Button>)}
          <Button size="small" type="primary" onClick={resetAll}>重新开始</Button>
        </div>}
      </Empty></Card>
      : <div className={`catalog-results ${view}`}>
        {result.books.map(book => <BookTile key={book.id} book={book} view={view} pending={pendingBookId === book.id} onDetail={openDetail} onRead={book => book.inLibrary ? openReader({ ...book, source: '官方读物' }) : openReader({ ...book, source: '官方读物', trial: true })} onAdd={book => performAction(book, false)} />)}
      </div>}

    {result.total > PAGE_SIZE && <Pagination className="catalog-pagination" current={page} pageSize={PAGE_SIZE} total={result.total} showSizeChanger={false} onChange={value => { setPage(value); window.scrollTo({ top: 0 }) }} />}

    <Modal width={760} title="读物详情" open={detailOpen} onCancel={() => { detailRequest.current += 1; setDetailOpen(false) }} footer={null}>
      {detailLoading ? <div className="modal-loading"><Card style={{ width: '100%' }}><Skeleton active title paragraph={{ rows: 9 }} /></Card></div> : detail?.error ? <Alert showIcon type="error" message="内容介绍暂时无法加载" description={detail.error} action={<Button onClick={() => openDetail(detail)}>重试</Button>} /> : detail && <div className="catalog-detail"><div className="catalog-detail-heading"><BookCover book={detail} catalog large /><div><Space wrap>{detail.level && <Tag>{LEVEL_LABELS[detail.level] || detail.level}</Tag>}<Tag>{resourceNames[detail.resourceType] || '读物'}</Tag>{detail.series?.title && <Tag>{detail.series.title}</Tag>}</Space><Title level={2}>{detail.title}</Title>{(detail.author || (detail.englishTitle && detail.englishTitle !== detail.title)) && <Paragraph>{[detail.englishTitle !== detail.title ? detail.englishTitle : '', detail.author].filter(Boolean).join(' · ')}</Paragraph>}<Space wrap>{(detail.tags || []).map(item => <Tag key={item.id || item.slug}>{item.title}</Tag>)}</Space><Paragraph type="secondary">收藏 {detail.favoriteCount || 0} · 阅读 {detail.readingCount || 0}</Paragraph></div></div><Paragraph>{bookDescription(detail)}</Paragraph>{detail.preview?.length > 0 && <Card size="small" title="有限预览" className="catalog-preview">{detail.preview.map((item, index) => <Paragraph key={item.id || index}>{item.text}</Paragraph>)}</Card>}<Card size="small" title="版权与阅读说明"><Paragraph>{detail.rightsNotice || detail.readerNotice || '加入书架后即可阅读；官方和私人音视频合计收藏数量受当前套餐限制，移出书架可释放名额。'}</Paragraph></Card><Space className="catalog-detail-actions">{detail.inLibrary ? <Button type="primary" onClick={() => openReader({ ...detail, source: '官方读物' })}>开始阅读</Button> : <><Button onClick={() => openReader({ ...detail, source: '官方读物', trial: true })}>开始试读</Button><Button loading={pendingBookId === detail.id} disabled={Boolean(pendingBookId) && pendingBookId !== detail.id} type="primary" onClick={() => performAction(detail, true)}>加入书架</Button></>}</Space></div>}
    </Modal>
  </div>
}

function FilterRow({ label, options, selected, onToggle }) {
  if (!options.length) return null
  return <div className="catalog-filter-row">
    <span className="catalog-filter-name">{label}</span>
    <div className="catalog-filter-values">
      {options.map(option => <button key={option.value} type="button" aria-pressed={selected.includes(option.value)}
        className={`catalog-chip${selected.includes(option.value) ? ' is-selected' : ''}`}
        onClick={() => onToggle(option.value)}
        disabled={!option.count && !selected.includes(option.value)}>
        <span>{option.label || option.title}</span><b>{option.count}</b>
      </button>)}
    </div>
  </div>
}

function BookTile({ book, view, pending, onDetail, onRead, onAdd }) {
  const level = book.level ? LEVEL_LABELS[book.level] || book.level : '未分级'
  const metrics = [book.estimatedMinutes > 0 ? `${book.estimatedMinutes} 分钟` : '时长未知', book.sentenceCount > 0 ? `${book.sentenceCount} 句` : '', book.wordCount > 0 ? `${book.wordCount.toLocaleString('zh-CN')} 词` : '', level].filter(Boolean)
  const description = String(book.description || '').trim() || bookDescription(book)
  const meta = <div className="catalog-tile-meta">
    {book.series?.title && <Text className="catalog-tile-source">{book.series.title}</Text>}
    <Title level={4} className="catalog-tile-title" title={book.title}>{book.title}</Title>
    <div className="catalog-tile-metrics">{metrics.map(item => <span key={item}>{item}</span>)}</div>
  </div>
  const actions = <div className="catalog-tile-actions">
    <Button type="primary" loading={pending} onClick={() => onRead(book)}>{book.inLibrary ? '继续阅读' : '试读'}</Button>
    <Button type="text" onClick={() => onDetail(book)}>{book.inLibrary ? '内容介绍' : '详情'}</Button>
    {!book.inLibrary && <Tooltip title="加入我的书架"><Button type="text" aria-label={`将《${book.title}》加入书架`} loading={pending} onClick={() => onAdd(book)}>加入书架</Button></Tooltip>}
  </div>
  if (view === 'list') return <article className="catalog-row">
    <BookCover book={book} catalog />
    <div className="catalog-row-body">{meta}<Paragraph className="catalog-row-copy" ellipsis={{ rows: 2 }}>{description}</Paragraph>{actions}</div>
  </article>
  return <article className="catalog-tile">
    <BookCover book={book} catalog />
    <div className="catalog-tile-body">{meta}<Paragraph className="catalog-tile-copy" ellipsis={{ rows: 2 }}>{description}</Paragraph>{actions}</div>
  </article>
}
