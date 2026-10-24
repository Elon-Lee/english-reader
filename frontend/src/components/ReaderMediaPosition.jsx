import React, { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { DragOutlined } from '@ant-design/icons'

export const boundedMediaPosition = value => Math.max(0, Math.min(1, Number(value) || 0))

// Store a proportion of the available vertical space, so the position survives
// changes in window size and media aspect ratio without leaving the workspace.
export default function ReaderMediaPosition({ value = 0, enabled, onSave }) {
  const handleRef = useRef(null)
  const drag = useRef(null)
  const positionRef = useRef(boundedMediaPosition(value))
  const [position, setPosition] = useState(positionRef.current)
  const [travel, setTravel] = useState(0)
  const [dragging, setDragging] = useState(false)
  const [saving, setSaving] = useState(false)
  const [keyboardDirty, setKeyboardDirty] = useState(false)
  const updatePosition = next => { positionRef.current = boundedMediaPosition(next); setPosition(positionRef.current) }

  useEffect(() => { if (!drag.current) updatePosition(value) }, [value])
  useLayoutEffect(() => {
    const panel = handleRef.current?.closest('.reader-media-panel'), row = panel?.parentElement
    if (!panel || !row) return
    const measure = () => {
      const stacked = getComputedStyle(panel).gridRowStart === '1'
      const style = getComputedStyle(panel)
      setTravel(enabled && innerWidth > 900 && !stacked ? Math.max(0, row.clientHeight - panel.offsetHeight - (parseFloat(style.marginTop) || 0) - (parseFloat(style.marginBottom) || 0)) : 0)
    }
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(panel); observer.observe(row)
    window.addEventListener('resize', measure)
    return () => { observer.disconnect(); window.removeEventListener('resize', measure) }
  }, [enabled])
  useLayoutEffect(() => {
    const panel = handleRef.current?.closest('.reader-media-panel')
    panel?.style.setProperty('--reader-media-offset', `${enabled ? position * travel : 0}px`)
    return () => panel?.style.removeProperty('--reader-media-offset')
  }, [enabled, position, travel])

  const commit = async () => {
    const next = positionRef.current
    if (Math.abs(next - boundedMediaPosition(value)) < .001) return
    setSaving(true)
    try { if (await onSave(next) === false) updatePosition(value) }
    catch { updatePosition(value) }
    finally { setSaving(false) }
  }
  const cancel = () => { if (!drag.current) return; drag.current = null; setDragging(false); updatePosition(value) }
  const finish = event => {
    if (drag.current?.id !== event.pointerId) return
    drag.current = null; setDragging(false)
    event.currentTarget.releasePointerCapture(event.pointerId)
    commit()
  }

  return <button ref={handleRef} type="button" className={`reader-media-drag-handle ${dragging ? 'is-dragging' : ''}`} disabled={!enabled || travel < 1 || saving}
    aria-label="上下拖动媒体位置，也可使用上下方向键调整" title={saving ? '正在保存位置…' : '上下拖动；方向键微调，Home / End 移至顶部 / 底部'}
    onPointerDown={event => { if (event.button !== 0 || !travel || saving) return; event.preventDefault(); event.currentTarget.focus(); drag.current = { id: event.pointerId, y: event.clientY, start: positionRef.current }; event.currentTarget.setPointerCapture(event.pointerId); setDragging(true) }}
    onPointerMove={event => { const state = drag.current; if (state?.id === event.pointerId) updatePosition(state.start + (event.clientY - state.y) / travel) }}
    onPointerUp={finish} onPointerCancel={cancel} onLostPointerCapture={cancel}
    onKeyDown={event => { if (!['ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key) || !travel) return; event.preventDefault(); event.stopPropagation(); updatePosition(event.key === 'Home' ? 0 : event.key === 'End' ? 1 : positionRef.current + (event.key === 'ArrowUp' ? -10 : 10) / travel); setKeyboardDirty(true) }}
    onKeyUp={event => { if (keyboardDirty && ['ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)) { setKeyboardDirty(false); commit() } }}
    onBlur={() => { if (keyboardDirty) { setKeyboardDirty(false); commit() } }}>
    <DragOutlined /><span>{saving ? '正在保存位置…' : dragging ? `媒体位置 ${Math.round(position * 100)}%` : '上下拖动调整位置'}</span>
  </button>
}
