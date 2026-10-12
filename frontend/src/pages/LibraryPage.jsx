import React, { useEffect, useMemo, useState } from 'react'
import { Button, Card, Dropdown, Empty, Input, List, Modal, Pagination, Progress, Select, Space, Tag, Typography } from 'antd'
import { FileTextOutlined, MoreOutlined, PlusOutlined } from '@ant-design/icons'

import { deleteJson, postJson } from '../api/client'

const { Paragraph, Text, Title } = Typography

function Cover({ book }) {
  return <div className="book-cover" style={{ '--cover': book.accent || '#dce9d8' }}><span>{String(book.title || '书').slice(0, 2).toUpperCase()}</span><small>{book.title}</small></div>
}

export default function LibraryPage({ libraryBooks, books: fallbackBooks, importTasks, openReader, openImport, onCancelImport, onRefresh, messageApi }) {
  const books = libraryBooks?.length ? libraryBooks : fallbackBooks || []
  const tasks = importTasks || []
  const [query, setQuery] = useState('')
  const [source, setSource] = useState('全部')
  const [sort, setSort] = useState('recent')
  const [page, setPage] = useState(1)
  const [taskHistoryOpen, setTaskHistoryOpen] = useState(false)
  const visibleBooks = useMemo(() => books.filter(book => `${book.title} ${book.subtitle || ''} ${book.author || ''}`.toLowerCase().includes(query.toLowerCase()) && (source === '全部' || book.source === source)).sort((a, b) => sort === 'title' ? a.title.localeCompare(b.title) : sort === 'progress' ? b.progress - a.progress : String(b.updatedAt || b.addedAt || '').localeCompare(String(a.updatedAt || a.addedAt || ''))), [books, query, sort, source])
  const pageSize = 8
  const pageBooks = visibleBooks.slice((page - 1) * pageSize, page * pageSize)
  useEffect(() => { setPage(1) }, [query, sort, source])
  useEffect(() => { if ((page - 1) * pageSize >= visibleBooks.length && page > 1) setPage(Math.max(1, Math.ceil(visibleBooks.length / pageSize))) }, [page, visibleBooks.length])

  const removeBook = book => Modal.confirm({
    title: book.source === '官方读物' ? `将《${book.title}》移出书架？` : `永久删除《${book.title}》？`,
    content: book.source === '官方读物' ? '已消耗的解锁额度不会退回，以后仍可重新加入书架。' : '该操作会删除私人读物、阅读进度、生词和标注；媒体文件进入待清理状态。',
    okText: book.source === '官方读物' ? '移出书架' : '永久删除',
    okButtonProps: { danger: true },
    onOk: async () => {
      try {
        if (book.source === '官方读物') await deleteJson(`/api/library/items/${encodeURIComponent(book.id)}`)
        else await deleteJson(`/api/workspace/books/${encodeURIComponent(book.id)}`, { confirmTitle: book.title })
        await onRefresh?.()
        messageApi.success(book.source === '官方读物' ? '已移出书架' : '私人读物已删除')
      } catch (error) { messageApi.error(error.message); throw error }
    },
  })

  const archiveBook = async book => {
    try {
      await postJson('/api/library/items', { bookId: book.id, shelfState: book.shelfState === 'archived' ? 'active' : 'archived' })
      await onRefresh?.()
      messageApi.success(book.shelfState === 'archived' ? '已恢复到书架' : '已归档')
    } catch (error) { messageApi.error(error.message) }
  }

  const taskList = list => <List size="small" dataSource={list} locale={{ emptyText: '暂无导入任务' }} renderItem={task => <List.Item actions={[
    ...(['queued', 'uploading', 'running', 'processing'].includes(task.status) ? [<Button key="cancel" size="small" danger onClick={() => onCancelImport?.(task)}>取消</Button>] : []),
    ...(task.status === 'failed' ? [<Button key="retry" size="small" onClick={openImport}>重新导入</Button>] : []),
  ]}><List.Item.Meta title={task.title || task.originalFilename || '未命名导入任务'} description={<><Text type={task.status === 'failed' ? 'danger' : 'secondary'}>{task.error || task.step || task.status}</Text><br /><Text type="secondary">{new Date(task.updatedAt || task.createdAt).toLocaleString('zh-CN')}</Text></>} /><div className="import-task-progress"><Progress percent={task.progress} status={task.status === 'failed' ? 'exception' : task.status === 'complete' ? 'success' : 'active'} /><Tag>{task.status}</Tag></div></List.Item>} />

  return <div className="page-stack"><div className="page-intro"><div><Text className="eyebrow">YOUR LIBRARY</Text><Title level={1}>我的书架</Title><Paragraph>管理官方收藏、私人导入、归档内容和完整导入任务记录。</Paragraph></div><Button type="primary" icon={<PlusOutlined />} onClick={openImport}>导入读物</Button></div><Card className="filter-card"><Space wrap><Input allowClear prefix={<FileTextOutlined />} placeholder="搜索我的读物" value={query} onChange={event => setQuery(event.target.value)} style={{ width: 280 }} /><Select value={source} onChange={setSource} options={['全部', '官方读物', '私人读物'].map(value => ({ value, label: value }))} /><Select value={sort} onChange={setSort} options={[{ value: 'recent', label: '最近更新' }, { value: 'progress', label: '阅读进度' }, { value: 'title', label: '标题排序' }]} /></Space></Card>{tasks.length > 0 && <Card title="最近导入任务" extra={<Button type="link" onClick={() => setTaskHistoryOpen(true)}>查看全部</Button>}>{taskList(tasks.slice(0, 3))}</Card>}<Card className="table-card"><List itemLayout="horizontal" dataSource={pageBooks} locale={{ emptyText: <Empty description="还没有符合条件的读物" /> }} renderItem={book => <List.Item actions={[<Button key="read" type="primary" ghost onClick={() => openReader(book)}>{book.progress ? '继续阅读' : '开始阅读'}</Button>, <Dropdown key="more" trigger={['click']} menu={{ items: [...(book.source === '官方读物' ? [{ key: 'archive', label: book.shelfState === 'archived' ? '恢复到书架' : '归档' }] : []), { key: 'remove', label: book.source === '官方读物' ? '移出书架' : '永久删除', danger: true }], onClick: ({ key }) => key === 'archive' ? archiveBook(book) : removeBook(book) }}><Button type="text" icon={<MoreOutlined />} /></Dropdown>]}><List.Item.Meta avatar={<Cover book={book} />} title={<Space>{book.title}<Tag color={book.source === '官方读物' ? 'gold' : 'green'}>{book.source}</Tag>{book.shelfState === 'archived' && <Tag>已归档</Tag>}</Space>} description={<><Text type="secondary">{book.author || '未知作者'} · {book.level || '未分级'}</Text><Progress percent={book.progress || 0} size="small" strokeColor="#2f6f50" /></>} /></List.Item>} />{visibleBooks.length > pageSize && <div className="list-pagination"><Pagination current={page} pageSize={pageSize} total={visibleBooks.length} showSizeChanger={false} showTotal={total => `共 ${total} 本`} onChange={setPage} /></div>}</Card><Modal width={820} title="全部导入任务" open={taskHistoryOpen} onCancel={() => setTaskHistoryOpen(false)} footer={null}>{taskList(tasks)}</Modal></div>
}
