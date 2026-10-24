import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Dropdown, Empty, Input, Modal, Pagination, Progress, Select, Space, Tag, Typography } from 'antd'
import { AppstoreOutlined, BarsOutlined, CloseOutlined, DeleteOutlined, FileTextOutlined, InboxOutlined, MoreOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons'
import { deleteJson, getJson, postJson } from '../api/client'
import BookCover from '../components/BookCover'
import { deriveReadingState, formatLastUpdated, READING_STATES } from '../utils/libraryState.mjs'
import { bookDescription, resourceNames } from '../utils/presentation.mjs'

const { Paragraph, Text, Title } = Typography
const PAGE_SIZE = 18

export default function LibraryPage({ libraryBooks, importTasks, openReader, openImport, onCancelImport, onRetryImport, onRefresh, messageApi, currentUser, selectScreen }) {
  const allBooks = libraryBooks || []
  const activeTasks = (importTasks || []).filter(task => !['complete', 'cancelled'].includes(task.status))

  const [query, setQuery] = useState(() => new URLSearchParams(location.search).get('q') || '')
  const [draftQuery, setDraftQuery] = useState(query)
  const [state, setState] = useState(() => new URLSearchParams(location.search).get('state') || 'all')
  const [sort, setSort] = useState(() => new URLSearchParams(location.search).get('sort') || 'recent')
  const [view, setView] = useState(() => localStorage.getItem('library-view') || 'grid')
  const [page, setPage] = useState(1)
  const [taskHistoryOpen, setTaskHistoryOpen] = useState(false)
  const [taskHistory, setTaskHistory] = useState({ tasks: [], total: 0, invalidCount: 0 })
  const [taskPage, setTaskPage] = useState(1)
  const [taskLoading, setTaskLoading] = useState(false)
  const [taskError, setTaskError] = useState('')
  const [taskReload, setTaskReload] = useState(0)
  const [deletingInvalid, setDeletingInvalid] = useState(false)

  const persistUrl = useCallback(() => {
    const params = new URLSearchParams(location.search)
    params.set('screen', 'library')
    if (query.trim()) params.set('q', query.trim())
    else params.delete('q')
    if (state !== 'all') params.set('state', state)
    else params.delete('state')
    if (sort !== 'recent') params.set('sort', sort)
    else params.delete('sort')
    history.replaceState(null, '', `${location.pathname}?${params.toString()}`)
  }, [query, state, sort])

  useEffect(() => { persistUrl() }, [persistUrl])
  useEffect(() => { setDraftQuery(query) }, [query])
  useEffect(() => { localStorage.setItem('library-view', view) }, [view])

  const stateCounts = useMemo(() => {
    return READING_STATES.map(item => ({
      ...item,
      count: item.key === 'all' ? allBooks.length : allBooks.filter(book => deriveReadingState(book) === item.key).length
    }))
  }, [allBooks])

  const filteredBooks = useMemo(() => {
    let result = allBooks
    if (state !== 'all') result = result.filter(book => deriveReadingState(book) === state)
    if (query.trim()) {
      const pattern = query.trim().toLowerCase()
      result = result.filter(book =>
        book.title.toLowerCase().includes(pattern) ||
        (book.author || '').toLowerCase().includes(pattern) ||
        (book.series?.title || '').toLowerCase().includes(pattern)
      )
    }
    return result
  }, [allBooks, state, query])

  const sortedBooks = useMemo(() => {
    const copy = [...filteredBooks]
    if (sort === 'recent') copy.sort((a, b) => new Date(b.updatedAt || b.createdAt) - new Date(a.updatedAt || a.createdAt))
    else if (sort === 'title') copy.sort((a, b) => a.title.localeCompare(b.title))
    else if (sort === 'progress') copy.sort((a, b) => (b.progress || 0) - (a.progress || 0))
    return copy
  }, [filteredBooks, sort])

  const paginatedBooks = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE
    return sortedBooks.slice(start, start + PAGE_SIZE)
  }, [sortedBooks, page])

  useEffect(() => { setPage(1) }, [state, query, sort])

  useEffect(() => {
    if (!taskHistoryOpen) return
    setTaskLoading(true); setTaskError('')
    getJson(`/api/workspace/imports?limit=8&offset=${(taskPage - 1) * 8}`)
      .then(data => setTaskHistory({ tasks: data.tasks || [], total: data.total || 0, invalidCount: data.invalidCount || 0 }))
      .catch(error => setTaskError(error.message || '加载失败'))
      .finally(() => setTaskLoading(false))
  }, [taskHistoryOpen, taskPage, taskReload])

  const deleteInvalid = async () => {
    setDeletingInvalid(true)
    try {
      await deleteJson('/api/workspace/imports/invalid')
      messageApi.success('已删除无效任务')
      setTaskReload(value => value + 1)
    } catch (error) {
      messageApi.error(error.message || '删除失败')
    } finally {
      setDeletingInvalid(false)
    }
  }

  const remove = async book => {
    Modal.confirm({
      title: book.source === '官方读物' ? '移出书架' : '永久删除',
      content: book.source === '官方读物' ? '从书架移出后可以重新添加，音视频内容会释放收藏名额。' : '删除后无法恢复，确定要删除吗？',
      okText: '确定',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          if (book.source === '官方读物') await deleteJson(`/api/library/items/${encodeURIComponent(book.id)}`)
          else await deleteJson(`/api/workspace/books/${encodeURIComponent(book.id)}`)
          await onRefresh?.()
          messageApi.success(book.source === '官方读物' ? '已移出书架' : '已删除')
        } catch (error) {
          messageApi.error(error.message || '操作失败')
        }
      }
    })
  }

  const taskList = tasks => {
    if (!tasks.length) return <Empty description="还没有导入任务" />
    return <div className="import-task-list">{tasks.map(task => (
      <div key={task.id} className="import-task-item">
        <FileTextOutlined />
        <div className="import-task-body">
          <div><Text strong>{task.title || task.filename || '未命名'}</Text></div>
          <div><Text type="secondary">{task.status === 'pending' ? '等待中' : task.status === 'processing' ? '处理中' : task.status === 'complete' ? '已完成' : task.status === 'failed' ? '失败' : '已取消'}</Text></div>
          {task.status === 'processing' && task.progress > 0 && <Progress percent={task.progress} size="small" />}
          {task.status === 'failed' && <Text type="danger">{task.error || '导入失败'}</Text>}
        </div>
        {task.status === 'processing' && <Button size="small" onClick={() => onCancelImport?.(task)}>取消</Button>}
        {task.status === 'failed' && <Button size="small" onClick={() => onRetryImport?.(task)}>重试</Button>}
      </div>
    ))}</div>
  }

  if (!currentUser) return <Card><Alert type="info" message="请先登录" /></Card>

  return <div className="page-stack library-page">
    <div className="library-head">
      <div>
        <Title level={1}>我的书架</Title>
        <Paragraph>继续读未读完的内容，整理稍后读的，清理已读完的。</Paragraph>
      </div>
      <Space>
        <Button icon={<SearchOutlined />} onClick={() => selectScreen('catalog')}>去书城</Button>
        <Button type="primary" icon={<PlusOutlined />} onClick={openImport}>导入读物</Button>
      </Space>
    </div>

    {activeTasks.length > 0 && <div className="library-import-banner">
      <Text strong>正在导入 {activeTasks.length} 个任务</Text>
      <Button type="link" size="small" onClick={() => setTaskHistoryOpen(true)}>查看详情</Button>
      {taskList(activeTasks.slice(0, 3))}
    </div>}

    <div className="library-toolbar">
      <Input
        allowClear
        value={draftQuery}
        prefix={<SearchOutlined />}
        placeholder="搜索标题、作者或系列"
        onChange={e => setDraftQuery(e.target.value)}
        onPressEnter={() => { setQuery(draftQuery); setPage(1) }}
        onBlur={() => { if (draftQuery !== query) { setQuery(draftQuery); setPage(1) } }}
        style={{ width: 280 }}
      />
      <div className="library-state-chips">
        {stateCounts.map(item => (
          <button
            key={item.key}
            type="button"
            className={`library-state-chip${state === item.key ? ' is-active' : ''}`}
            onClick={() => setState(item.key)}
          >
            {item.label}<span className="count">{item.count}</span>
          </button>
        ))}
      </div>
      <Space style={{ marginLeft: 'auto' }}>
        <Select value={sort} onChange={setSort} style={{ width: 120 }} size="small" options={[
          { value: 'recent', label: '最近更新' },
          { value: 'title', label: '标题' },
          { value: 'progress', label: '进度' },
        ]} />
        <Button.Group size="small">
          <Button type={view === 'grid' ? 'primary' : 'default'} icon={<AppstoreOutlined />} onClick={() => setView('grid')} />
          <Button type={view === 'list' ? 'primary' : 'default'} icon={<BarsOutlined />} onClick={() => setView('list')} />
        </Button.Group>
        <Button size="small" onClick={() => setTaskHistoryOpen(true)}>导入记录</Button>
      </Space>
    </div>

    <div className="library-result-bar">
      <Text type="secondary">{sortedBooks.length} 本{state !== 'all' ? ` · ${stateCounts.find(s => s.key === state)?.label}` : ''}</Text>
    </div>

    {sortedBooks.length === 0 ? (
      <Card className="library-empty">
        <Empty
          image={<InboxOutlined style={{ fontSize: 64, color: '#d0d0d0' }} />}
          description={
            allBooks.length === 0 ? (
              <div>
                <Paragraph>书架还是空的</Paragraph>
                <Paragraph type="secondary">从书城挑一篇今天读得完的内容，<br />或导入自己的 PDF、YouTube 视频开始学习。</Paragraph>
              </div>
            ) : query.trim() ? (
              <Paragraph>没有匹配"{query}"的读物</Paragraph>
            ) : state === 'finished' ? (
              <Paragraph>还没有已读完的读物<br /><Text type="secondary">把正在读的内容读到 95% 以上，就会出现在这里。</Text></Paragraph>
            ) : (
              <Paragraph>没有符合条件的读物</Paragraph>
            )
          }
        >
          {allBooks.length === 0 && <Space>
            <Button type="primary" onClick={() => selectScreen('catalog')}>去书城看看</Button>
            <Button onClick={openImport}>导入读物</Button>
          </Space>}
          {allBooks.length > 0 && query.trim() && <Button onClick={() => { setQuery(''); setDraftQuery('') }}>清除搜索</Button>}
          {allBooks.length > 0 && !query.trim() && state !== 'all' && <Button onClick={() => setState('all')}>查看全部书架</Button>}
        </Empty>
      </Card>
    ) : (
      <>
        <div className={`library-results ${view}`}>
          {paginatedBooks.map(book => (
            <LibraryBookCard key={book.id} book={book} view={view} openReader={openReader} onRemove={remove} />
          ))}
        </div>
        {sortedBooks.length > PAGE_SIZE && (
          <div className="library-pagination">
            <Pagination
              current={page}
              pageSize={PAGE_SIZE}
              total={sortedBooks.length}
              showSizeChanger={false}
              showTotal={total => `共 ${total} 本`}
              onChange={value => { setPage(value); window.scrollTo({ top: 0 }) }}
            />
          </div>
        )}
      </>
    )}

    <Modal width={820} title="导入记录" open={taskHistoryOpen} onCancel={() => setTaskHistoryOpen(false)} footer={null}>
      <div className="import-history-toolbar">
        <Text type="secondary">共 {taskHistory.total} 条任务</Text>
        <Button danger loading={deletingInvalid} disabled={taskLoading || Boolean(taskError) || !taskHistory.invalidCount} onClick={deleteInvalid}>
          删除无效任务
        </Button>
      </div>
      {taskError ? (
        <Empty description={taskError}><Button onClick={() => setTaskReload(value => value + 1)}>重新加载</Button></Empty>
      ) : (
        <div aria-busy={taskLoading}>
          {taskLoading ? <Progress percent={99} status="active" showInfo={false} /> : taskList(taskHistory.tasks)}
        </div>
      )}
      <div className="list-pagination">
        <Pagination
          current={taskPage}
          pageSize={8}
          total={taskHistory.total}
          showSizeChanger={false}
          showTotal={total => `共 ${total} 条`}
          onChange={setTaskPage}
          disabled={taskLoading}
        />
      </div>
    </Modal>
  </div>
}

