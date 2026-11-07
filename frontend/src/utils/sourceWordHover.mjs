// Highlight DOM Ranges without wrapping or changing the original book markup.
export function sourceWordAt(words, x, y) {
  return words.find(word => [...word.range.getClientRects()].some(rect => x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom))
}

export function installSourceWordHover(root, words) {
  const doc = root.ownerDocument, view = doc.defaultView
  const style = doc.createElement('style')
  style.textContent = '::highlight(reader-word-hover){background-color:rgba(126,166,106,.32);text-decoration:underline;text-decoration-color:#527641}'
  doc.head.append(style)
  let hovered, node, previousCursor, frame, pointer
  const clear = () => {
    if (node) node.style.cursor = previousCursor
    node = null; hovered = null
    view.CSS?.highlights?.delete('reader-word-hover')
  }
  const move = event => {
    pointer = { x: event.clientX, y: event.clientY, node: event.target }
    if (frame) return
    frame = view.requestAnimationFrame(() => {
      frame = null
      const word = sourceWordAt(words, pointer.x, pointer.y)
      if (word === hovered && pointer.node === node) return
      clear()
      if (!word) return
      hovered = word; node = pointer.node; previousCursor = node.style.cursor
      node.style.cursor = 'pointer'
      if (view.Highlight && view.CSS?.highlights) view.CSS.highlights.set('reader-word-hover', new view.Highlight(word.range))
    })
  }
  const leave = () => { view.cancelAnimationFrame(frame); frame = null; clear() }
  root.addEventListener('pointermove', move)
  root.addEventListener('pointerleave', leave)
  root.addEventListener('pointerdown', leave)
  return () => {
    leave(); style.remove()
    root.removeEventListener('pointermove', move); root.removeEventListener('pointerleave', leave); root.removeEventListener('pointerdown', leave)
  }
}
