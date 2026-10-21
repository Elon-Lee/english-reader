import Cover from '../components/BookCover'
import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Button, Card, Dropdown, Empty, Input, List, Modal, Pagination, Progress, Select, Space, Tag, Typography } from 'antd'
import { FileTextOutlined, MoreOutlined, PlusOutlined } from '@ant-design/icons'

import { deleteJson, getJson, postJson } from '../api/client'

const { Paragraph, Text, Title } = Typography



export default function LibraryPage({ libraryBooks, importTasks, openReader, openImport, onCancelImport, onRetryImport, onRefresh, messageApi, currentUser, selectScreen }) {
  const books = libraryBooks || []
  const tasks = (importTasks || []).filter(task => !['complete', 'cancelled'].includes(task.status))
  const [query, setQuery] = useState('')
  const [source, setSource] = useState('全部')
  const [sort, setSort] = useState('recent')
  const [page, setPage] = useState(1)
  const [taskHistoryOpen, setTaskHistoryOpen] = useState(false)
  const [taskPage, setTaskPage] = useState(1)
  const [taskHistory, setTaskHistory] = useState({ tasks: [], total: 0, invalidCount: 0 })
  const [taskLoading, setTaskLoading] = useState(false)
  const [taskError, setTaskError] = useState('')
  const [taskReload, setTaskReload] = useState(0)
  const [deletingInvalid, setDeletingInvalid] = useState(false)
  const historyRequest = useRef(0)
  const [retryingTaskId, setRetryingTaskId] = useState('')
  const [shelfFilter, setShelfFilter] = useState('active')
  const [archivingBookId, setArchivingBookId] = useState('')
  const archivePending = useRef(false)
  useEffect(() => {
    if (!taskHistoryOpen) return
    let disposed = false
    const load = async (foreground = false) => {
      const request = ++historyRequest.current
      if (foreground) setTaskLoading(true)
      try {
        const data = await getJson(`/api/workspace/imports?page=${taskPage}&limit=8`)
        if (disposed || request !== historyRequest.current) return
        const lastPage = Math.max(1, Math.ceil(data.total / 8))
        if (taskPage > lastPage) { setTaskPage(lastPage); return }
        setTaskHistory(data); setTaskError('')
      } catch (error) { if (!disposed && request === historyRequest.current) setTaskError(error.message) }
      finally { if (!disposed && request === historyRequest.current) setTaskLoading(false) }
    }
    void load(true)
    const timer = setInterval(() => { void load() }, 3000)
    return () => { disposed = true; clearInterval(timer) }
  }, [taskHistoryOpen, taskPage, taskReload])

  const deleteInvalid = () => Modal.confirm({
    title: '删除无效任务？',
    content: '将删除当前账号的全部失败和已取消的任务记录，删除后无法从这些记录重试。已完成和正在处理的任务会保留。',
    okText: '删除无效任务', okButtonProps: { danger: true },
    onOk: async () => {
      setDeletingInvalid(true)
      ++historyRequest.current
      try {
        const result = await postJson('/api/workspace/imports/delete-invalid', {})
        setTaskReload(value => value + 1)
        await onRefresh?.()
        messageApi.success(`已删除 ${result.deletedCount} 条无效任务`)
      } catch (error) { messageApi.error(error.message); throw error }
      finally { setDeletingInvalid(false) }
    },
  })
  const visibleBooks = useMemo(() => books.filter(book => `${book.title} ${book.subtitle || ''} ${book.author || ''}`.toLowerCase().includes(query.toLowerCase()) && (source === '全部' || book.source === source)).sort((a, b) => sort === 'title' ? a.title.localeCompare(b.title) : sort === 'progress' ? b.progress - a.progress : String(b.updatedAt || b.addedAt || '').localeCompare(String(a.updatedAt || a.addedAt || ''))), [books, query, sort, source])
  const pageSize = 8
  const filteredBooks = visibleBooks.filter(book => shelfFilter === 'all' || (shelfFilter === 'later' ? book.shelfState === 'later' : book.shelfState !== 'later'))
  const pageBooks = filteredBooks.slice((page - 1) * pageSize, page * pageSize)
  useEffect(() => { setPage(1) }, [query, sort, source, shelfFilter])
  useEffect(() => { if ((page - 1) * pageSize >= filteredBooks.length && page > 1) setPage(Math.max(1, Math.ceil(filteredBooks.length / pageSize))) }, [page, filteredBooks.length])

  const removeBook = book => Modal.confirm({
    title: book.source === '官方读物' ? `将《${book.title}》移出书架？` : `永久删除《${book.title}》？`,
    content: book.source === '官方读物' ? '移出后将停止该读物的阅读和媒体访问，并释放收藏名额。学习记录会保留，重新加入时需符合当前套餐的收藏上限。' : '该操作会删除私人读物、阅读进度、生词和标注；并清理关联媒体文件，无法恢复。',
    okText: book.source === '官方读物' ? '移出书架' : '永久删除',
    okButtonProps: { danger: true },
    onOk: async () => {
      try {
        if (book.source === '官方读物') await deleteJson(`/api/library/items/${encodeURIComponent(book.id)}`)
        else {
          const result = await deleteJson(`/api/workspace/books/${encodeURIComponent(book.id)}`, { confirmTitle: book.title })
          if (result.pendingFiles) messageApi.warning('内容已删除，部分媒体文件待清理')
        }
        await onRefresh?.()
        messageApi.success(book.source === '官方读物' ? '已移出书架' : '私人读物已删除')
      } catch (error) { messageApi.error(error.message); throw error }
    },
  })

  const archiveBook = async book => {
    if (archivePending.current) return
    archivePending.current = true
    setArchivingBookId(book.id)
    try {
      await postJson('/api/library/items', { bookId: book.id, shelfState: book.shelfState === 'later' ? 'active' : 'later' })
      await onRefresh?.()
      messageApi.success(book.shelfState === 'later' ? '已恢复到书架' : '已归档，可在“已归档”中查看')
    } catch (error) { messageApi.error(error.message) }
    finally { archivePending.current = false; setArchivingBookId('') }
  }

  const taskList = list => <List size="small" dataSource={list} locale={{ emptyText: '暂无导入任务' }} renderItem={task => <List.Item actions={[
    ...(['queued', 'uploading', 'running', 'processing'].includes(task.status) ? [<Button key="cancel" size="small" danger onClick={() => onCancelImport?.(task)}>取消</Button>] : []),
    ...(task.status === 'failed' ? [<Button key="retry" size="small" loading={retryingTaskId === task.id} onClick={async () => { setRetryingTaskId(task.id); try { await onRetryImport?.(task) } finally { setRetryingTaskId('') } }}>重试</Button>] : []),
  ]}><List.Item.Meta title={task.title || task.originalFilename || '未命名导入任务'} description={<><Text type={task.status === 'failed' ? 'danger' : 'secondary'}>{task.error || task.step || task.status}</Text><br /><Text type="secondary">导入时间：{task.createdAt ? new Date(task.createdAt).toLocaleString('zh-CN', { hour12: false }) : '—'}</Text></>} /><div className="import-task-progress"><Progress percent={task.progress} status={task.status === 'failed' ? 'exception' : task.status === 'complete' ? 'success' : 'active'} /><Tag>{task.status}</Tag></div></List.Item>} />

  return <div className="page-stack"><div className="page-intro"><div><Text className="eyebrow">YOUR LIBRARY</Text><Title level={1}>我的书架</Title><Paragraph>归档会收起暂时不读的官方收藏，保留学习记录和阅读权限，仍占收藏名额；移出书架才会释放名额。</Paragraph></div><Space>{currentUser?.isAdmin && <Button onClick={() => selectScreen('admin', 'catalog')}>管理书城上架 / 下架</Button>}<Button type="primary" icon={<PlusOutlined />} onClick={openImport}>导入读物</Button><Button onClick={() => setTaskHistoryOpen(true)}>导入记录</Button></Space></div><Card className="filter-card"><Space wrap><Input allowClear prefix={<FileTextOutlined />} placeholder="搜索我的读物" value={query} onChange={event => setQuery(event.target.value)} style={{ width: 280 }} /><Select value={source} onChange={setSource} options={['全部', '官方读物', '私人读物'].map(value => ({ value, label: value }))} /><Select aria-label="书架状态" value={shelfFilter} onChange={setShelfFilter} options={[{ value: 'active', label: '当前书架' }, { value: 'later', label: '已归档' }, { value: 'all', label: '全部状态' }]} /><Select value={sort} onChange={setSort} options={[{ value: 'recent', label: '最近更新' }, { value: 'progress', label: '阅读进度' }, { value: 'title', label: '标题排序' }]} /></Space></Card>{tasks.length > 0 && <Card title="最近导入任务" extra={<Button type="link" onClick={() => setTaskHistoryOpen(true)}>查看全部</Button>}>{taskList(tasks.slice(0, 3))}</Card>}<Card className="table-card"><List itemLayout="horizontal" dataSource={pageBooks} locale={{ emptyText: <Empty description="还没有符合条件的读物" /> }} renderItem={book => <List.Item actions={[<Button key="read" type="primary" ghost onClick={() => openReader(book)}>{book.progress ? '继续阅读' : '开始阅读'}</Button>, <Dropdown disabled={Boolean(archivingBookId)} key="more" trigger={['click']} menu={{ items: [...(book.source === '官方读物' ? [{ key: 'archive', label: book.shelfState === 'later' ? '恢复到书架' : '归档' }] : []), { key: 'remove', label: book.source === '官方读物' ? '移出书架' : '永久删除', danger: true }], onClick: ({ key }) => key === 'archive' ? archiveBook(book) : removeBook(book) }}><Button loading={archivingBookId === book.id} type="text" icon={<MoreOutlined />} /></Dropdown>]}><List.Item.Meta avatar={<Cover book={book} />} title={<Space>{book.title}<Tag color={book.source === '官方读物' ? 'gold' : 'green'}>{book.source}</Tag>{book.shelfState === 'later' && <Tag>已归档</Tag>}</Space>} description={<><Text type="secondary">{book.author || '未知作者'} · {book.level || '未分级'}</Text><Progress percent={book.progress || 0} size="small" strokeColor="#2f6f50" /></>} /></List.Item>} />{filteredBooks.length > pageSize && <div className="list-pagination"><Pagination current={page} pageSize={pageSize} total={filteredBooks.length} showSizeChanger={false} showTotal={total => `共 ${total} 本`} onChange={setPage} /></div>}</Card><Modal width={820} title="全部导入任务" open={taskHistoryOpen} onCancel={() => setTaskHistoryOpen(false)} footer={null}><div className="import-history-toolbar"><Text type="secondary">共 {taskHistory.total} 条任务</Text><Button danger loading={deletingInvalid} disabled={taskLoading || Boolean(taskError) || !taskHistory.invalidCount} onClick={deleteInvalid}>删除无效任务</Button></div>{taskError ? <Empty description={taskError}><Button onClick={() => setTaskReload(value => value + 1)}>重新加载</Button></Empty> : <div aria-busy={taskLoading}>{taskLoading ? <Progress percent={99} status="active" showInfo={false} /> : taskList(taskHistory.tasks)}</div>}<div className="list-pagination"><Pagination current={taskPage} pageSize={8} total={taskHistory.total} showSizeChanger={false} showTotal={total => `共 ${total} 条`} onChange={setTaskPage} disabled={taskLoading} /></div></Modal></div>
}
