import { useCallback, useEffect, useRef } from 'react'

export default function useBookPageTurn() {
  const paper = useRef(null), pending = useRef(null)
  const turn = useCallback(direction => {
    const node = paper.current
    pending.current?.cancel()
    if (!node || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    // A paper leaf rotates around the binding while its moving shadow crosses the page.
    const leaf = document.createElement('div')
    leaf.className = `book-turn-leaf ${direction < 0 ? 'is-backward' : ''}`
    leaf.setAttribute('aria-hidden', 'true')
    node.classList.add('book-page-turning')
    node.append(leaf)
    const animation = leaf.animate([
      { transform: 'perspective(1800px) rotateY(0deg)', opacity: .96 },
      { transform: `perspective(1800px) rotateY(${direction < 0 ? 65 : -65}deg)`, opacity: .8, offset: .55 },
      { transform: `perspective(1800px) rotateY(${direction < 0 ? 115 : -115}deg)`, opacity: 0 },
    ], { duration: 900, easing: 'cubic-bezier(.22,.55,.3,1)', fill: 'forwards' })
    const cleanup = () => { leaf.remove(); if (pending.current === animation) { pending.current = null; node.classList.remove('book-page-turning') } }
    animation.onfinish = cleanup; animation.oncancel = cleanup
    pending.current = animation
  }, [])
  useEffect(() => () => pending.current?.cancel(), [])
  return [paper, turn]
}
