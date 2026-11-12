import React, { lazy, Suspense, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Button, Drawer, Empty, InputNumber, Slider, Spin, Tooltip } from 'antd'
import { LeftOutlined, RightOutlined, UnorderedListOutlined } from '@ant-design/icons'
import { blockParts, pageForOffset, readingBlocks, readingChapters } from '../utils/extensiveReading.mjs'
import './extensive-reader.css'
import useBookPageTurn from './useBookPageTurn'

const PdfReadingPage = lazy(() => import('./PdfReadingPage'))
const EpubSourceReader = lazy(() => import('./EpubSourceReader'))

export default function ExtensiveReader(props) {
  if (!props.trial && props.book.readingDocument?.source?.version === 1) return <Suspense fallback={<Spin />}><EpubSourceReader {...props} /></Suspense>
  return <DocumentReader {...props} />
}

function DocumentReader({ book, title, appearance, active, readingLocation, onPosition, actions, sentenceRefs, pdf, trial, onAdd, adding, positionSave, onRetryPosition }) {
  const [paper, turn] = useBookPageTurn()
  const blocks = useMemo(() => readingBlocks(book), [book])
  const chapters = useMemo(() => readingChapters(blocks, title), [blocks, title])
  const indexById = useMemo(() => new Map(book.sentences.map((s, i) => [String(s.id), i])), [book.sentences])
  const viewport = useRef(null), stream = useRef(null), pageMap = useRef([]), anchor = useRef(null), position = useRef(onPosition)
  position.current = onPosition
  const [page, setPage] = useState(() => pdf && !trial ? Math.max(0, Number(readingLocation?.page || book.sentences[active]?.page || 1) - 1) : 0), [pages, setPages] = useState(1), [width, setWidth] = useState(0), [contents, setContents] = useState(false)
  const [measured, setMeasured] = useState(false)
  const originalPdf = Boolean(pdf && !trial)
  const activeId = String(book.sentences[active]?.id || '')
  const initialId = useRef(activeId)
  const go = useCallback(target => {
    const next = Math.max(0, Math.min(pages - 1, Number(target) || 0))
    if (next !== page) turn(next > page ? 1 : -1)
    setPage(next)
    const word = pageMap.current[next]
    if (word) {
      anchor.current = word.key
      const index = indexById.get(word.sentenceId)
      if (index !== undefined) position.current(index)
    } else if (originalPdf) {
      const index = book.sentences.findIndex(s => Number(s.page) === next + 1)
      position.current(index >= 0 ? index : active, book.readingDocument?.format === 'pdf' ? { format: 'pdf', page: next + 1 } : undefined)
    }
  }, [pages, page, indexById, originalPdf, book.sentences, active, turn])

  useLayoutEffect(() => {
    if (originalPdf) return
    const container = viewport.current, flow = stream.current
    if (!container || !flow) return
    let frame, disposed = false
    const measure = () => {
      if (disposed || !container.clientWidth || !container.clientHeight) return
      const w = container.clientWidth, step = w + 48
      flow.style.columnWidth = `${w}px`
      const base = flow.getBoundingClientRect().left
      const count = Math.max(1, Math.ceil((flow.scrollWidth + 48) / step))
      const starts = [], locations = new Map()
      for (const node of flow.querySelectorAll('[data-reading-word]')) {
        const p = pageForOffset(node.getBoundingClientRect().left - base, w)
        const item = { key: node.dataset.readingWord, sentenceId: node.dataset.sentenceId, pageLabel: node.closest('[data-page-label]')?.dataset.pageLabel }
        if (!starts[p]) starts[p] = item
        locations.set(item.key, p)
      }
      pageMap.current = starts
      const requested = anchor.current || `${initialId.current}:0`
      const next = Math.min(count - 1, locations.get(requested) ?? 0)
      setWidth(w); setPages(count); setPage(next); setMeasured(true)
    }
    const schedule = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(measure) }
    const observer = new ResizeObserver(schedule)
    observer.observe(container); schedule()
    document.fonts?.ready.then(schedule)
    return () => { disposed = true; cancelAnimationFrame(frame); observer.disconnect() }
  }, [blocks, appearance, originalPdf])

  // Existing "locate original sentence" changes focus on the same real sentence anchor.
  useEffect(() => {
    if (originalPdf || !measured) return
    const current = pageMap.current[page]
    if (current?.sentenceId === activeId) return
    const node = Array.from(stream.current?.querySelectorAll('[data-reading-word]') || []).find(n => n.dataset.sentenceId === activeId)
    if (node) {
      anchor.current = node.dataset.readingWord
      setPage(pageForOffset(node.getBoundingClientRect().left - stream.current.getBoundingClientRect().left, width))
    }
  }, [activeId])

  useEffect(() => {
    const handler = event => {
      if (event.ctrlKey || event.metaKey || event.altKey || contents || document.querySelector('.ant-modal-wrap:not([style*="display: none"])')) return
      if (event.target.closest?.('input,textarea,select,button,[role="button"],[role="dialog"],[role="combobox"],[contenteditable="true"],.reader-lookup-card,.reader-inspector')) return
      const backwards = ['ArrowLeft', 'PageUp'].includes(event.key) || (event.key === ' ' && event.shiftKey)
      if (backwards || ['ArrowRight', 'PageDown', ' '].includes(event.key)) {
        event.preventDefault(); go(page + (backwards ? -1 : 1))
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [go, page, contents])

  const jump = chapter => {
    setContents(false)
    if (originalPdf) { go((chapter.page || 1) - 1); return }
    const node = document.getElementById(`reading-${chapter.id}`)
    if (node && stream.current) go(pageForOffset(node.getBoundingClientRect().left - stream.current.getBoundingClientRect().left, width))
  }
  const currentSection = [...chapters].reverse().find(c => {
    const node = document.getElementById(`reading-${c.id}`)
    return node && stream.current && pageForOffset(node.getBoundingClientRect().left - stream.current.getBoundingClientRect().left, width) <= page
  })
  const percent = Math.round(((page + 1) / pages) * 100)
  const navigationChapters = originalPdf ? Array.from({ length: pages }, (_, i) => ({ id: `pdf-${i}`, title: `第 ${i + 1} 页`, page: i + 1 })) : chapters
  return <section className="extensive-reader" aria-label="泛读模式">
    <div className="extensive-running-head"><Button type="text" aria-label="目录" icon={<UnorderedListOutlined />} onClick={() => setContents(true)}>目录</Button><span>{currentSection?.title || title}</span><span className="extensive-edition">{originalPdf ? '原版书页' : '纸间微光 · 泛读'}</span></div>
    <div className="extensive-page-stage">
      <Tooltip title="上一页 · ←"><Button className="extensive-turn extensive-turn-prev" type="text" aria-label="上一页" icon={<LeftOutlined />} disabled={!page} onClick={() => go(page - 1)} /></Tooltip>
      <div ref={paper} className={`extensive-paper ${originalPdf ? 'is-pdf' : ''}`}>
        {originalPdf ? <Suspense fallback={<div className="extensive-loading"><Spin tip="正在准备原版书页…"><div /></Spin></div>}><PdfReadingPage book={book} actions={actions} url={pdf.url} page={page + 1} onLoaded={count => { setPages(count); setMeasured(true); setPage(value => Math.min(count - 1, value)) }} /></Suspense> : <div className="extensive-viewport" ref={viewport}>
          <div className="extensive-flow" ref={stream} style={{ transform: `translateX(-${page * (width + 48)}px)`, visibility: measured ? 'visible' : 'hidden' }}>
            {blocks.map((block, i) => {
              const isTitle = i === 0 && block.text.trim().toLowerCase() === title.trim().toLowerCase()
              const Tag = isTitle ? 'h1' : block.type === 'heading' ? 'h2' : block.type === 'quote' ? 'blockquote' : 'p'
              return <Tag id={`reading-${block.id}`} key={block.id} data-page-label={block.pageLabel} className={block.section && blocks[i - 1]?.section !== block.section && i > 0 ? 'extensive-chapter-start' : ''}>
                {blockParts(block).map((part, j) => {
                  if (part.sentenceId === undefined) return <React.Fragment key={j}>{part.text}</React.Fragment>
                  const index = indexById.get(String(part.sentenceId)), sentence = book.sentences[index]
                  return <span key={j} className="reader-word extensive-word" role="button" tabIndex={-1} data-reading-word={`${part.sentenceId}:${part.wordIndex}`} data-sentence-id={String(part.sentenceId)} ref={node => { if (part.wordIndex === 0) sentenceRefs.current[index] = node }} onClick={event => actions.current.lookup(sentence, part.wordIndex, part.text, event.currentTarget)}>{part.text}</span>
                })}
              </Tag>
            })}
            {trial && <div className="extensive-trial-end"><small>试读结束</small><h2>下一页，继续读下去。</h2><p>加入书架，解锁完整内容。</p><Button type="primary" loading={adding} onClick={onAdd}>加入书架继续阅读</Button></div>}
            {!blocks.length && <Empty description="暂无可阅读的正文" />}
          </div>
        </div>}
      </div>
      <Tooltip title="下一页 · →"><Button className="extensive-turn extensive-turn-next" type="text" aria-label="下一页" icon={<RightOutlined />} disabled={page >= pages - 1} onClick={() => go(page + 1)} /></Tooltip>
    </div>
    <footer className="extensive-navigation">
      <div className="extensive-page-info"><span>{trial ? '试读' : '阅读进度'} {percent}%</span><div><span>当前页</span><span className="extensive-page-number"><InputNumber style={{ '--page-digits': String(page + 1).length }} aria-label="跳转页码" min={1} max={pages} value={page + 1} controls={false} onChange={value => { if (value) go(value - 1) }} /><span>/{pages}页</span></span></div><span>{originalPdf ? '保留原始排版与页数' : '← → 翻页 · 点击单词查词'}</span></div>
      <Slider aria-label="阅读翻页进度" min={1} max={Math.max(1, pages)} value={page + 1} tooltip={{ formatter: value => `第 ${value} 页` }} onChange={value => go(value - 1)} />
      <div className="extensive-footnote"><span>{originalPdf ? 'PDF 原版' : `保留原文段落 · ${pageMap.current[page]?.pageLabel ? `原书页码 ${pageMap.current[page].pageLabel} · ` : ''}页数随字号调整`}</span><span role="status">{trial?'试读进度不保存':positionSave?.state==='error'?<Button size="small" type="link" danger title={positionSave.error} onClick={onRetryPosition}>重试保存进度</Button>:positionSave?.state==='saved'?'进度已保存':positionSave?.state==='saving'?'正在保存进度…':'进度自动保留'}</span><span>纸间微光</span></div>
    </footer>
    <Drawer className="extensive-contents" title={originalPdf?'原文页码':'目录'} placement="left" width={340} open={contents} onClose={() => setContents(false)}><p className="extensive-contents-title">{title}</p><nav aria-label="章节目录">{navigationChapters.map((chapter, index) => <button key={chapter.id || index} onClick={() => jump(chapter)}><small>{String(index + 1).padStart(2, '0')}</small><span>{chapter.title}</span></button>)}</nav></Drawer>
  </section>
}
