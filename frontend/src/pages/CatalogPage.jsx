import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Button, Card, Col, Empty, Input, Modal, Row, Segmented, Select, Skeleton, Space, Tag, Typography } from 'antd'
import { BookOutlined, FileTextOutlined } from '@ant-design/icons'

import { getJson, postJson } from '../api/client'
import PageSkeleton from '../components/PageSkeleton'

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
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detail, setDetail] = useState(null)
  const [pendingBookId, setPendingBookId] = useState('')
  const actionPending = useRef(false)
  const catalogRequest = useRef(0)
  const firstCatalogLoad = useRef(true)

  useEffect(() => {
    setItems(current => current.map(book => {
      const latest = (catalogBooks || []).find(item => item.id === book.id)
      return latest ? { ...book, inLibrary: latest.inLibrary } : book
    }))
  }, [catalogBooks])

  useEffect(() => {
    Promise.all([getJson('/api/catalog/series', { series: [] }), getJson('/api/catalog/tags', { tags: [] })]).then(([seriesData, tagsData]) => {
      setSeriesOptions(seriesData.series || [])
      setTagOptions(tagsData.tags || [])
    }).finally(() => setOptionsLoading(false))
  }, [])

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
        if (requestId === catalogRequest.current) messageApi.error(error.message || '书城加载失败')
      } finally {
        if (requestId === catalogRequest.current) setLoading(false)
      }
    }, 220)
    return () => { clearTimeout(timer); catalogRequest.current += 1 }
  }, [level, query, resourceType, series, tag])

  const levels = useMemo(() => [...new Set((items || []).map(item => item.level).filter(Boolean))].sort(), [items])
  const resources = useMemo(() => [...new Set((items || []).map(item => item.resourceType).filter(Boolean))].sort(), [items])

  const openDetail = async book => {
    setDetailOpen(true)
    setDetailLoading(true)
    setDetail(null)
    try {
      const data = await getJson(`/api/catalog/books/${encodeURIComponent(book.id)}`)
      setDetail(data.book)
    } catch (error) { setDetail({ error: error.message }) }
    finally { setDetailLoading(false) }
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
      messageApi.error(error.message || '书架操作失败')
    } finally {
      actionPending.current = false
      setPendingBookId('')
    }
  }

  if (optionsLoading) return <PageSkeleton />
  return <div className="page-stack">
    <div className="page-intro"><div><Text className="eyebrow">CURATED LIBRARY</Text><Title level={1}>首页 · 书城</Title><Paragraph>按系列、难度、主题和资源类型挑选官方读物，先预览再加入书架。</Paragraph></div><Button icon={<BookOutlined />} onClick={() => selectScreen('library')}>我的书架</Button></div>
    <Card className="filter-card catalog-filter-card">
      <Space wrap>
        <Input allowClear prefix={<FileTextOutlined />} placeholder="搜索标题、作者或主题" value={query} onChange={event => setQuery(event.target.value)} style={{ width: 280 }} />
        <Select allowClear placeholder="难度" value={level || undefined} onChange={value => setLevel(value || '')} options={levels.map(value => ({ value, label: value }))} />
        <Select allowClear showSearch optionFilterProp="label" placeholder="系列" value={series || undefined} onChange={value => setSeries(value || '')} options={seriesOptions.map(item => ({ value: item.slug || item.id, label: `${item.title}（${item.bookCount}）` }))} />
        <Select allowClear showSearch optionFilterProp="label" placeholder="主题标签" value={tag || undefined} onChange={value => setTag(value || '')} options={tagOptions.map(item => ({ value: item.slug || item.id, label: `${item.title}（${item.bookCount}）` }))} />
        <Select allowClear placeholder="资源类型" value={resourceType || undefined} onChange={value => setResourceType(value || '')} options={resources.map(value => ({ value, label: value }))} />
        <Button onClick={() => { setQuery(''); setLevel(''); setSeries(''); setTag(''); setResourceType('') }}>重置</Button>
      </Space>
    </Card>
    {loading ? <Row gutter={[20, 20]}>{[0, 1, 2, 3, 4, 5].map(item => <Col xs={24} sm={12} xl={8} key={item}><Card><Skeleton active title paragraph={{ rows: 5 }} /></Card></Col>)}</Row> : <Row gutter={[20, 20]}>{items.length ? items.map(book => <Col xs={24} sm={12} xl={8} key={book.id}><Card hoverable className="book-card catalog-book-card" onClick={() => openDetail(book)}><div className="catalog-cover-placeholder"><span>{String(book.title || '书').slice(0, 2).toUpperCase()}</span></div><Space wrap><Tag>{book.level || '未分级'}</Tag><Tag color="gold">{book.resourceType || 'book'}</Tag>{book.inLibrary && <Tag color="success">已加入书架</Tag>}</Space><Title level={4} ellipsis={{ rows: 1 }}>{book.title}</Title><Text type="secondary" ellipsis>{book.englishTitle || book.author || book.description}</Text><Paragraph ellipsis={{ rows: 2 }}>{book.description || '查看详情、有限预览和版权信息。'}</Paragraph><Space><Text type="secondary">{book.estimatedMinutes || 0} 分钟</Text><Text type="secondary">{book.sentenceCount || 0} 句</Text></Space><Button loading={pendingBookId === book.id} disabled={Boolean(pendingBookId) && pendingBookId !== book.id} block type={book.inLibrary ? 'default' : 'primary'} onClick={event => { event.stopPropagation(); book.inLibrary ? openReader({ ...book, source: '官方读物' }) : performAction(book, true) }} style={{ marginTop: 14 }}>{book.inLibrary ? '开始阅读' : '加入书架'}</Button></Card></Col>) : <Col span={24}><Empty description="没有符合筛选条件的官方读物" /></Col>}</Row>}
    <Modal width={760} title="读物详情" open={detailOpen} onCancel={() => setDetailOpen(false)} footer={null}>
      {detailLoading ? <div className="modal-loading"><Card style={{ width: '100%' }}><Skeleton active title paragraph={{ rows: 9 }} /></Card></div> : detail?.error ? <Empty description={detail.error} /> : detail && <div className="catalog-detail"><div className="catalog-detail-heading"><div className="catalog-cover-placeholder large"><span>{String(detail.title || '书').slice(0, 2).toUpperCase()}</span></div><div><Space wrap><Tag>{detail.level || '未分级'}</Tag><Tag color="gold">{detail.resourceType || 'book'}</Tag>{detail.series?.title && <Tag>{detail.series.title}</Tag>}</Space><Title level={2}>{detail.title}</Title><Paragraph>{detail.englishTitle}{detail.author ? ` · ${detail.author}` : ''}</Paragraph><Space wrap>{(detail.tags || []).map(item => <Tag key={item.id || item.slug}>{item.title}</Tag>)}</Space></div></div><Paragraph>{detail.description || '暂无简介。'}</Paragraph>{detail.preview?.length > 0 && <Card size="small" title="有限预览" className="catalog-preview">{detail.preview.map((item, index) => <Paragraph key={item.id || index}>{item.text}</Paragraph>)}</Card>}<Card size="small" title="版权与阅读说明"><Paragraph>{detail.rightsNotice || detail.readerNotice || '加入书架后即可阅读；官方和私人音视频合计收藏数量受当前套餐限制，移出书架可释放名额。'}</Paragraph></Card><Space className="catalog-detail-actions">{detail.inLibrary ? <Button type="primary" onClick={() => openReader({ ...detail, source: '官方读物' })}>开始阅读</Button> : <Button loading={pendingBookId === detail.id} disabled={Boolean(pendingBookId) && pendingBookId !== detail.id} type="primary" onClick={() => performAction(detail, true)}>{'加入书架'}</Button>}</Space></div>}
    </Modal>
  </div>
}
