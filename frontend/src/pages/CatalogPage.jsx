import React, { useEffect, useMemo, useRef, useState } from 'react'
import { handleMembershipLimit } from '../api/membershipLimit'
import { Alert, Button, Card, Col, Empty, Input, Modal, Row, Select, Skeleton, Space, Tag, Typography } from 'antd'
import { BookOutlined, FileTextOutlined, ReadOutlined } from '@ant-design/icons'

import { getJson, postJson } from '../api/client'
import PageSkeleton from '../components/PageSkeleton'
import BookCover from '../components/BookCover'
import { bookDescription, resourceNames } from '../utils/presentation.mjs'

const { Paragraph, Text, Title } = Typography

export default function CatalogPage({ catalogBooks, openReader, selectScreen, onRefresh, messageApi }) {
  const [items, setItems] = useState(catalogBooks || [])
  const [query, setQuery] = useState('')
  const [level, setLevel] = useState('')
  const [series, setSeries] = useState('')
  const [tag, setTag] = useState('')
  const [resourceType, setResourceType] = useState('')
  const [seriesOptions, setSeriesOptions] = useState([])
  const [tagOptions, setTagOptions] = useState([])
  const [optionsLoading, setOptionsLoading] = useState(true)
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [revision, setRevision] = useState(0)
  const [optionsError, setOptionsError] = useState('')
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detail, setDetail] = useState(null)
  const [pendingBookId, setPendingBookId] = useState('')
  const actionPending = useRef(false)
  const catalogRequest = useRef(0)
  const firstCatalogLoad = useRef(true)
  const detailRequest = useRef(0)

  useEffect(() => {
    setItems(current => current.map(book => {
      const latest = (catalogBooks || []).find(item => item.id === book.id)
      return latest ? { ...book, inLibrary: latest.inLibrary } : book
    }))
  }, [catalogBooks])

  useEffect(() => {
    let active = true
    setOptionsError('')
    Promise.all([getJson('/api/catalog/series'), getJson('/api/catalog/tags')]).then(([seriesData, tagsData]) => {
      if (!active) return
      setSeriesOptions(seriesData.series || [])
      setTagOptions(tagsData.tags || [])
    }).catch(error => { if (active) setOptionsError(error.message || '筛选选项加载失败') }).finally(() => { if (active) setOptionsLoading(false) })
    return () => { active = false }
  }, [revision])

  useEffect(() => {
    if (firstCatalogLoad.current && !query.trim() && !level && !series && !tag && !resourceType) {
      firstCatalogLoad.current = false
      setItems(catalogBooks || [])
      return undefined
    }
    firstCatalogLoad.current = false
    const requestId = ++catalogRequest.current
    const timer = setTimeout(async () => {
      setLoading(true)
      setLoadError('')
      const params = new URLSearchParams({ limit: '60' })
      if (query.trim()) params.set('q', query.trim())
      if (level) params.set('level', level)
      if (series) params.set('series', series)
      if (tag) params.set('tag', tag)
      if (resourceType) params.set('resourceType', resourceType)
      try {
        const data = await getJson(`/api/catalog?${params.toString()}`)
        if (requestId === catalogRequest.current) setItems(data.books || [])
      } catch (error) {
        if (requestId === catalogRequest.current) setLoadError(error.message || '书城加载失败')
      } finally {
        if (requestId === catalogRequest.current) setLoading(false)
      }
    }, 220)
    return () => { clearTimeout(timer); catalogRequest.current += 1 }
  }, [level, query, resourceType, series, tag, revision])

  const levels = useMemo(() => [...new Set([...(catalogBooks || []), ...items].map(item => item.level).filter(Boolean))].sort(), [catalogBooks, items])
  const resources = ['book', 'audio', 'video', 'youtube']

  const openDetail = async book => {
    const requestId = ++detailRequest.current
    setDetailOpen(true)
    setDetailLoading(true)
    setDetail(null)
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
      setItems(current => current.map(item => item.id === book.id ? { ...item, inLibrary: true } : item))
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

  if (optionsLoading) return <PageSkeleton />
  return <div className="page-stack">
    <div className="page-intro"><div><Text className="eyebrow">CURATED LIBRARY</Text><Title level={1}>发现下一篇想读懂的内容</Title><Paragraph>按兴趣挑选官方读物，先试读，再加入自己的书架。</Paragraph></div><Button icon={<BookOutlined />} onClick={() => selectScreen('library')}>我的书架</Button></div>
    {optionsError && <Alert showIcon type="warning" message="部分筛选暂时不可用" description={optionsError} action={<Button onClick={() => setRevision(value => value + 1)}>重试</Button>} />}
    <Card className="filter-card catalog-filter-card">
      <Space wrap>
        <Input aria-label="搜索读物" allowClear prefix={<FileTextOutlined />} placeholder="搜索标题、作者或主题" value={query} onChange={event => setQuery(event.target.value)} style={{ width: 280 }} />
        <Select aria-label="难度" allowClear placeholder="难度" value={level || undefined} onChange={value => setLevel(value || '')} options={levels.map(value => ({ value, label: value }))} />
        <Select allowClear showSearch optionFilterProp="label" placeholder="系列" value={series || undefined} onChange={value => setSeries(value || '')} options={seriesOptions.map(item => ({ value: item.slug || item.id, label: `${item.title}（${item.bookCount}）` }))} />
        <Select allowClear showSearch optionFilterProp="label" placeholder="主题标签" value={tag || undefined} onChange={value => setTag(value || '')} options={tagOptions.map(item => ({ value: item.slug || item.id, label: `${item.title}（${item.bookCount}）` }))} />
        <Select aria-label="资源类型" allowClear placeholder="资源类型" value={resourceType || undefined} onChange={value => setResourceType(value || '')} options={resources.map(value => ({ value, label: resourceNames[value] || value }))} />
        <Button onClick={() => { setQuery(''); setLevel(''); setSeries(''); setTag(''); setResourceType('') }}>重置</Button>
      </Space>
    </Card>
    {loading ? <Row gutter={[20, 20]}>{[0, 1, 2].map(item => <Col xs={24} sm={12} xl={8} key={item}><Card><Skeleton active title paragraph={{ rows: 5 }} /></Card></Col>)}</Row> : loadError ? <Alert showIcon type="error" message="书城暂时无法加载" description={loadError} action={<Button onClick={() => setRevision(value => value + 1)}>重试</Button>} /> : <Row gutter={[20, 20]}>{items.length ? items.map(book => <Col xs={24} sm={12} xl={8} key={book.id}><Card className="book-card catalog-book-card"><BookCover book={book} catalog /><Space wrap>{book.level && <Tag>{book.level}</Tag>}<Tag>{resourceNames[book.resourceType] || '读物'}</Tag>{book.inLibrary && <Tag color="success">已在书架</Tag>}</Space><Title level={4} ellipsis={{ rows: 2 }}>{book.title}</Title>{book.author && <Text type="secondary">{book.author}</Text>}<Paragraph ellipsis={{ rows: 2 }}>{bookDescription(book)}</Paragraph><Space><Text type="secondary">{book.estimatedMinutes > 0 ? `约 ${book.estimatedMinutes} 分钟` : '按自己的节奏阅读'}</Text>{book.sentenceCount > 0 && <Text type="secondary">{book.sentenceCount} 句</Text>}</Space><Button block type="primary" onClick={() => book.inLibrary ? openReader({ ...book, source: '官方读物' }) : openDetail(book)} style={{ marginTop: 14 }}>{book.inLibrary ? '开始阅读' : '查看与试读'}</Button><div className="catalog-secondary-action">{book.inLibrary && <Button type="link" onClick={() => openDetail(book)}>查看内容介绍</Button>}</div></Card></Col>) : <Col span={24}><Empty description="暂时没有符合条件的读物"><Button onClick={() => { setQuery(''); setLevel(''); setSeries(''); setTag(''); setResourceType('') }}>清除筛选</Button></Empty></Col>}</Row>}
    <Modal width={760} title="读物详情" open={detailOpen} onCancel={() => { detailRequest.current += 1; setDetailOpen(false) }} footer={null}>
      {detailLoading ? <div className="modal-loading"><Card style={{ width: '100%' }}><Skeleton active title paragraph={{ rows: 9 }} /></Card></div> : detail?.error ? <Alert showIcon type="error" message="内容介绍暂时无法加载" description={detail.error} action={<Button onClick={() => openDetail(detail)}>重试</Button>} /> : detail && <div className="catalog-detail"><div className="catalog-detail-heading"><BookCover book={detail} catalog large /><div><Space wrap>{detail.level && <Tag>{detail.level}</Tag>}<Tag>{resourceNames[detail.resourceType] || '读物'}</Tag>{detail.series?.title && <Tag>{detail.series.title}</Tag>}</Space><Title level={2}>{detail.title}</Title>{(detail.author || (detail.englishTitle && detail.englishTitle !== detail.title)) && <Paragraph>{[detail.englishTitle !== detail.title ? detail.englishTitle : '', detail.author].filter(Boolean).join(' · ')}</Paragraph>}<Space wrap>{(detail.tags || []).map(item => <Tag key={item.id || item.slug}>{item.title}</Tag>)}</Space><Paragraph type="secondary">收藏 {detail.favoriteCount || 0} · 阅读 {detail.readingCount || 0}</Paragraph></div></div><Paragraph>{bookDescription(detail)}</Paragraph>{detail.preview?.length > 0 && <Card size="small" title="有限预览" className="catalog-preview">{detail.preview.map((item, index) => <Paragraph key={item.id || index}>{item.text}</Paragraph>)}</Card>}<Card size="small" title="版权与阅读说明"><Paragraph>{detail.rightsNotice || detail.readerNotice || '加入书架后即可阅读；官方和私人音视频合计收藏数量受当前套餐限制，移出书架可释放名额。'}</Paragraph></Card><Space className="catalog-detail-actions">{detail.inLibrary ? <Button type="primary" onClick={() => openReader({ ...detail, source: '官方读物' })}>开始阅读</Button> : <><Button icon={<ReadOutlined />} onClick={() => openReader({ ...detail, source: '官方读物', trial: true })}>开始试读</Button><Button loading={pendingBookId === detail.id} disabled={Boolean(pendingBookId) && pendingBookId !== detail.id} type="primary" onClick={() => performAction(detail, true)}>加入书架</Button></>}</Space></div>}
    </Modal>
  </div>
}
