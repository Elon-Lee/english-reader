import React, { useEffect, useRef, useState } from 'react'
import { installSourceWordHover } from '../utils/sourceWordHover.mjs'
import { Alert, Button, Space, Spin } from 'antd'
import { getDocument, GlobalWorkerOptions, TextLayer, version } from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import 'pdfjs-dist/web/pdf_viewer.css'
import { sourceWordRanges } from '../utils/sourceTextRanges.mjs'

GlobalWorkerOptions.workerSrc = `${workerUrl}${workerUrl.includes('?') ? '&' : '?'}v=${version}`

export default function PdfReadingPage({ url, page, onLoaded, book, actions }) {
  const [document, setDocument] = useState(null), [error, setError] = useState(''), [busy, setBusy] = useState(true), [retry, setRetry] = useState(0), [zoom, setZoom] = useState(1), [size, setSize] = useState({ width: 1, height: 1 })
  const host = useRef(null), canvas = useRef(null), text = useRef(null), loaded = useRef(onLoaded)
  const words = useRef([]), currentActions = useRef(actions)
  currentActions.current = actions
  loaded.current = onLoaded
  useEffect(() => {
    setBusy(true); setError(''); setDocument(null)
    const task = getDocument({ url, withCredentials: true, isEvalSupported: false,
      cMapUrl: `/pdf-assets/${version}/cmaps/`, cMapPacked: true,
      standardFontDataUrl: `/pdf-assets/${version}/standard_fonts/`, wasmUrl: `/pdf-assets/${version}/wasm/` })
    let disposed = false
    task.promise.then(pdf => { if (!disposed) { setDocument(pdf); loaded.current(pdf.numPages) } }).catch(e => { if (!disposed) { setBusy(false); setError(e.message || 'PDF 加载失败') } })
    return () => { disposed = true; task.destroy() }
  }, [url, retry])
  useEffect(() => {
    if (!host.current) return
    const observer = new ResizeObserver(([entry]) => setSize({ width: entry.contentRect.width, height: entry.contentRect.height }))
    observer.observe(host.current)
    return () => observer.disconnect()
  }, [])
  useEffect(() => {
    if (!document || !canvas.current || size.width <= 1) return
    let disposed = false, render, layer, clearHover
    setBusy(true); setError('')
    const paint = async () => {
      const pdfPage = await document.getPage(Math.min(document.numPages, Math.max(1, page)))
      if (disposed) return
      const original = pdfPage.getViewport({ scale: 1 })
      const scale = Math.min((size.width - 24) / original.width, (size.height - 24) / original.height) * zoom
      const viewport = pdfPage.getViewport({ scale: Math.max(.1, scale) }), ratio = Math.min(window.devicePixelRatio || 1, 2)
      const node = canvas.current
      node.width = Math.floor(viewport.width * ratio); node.height = Math.floor(viewport.height * ratio)
      node.style.width = `${viewport.width}px`; node.style.height = `${viewport.height}px`
      text.current.replaceChildren()
      text.current.parentElement.style.setProperty('--scale-factor', viewport.scale)
      text.current.parentElement.style.width = `${viewport.width}px`
      text.current.parentElement.style.height = `${viewport.height}px`
      render = pdfPage.render({ canvasContext: node.getContext('2d'), viewport, transform: ratio === 1 ? null : [ratio, 0, 0, ratio, 0, 0] })
      await render.promise
      if (disposed) return
      const textContent = await pdfPage.getTextContent()
      if (disposed) return
      layer = new TextLayer({ textContentSource: textContent, container: text.current, viewport })
      await layer.render()
      if (disposed) return
      const doc = text.current.ownerDocument
      words.current = sourceWordRanges({ body: text.current, createRange: () => doc.createRange() }, undefined,
        (book?.readingDocument?.blocks || []).filter(block => Number(block.page) === page && !block.section))
      clearHover = installSourceWordHover(text.current, words.current)
      if (!disposed) setBusy(false)
    }
    paint().catch(e => { if (!disposed && e.name !== 'RenderingCancelledException') { setBusy(false); setError(e.message || '原文页面渲染失败') } })
    return () => { disposed = true; clearHover?.(); render?.cancel(); layer?.cancel() }
  }, [document, page, size, zoom, retry, book])
  const lookup = event => {
    const word = words.current.find(word => [...word.range.getClientRects()].some(r => event.clientX >= r.left && event.clientX <= r.right && event.clientY >= r.top && event.clientY <= r.bottom))
    const sentence = word && book?.sentences.find(sentence => String(sentence.id) === String(word.sentenceId))
    if (sentence) currentActions.current?.current.lookup(sentence, word.wordIndex, word.text, { getBoundingClientRect: () => word.range.getBoundingClientRect() })
  }
  return <div className="extensive-pdf">
    <div className="extensive-pdf-zoom"><Space size={4}><Button size="small" type="text" disabled={zoom <= 1} onClick={() => setZoom(value => Math.max(1, value - .25))} aria-label="缩小原文">−</Button><Button size="small" type="text" onClick={() => setZoom(1)}>{zoom === 1 ? '适合整页' : `${Math.round(zoom * 100)}%`}</Button><Button size="small" type="text" disabled={zoom >= 2.5} onClick={() => setZoom(value => Math.min(2.5, value + .25))} aria-label="放大原文">＋</Button></Space></div>
    <div className="extensive-pdf-host" ref={host}>
      <div className="extensive-pdf-page" aria-label={`PDF 原文第 ${page} 页`} style={{ visibility: busy || error ? 'hidden' : 'visible' }}><canvas ref={canvas} /><div ref={text} className="textLayer" onClick={lookup} /></div>
    </div>
    {busy && <div className="extensive-loading"><Spin tip="正在加载原文页面…"><div /></Spin></div>}
    {error && <div className="extensive-pdf-error"><Alert type="error" showIcon message="原文页面加载失败" description={error} action={<Button onClick={() => setRetry(value => value + 1)}>重新加载</Button>} /></div>}
  </div>
}
