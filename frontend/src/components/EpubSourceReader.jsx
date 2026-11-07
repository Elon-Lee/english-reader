import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Alert, Button, Drawer, InputNumber, Spin } from 'antd'
import { LeftOutlined, RightOutlined, UnorderedListOutlined } from '@ant-design/icons'
import { archivePath, openEpubArchive, sourceWordRanges } from '../utils/epubSource.mjs'
import { installSourceWordHover, sourceWordAt } from '../utils/sourceWordHover.mjs'
import useBookPageTurn from './useBookPageTurn'

export default function EpubSourceReader({ book, title, active, readingLocation, onPosition, actions, positionSave, onRetryPosition }) {
  const source = book.readingDocument.source, spine = source.spine
  const saved = readingLocation
  const initialChapter = saved?.format === 'epub' ? saved.chapter : Math.max(0, spine.findIndex(s => s.section === book.sentences[active]?.section))
  const [chapter, setChapter] = useState(Math.min(spine.length - 1, initialChapter)), [page, setPage] = useState(0), [pages, setPages] = useState(1)
  const [html, setHtml] = useState(''), [error, setError] = useState(''), [busy, setBusy] = useState(true), [retry, setRetry] = useState(0), [contents, setContents] = useState(false)
  const [archive, setArchive] = useState(null)
  const navigation = useMemo(() => archive?.navigation(spine, book.readingDocument.blocks) || [], [archive, spine, book.readingDocument.blocks])
  const [paper, turn] = useBookPageTurn()
  const iframe = useRef(null), host = useRef(null), cleanup = useRef(null), ranges = useRef([]), geometry = useRef({ step: 1, scale: 1 }), current = useRef({ chapter, page, pages })
  current.current = { chapter, page, pages }
  const callbacks = useRef({ onPosition, actions }); callbacks.current = { onPosition, actions }
  const reportedActive = useRef(active)
  const target = useRef(saved?.format === 'epub' ? { offset: saved.offset } : { sentenceId: book.sentences[active]?.id })
  const fixed = spine[chapter].layout === 'fixed'
  const asset = book.mediaAssets.find(a => a.id === source.assetId) || book.mediaAssets.find(a => a.contentType === 'application/epub+zip')
  const emitPosition = useCallback((nextPage, offset) => {
    const mapped = ranges.current.find(word => {
      if (!word.range.getClientRects().length) return false
      const rect = word.range.getBoundingClientRect()
      return fixed || rect.left + current.current.page * geometry.current.step >= nextPage * geometry.current.step - 1
    }) || [...ranges.current].reverse().find(word => word.range.getClientRects().length)
    const index = mapped ? book.sentences.findIndex(s => String(s.id) === String(mapped.sentenceId)) : book.sentences.findIndex(s => s.section === spine[chapter].section)
    target.current = { offset: offset ?? mapped?.offset ?? 0 }
    reportedActive.current = Math.max(0, index)
    callbacks.current.onPosition(Math.max(0, index), { format: 'epub', chapter, offset: offset ?? mapped?.offset ?? 0 })
  }, [book.sentences, chapter, fixed, spine])

  useEffect(() => {
    const abort = new AbortController(); let opened
    setBusy(true); setError(''); setArchive(null)
    ;(async () => {
      if (!asset?.url) throw new Error('未找到可访问的 EPUB 原文件')
      const response = await fetch(asset.url, { credentials: 'include', signal: abort.signal })
      if (!response.ok) throw new Error(`EPUB 原文件加载失败（${response.status}）`)
      const bytes = await response.arrayBuffer()
      if (abort.signal.aborted) return
      opened = openEpubArchive(bytes); setArchive(opened)
    })().catch(e => { if (!abort.signal.aborted) { setError(e.message); setBusy(false) } })
    return () => { abort.abort(); opened?.close() }
  }, [asset?.url, retry])

  useEffect(() => {
    if (!archive) return
    setBusy(true); setError('')
    try { setHtml(archive.chapter(spine[chapter].href).html) }
    catch (e) { setError(e.message); setBusy(false) }
  }, [archive, chapter, spine])

  const go = useCallback((direction) => {
    const state = current.current, next = state.page + direction
    if (next >= 0 && next < state.pages) {
      turn(direction); emitPosition(next); setPage(next)
    } else if (state.chapter + direction >= 0 && state.chapter + direction < spine.length) {
      turn(direction)
      target.current = direction < 0 ? { last: true } : { offset: 0 }
      setPage(0); setChapter(state.chapter + direction)
    }
  }, [emitPosition, spine.length, turn])
  const navigate = useCallback(entry => {
    setContents(false)
    if (entry.chapter !== chapter) {
      turn(entry.chapter > chapter ? 1 : -1)
      target.current = { offset: 0, elementId: entry.elementId, sentenceId: entry.sentenceId }
      setPage(0); setChapter(entry.chapter)
      return
    }
    const doc = iframe.current?.contentDocument
    const destination = entry.elementId ? doc?.getElementById(entry.elementId) : entry.sentenceId ? ranges.current.find(word => String(word.sentenceId) === String(entry.sentenceId))?.range : null
    const next = fixed ? 0 : Math.min(current.current.pages - 1, Math.max(0, destination ? Math.floor((destination.getBoundingClientRect().left - doc.body.getBoundingClientRect().left) / geometry.current.step) : 0))
    if (next !== current.current.page) turn(next > current.current.page ? 1 : -1)
    emitPosition(next); setPage(next)
  }, [chapter, emitPosition, fixed, turn])
  const navigateRef = useRef(navigate); navigateRef.current = navigate
  const goRef = useRef(go); goRef.current = go
  const onKey = useCallback(event => {
    if (event.ctrlKey || event.metaKey || event.altKey || contents || event.target.closest?.('input,button,[role="dialog"],textarea,.reader-lookup-card,.reader-inspector') || document.querySelector('.ant-modal-wrap:not([style*="display: none"])')) return
    if (['ArrowLeft', 'PageUp', 'ArrowRight', 'PageDown', ' '].includes(event.key)) {
      event.preventDefault(); goRef.current(['ArrowLeft', 'PageUp'].includes(event.key) || (event.key === ' ' && event.shiftKey) ? -1 : 1)
    }
  }, [contents])
  useEffect(() => { window.addEventListener('keydown', onKey); return () => window.removeEventListener('keydown', onKey) }, [onKey])

  const prepare = useCallback(async () => {
    const frame = iframe.current, doc = frame?.contentDocument
    if (!doc?.body || !host.current) return
    try {
      // Wait for the original fonts and illustrations before calculating page positions.
      await doc.fonts.ready
      await Promise.all([...doc.images].map(image => image.decode?.().catch(() => {})))
      if (frame !== iframe.current || doc !== frame.contentDocument) return
      const root = doc.documentElement, body = doc.body
      const background = [body, root].map(node => frame.contentWindow.getComputedStyle(node).backgroundColor)
        .find(color => color !== 'transparent' && color !== 'rgba(0, 0, 0, 0)') || 'rgb(255, 255, 255)'
      host.current.closest('.extensive-paper').style.setProperty('--source-paper', background)
      frame.style.backgroundColor = background
      const index = sourceWordRanges(doc, spine[chapter].section, book.readingDocument.blocks)
      ranges.current = index
      const viewport = archive.chapter(spine[chapter].href).viewport
      const measure = () => {
        if (!host.current) return
        const width = host.current.clientWidth, height = host.current.clientHeight
        let measuredPage = 0, measuredPages = 1
        root.style.setProperty('overflow', 'hidden', 'important')
        if (fixed) {
          const originalWidth = Number(viewport.match(/width\s*=\s*([\d.]+)/i)?.[1]) || body.scrollWidth || width
          const originalHeight = Number(viewport.match(/height\s*=\s*([\d.]+)/i)?.[1]) || body.scrollHeight || height
          const scale = Math.min(width / originalWidth, height / originalHeight)
          geometry.current = { step: 1, scale }
          Object.assign(frame.style, { width: `${originalWidth}px`, height: `${originalHeight}px`, transform: `scale(${scale})`, left: `${(width - originalWidth * scale) / 2}px`, top: `${(height - originalHeight * scale) / 2}px` })
          root.style.width = `${originalWidth}px`; root.style.height = `${originalHeight}px`
          setPages(1); setPage(0)
        } else {
          Object.assign(frame.style, { width: '100%', height: '100%', transform: '', left: '0', top: '0' })
          const style = frame.contentWindow.getComputedStyle(body)
          const marginsX = parseFloat(style.marginLeft) + parseFloat(style.marginRight)
          const marginsY = parseFloat(style.marginTop) + parseFloat(style.marginBottom)
          const column = Math.max(1, width - marginsX)
          body.style.setProperty('width', `${column}px`, 'important'); body.style.setProperty('height', `${Math.max(1, height - marginsY)}px`, 'important')
          body.style.setProperty('column-width', `${column}px`, 'important'); body.style.setProperty('column-gap', '48px', 'important'); body.style.setProperty('column-fill', 'auto', 'important')
          body.style.transform = ''
          const count = Math.max(1, Math.ceil((body.scrollWidth + 48) / (column + 48)))
          geometry.current = { step: column + 48, scale: 1 }
          const requested = target.current
          const word = requested?.sentenceId ? index.find(w => String(w.sentenceId) === String(requested.sentenceId)) : index.find(w => w.offset >= (requested?.offset || 0))
          const destination = requested?.elementId ? doc.getElementById(requested.elementId) : word?.range
          const next = requested?.last ? count - 1 : Math.min(count - 1, Math.max(0, destination ? Math.floor((destination.getBoundingClientRect().left - body.getBoundingClientRect().left) / geometry.current.step) : 0))
          measuredPage = next; measuredPages = count
          setPages(count); setPage(next)
          body.style.transform = `translateX(-${next * geometry.current.step}px)`
        }
        current.current = { chapter, page: measuredPage, pages: measuredPages }
        setBusy(false)
        return measuredPage
      }
      emitPosition(measure())
      const observer = new ResizeObserver(() => {
        measure()
      })
      observer.observe(host.current)
      const click = event => {
        event.preventDefault()
        const link = event.target.closest?.('[data-epub-link]')?.dataset.epubLink
        if (link) {
          const destination = link.startsWith('#') ? spine[chapter].href : archivePath(spine[chapter].href, link)
          const next = spine.findIndex(item => item.href === destination)
          let fragment = ''
          try { fragment = link.includes('#') ? decodeURIComponent(link.split('#')[1]) : '' } catch { return }
          if (next >= 0) navigateRef.current({ chapter: next, elementId: fragment })
          return
        }
        const word = sourceWordAt(index, event.clientX, event.clientY)
        if (!word) return
        const sentence = book.sentences.find(s => String(s.id) === String(word.sentenceId)), rect = word.range.getBoundingClientRect(), bounds = frame.getBoundingClientRect(), scale = geometry.current.scale
        if (sentence) callbacks.current.actions.current.lookup(sentence, word.wordIndex, word.text, { getBoundingClientRect: () => ({ left: bounds.left + rect.left * scale, right: bounds.left + rect.right * scale, top: bounds.top + rect.top * scale, bottom: bounds.top + rect.bottom * scale }) })
      }
      doc.addEventListener('click', click); doc.addEventListener('keydown', onKey)
      cleanup.current?.()
      const clearHover = installSourceWordHover(body, index)
      cleanup.current = () => { clearHover(); observer.disconnect(); doc.removeEventListener('click', click); doc.removeEventListener('keydown', onKey) }
    } catch (e) { setBusy(false); setError(e.message || 'EPUB 原文页面加载失败') }
  }, [archive, chapter, fixed, book, spine, emitPosition, onKey])
  useEffect(() => () => cleanup.current?.(), [html, chapter])
  useEffect(() => {
    const body = iframe.current?.contentDocument?.body
    if (body && !fixed) body.style.transform = `translateX(-${page * geometry.current.step}px)`
  }, [page, fixed])
  useEffect(() => {
    if (active === reportedActive.current || busy) return
    reportedActive.current = active
    const sentence = book.sentences[active], destination = spine.findIndex(item => item.section === sentence?.section)
    if (destination < 0) return
    target.current = { sentenceId: sentence.id }
    if (destination !== chapter) { setPage(0); setChapter(destination); return }
    const word = ranges.current.find(item => String(item.sentenceId) === String(sentence.id))
    if (word && !fixed) {
      const next = Math.min(pages - 1, Math.max(0, Math.floor((word.range.getBoundingClientRect().left + page * geometry.current.step) / geometry.current.step)))
      emitPosition(next, word.offset); setPage(next)
    }
  }, [active, busy, book.sentences, chapter, fixed, spine, pages, page, emitPosition])
  const currentEntry = [...navigation].reverse().find(entry => {
    if (entry.chapter !== chapter) return entry.chapter < chapter
    const doc = iframe.current?.contentDocument
    const destination = entry.elementId ? doc?.getElementById(entry.elementId) : entry.sentenceId ? ranges.current.find(word => String(word.sentenceId) === String(entry.sentenceId))?.range : null
    return !destination || Math.floor((destination.getBoundingClientRect().left - doc.body.getBoundingClientRect().left) / geometry.current.step) <= page
  })
  return <section className="extensive-reader source-reader" aria-label="泛读模式">
    <div className="extensive-running-head"><Button type="text" aria-label="目录" icon={<UnorderedListOutlined />} onClick={() => setContents(true)}>目录</Button><span>{currentEntry?.title || title}</span><span className="extensive-edition">EPUB 原版</span></div>
    <div className="extensive-page-stage">
      <Button className="extensive-turn" type="text" aria-label="上一页" icon={<LeftOutlined />} disabled={busy || (!chapter && !page)} onClick={() => go(-1)} />
      <div ref={paper} className={`extensive-paper is-source ${fixed ? 'is-fixed' : ''}`}>
        <div className="epub-source-host" ref={host}>{html && <iframe key={chapter + ':' + retry} ref={iframe} title="EPUB 原文书页" sandbox="allow-same-origin" srcDoc={html} onLoad={prepare} style={{ visibility: busy || error ? 'hidden' : 'visible' }} />}</div>
        {busy && <div className="extensive-loading"><Spin tip="正在加载原版书页…"><div /></Spin></div>}
        {error && <div className="extensive-pdf-error"><Alert type="error" showIcon message="原版书页加载失败" description={error} action={<Button onClick={() => { setHtml(''); setRetry(n => n + 1) }}>重新加载</Button>} /></div>}
      </div>
      <Button className="extensive-turn" type="text" aria-label="下一页" icon={<RightOutlined />} disabled={busy || (chapter === spine.length - 1 && page === pages - 1)} onClick={() => go(1)} />
    </div>
    <footer className="extensive-navigation">
      <div className="extensive-page-info"><span>{fixed ? `原文第 ${chapter + 1} / ${spine.length} 页` : `章节 ${currentEntry ? navigation.indexOf(currentEntry) + 1 : '—'} / ${navigation.length}`}</span><div><span>当前页</span><span className="extensive-page-number"><InputNumber style={{ '--page-digits': String(fixed ? chapter + 1 : page + 1).length }} aria-label="跳转页码" min={1} max={fixed ? spine.length : pages} value={fixed ? chapter + 1 : page + 1} controls={false} disabled={busy} onChange={value => { if (!value) return; if (fixed) navigate({ chapter: value - 1 }); else { if (value - 1 !== page) turn(value - 1 > page ? 1 : -1); emitPosition(value - 1); setPage(value - 1) } }} /><span>/{fixed ? spine.length : pages}页</span></span></div><span>← → 翻页 · 点击单词查词</span></div>
      <div className="extensive-footnote"><span>{fixed ? '原始画布等比展示' : '保留原书样式 · 屏幕页随窗口变化'}</span><span role="status">{positionSave?.state === 'error' ? <Button size="small" danger type="link" title={positionSave.error} onClick={onRetryPosition}>重试保存进度</Button> : positionSave?.state === 'saved' ? '进度已保存' : '正在保存进度…'}</span><span>RynEnglish</span></div>
    </footer>
    <Drawer className="extensive-contents" title="原书目录" placement="left" width={340} open={contents} onClose={() => setContents(false)}><p>{title}</p><nav aria-label="章节目录">{navigation.map((entry, index) => <button key={index} aria-current={entry === currentEntry ? 'location' : undefined} style={{ paddingLeft: 8 + entry.depth * 16 }} disabled={busy} onClick={() => navigate(entry)}><small>{index + 1}</small><span>{entry.title}</span></button>)}</nav></Drawer>
  </section>
}