function LibraryBookCard({ book, view, openReader, onRemove }) {
  const readingState = deriveReadingState(book)
  const progress = book.progress || 0
  const showProgress = progress > 0 && progress < 95
  const isFinished = progress >= 95

  const menuItems = [
    {
      key: 'remove',
      label: book.source === '官方读物' ? '移出书架' : '永久删除',
      icon: <DeleteOutlined />,
      danger: true,
      onClick: () => onRemove(book)
    }
  ]

  if (view === 'list') {
    return <article className="library-row">
      <div className="library-row-cover">
        <BookCover book={book} />
      </div>
      <div className="library-row-body">
        <Title level={4} className="library-row-title">{book.title}</Title>
        <div className="library-row-meta">
          {book.author && <Text>{book.author}</Text>}
          {book.level && <Text> · {book.level}</Text>}
          <Tag>{book.source}</Tag>
        </div>
        {showProgress && (
          <Progress percent={progress} strokeColor="#f4a261" showInfo={false} size="small" style={{ maxWidth: 200 }} />
        )}
        {isFinished && <Tag color="success">已读完</Tag>}
        <Text type="secondary" className="library-row-time">{formatLastUpdated(book.updatedAt)}</Text>
      </div>
      <Space className="library-row-actions">
        <Button type="primary" onClick={() => openReader(book)}>
          {progress === 0 ? '开始阅读' : '继续阅读'}
        </Button>
        <Dropdown menu={{ items: menuItems }} trigger={['click']} placement="bottomRight">
          <Button icon={<MoreOutlined />} />
        </Dropdown>
      </Space>
    </article>
  }

  return <article className="library-card">
    <div className="library-cover-wrapper">
      <BookCover book={book} />
      {showProgress && (
        <div className="library-cover-overlay">
          <Progress percent={progress} strokeColor="#f4a261" showInfo={false} size="small" />
        </div>
      )}
      {isFinished && <div className="library-cover-badge">✓ 已读完</div>}
    </div>
    <div className="library-card-body">
      <Dropdown menu={{ items: menuItems }} trigger={['click']} placement="bottomRight">
        <Button type="text" icon={<MoreOutlined />} size="small" className="library-card-menu" />
      </Dropdown>
      <Title level={5} className="library-card-title">{book.title}</Title>
      <div className="library-card-meta">
        {book.author && <Text>{book.author}</Text>}
        {book.author && book.level && <Text> · </Text>}
        {book.level && <Text>{book.level}</Text>}
        {(book.author || book.level) && book.source && <Text> · </Text>}
        {book.source && <Tag size="small">{book.source}</Tag>}
      </div>
      <Text type="secondary" className="library-card-time">{formatLastUpdated(book.updatedAt)}</Text>
      <Button type="primary" block onClick={() => openReader(book)}>
        {progress === 0 ? '开始阅读' : '继续阅读'}
      </Button>
    </div>
  </article>
}
