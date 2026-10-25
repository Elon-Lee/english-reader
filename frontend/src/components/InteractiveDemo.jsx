import React, { useState } from 'react'
import { Tooltip } from 'antd'

export default function InteractiveDemo() {
  const [clickedWords, setClickedWords] = useState(new Set())
  const [showHint, setShowHint] = useState(true)
  const [openTooltip, setOpenTooltip] = useState(null)

  const handleWordClick = (event, word) => {
    event.preventDefault()
    event.stopPropagation()
    setClickedWords(prev => new Set([...prev, word]))
    setOpenTooltip(openTooltip === word ? null : word)
    if (showHint) setShowHint(false)
  }

  const WordTooltip = ({ word, meaning, pos, children }) => (
    <Tooltip
      title={
        <div className="demo-meaning-card">
          <div className="demo-meaning-header">
            <b>{word}</b>
            <span className="demo-pos">{pos}</span>
          </div>
          <p className="demo-meaning-text">{meaning}</p>
        </div>
      }
      open={openTooltip === word}
      onOpenChange={(visible) => {
        if (!visible) setOpenTooltip(null)
      }}
      trigger="click"
      placement="top"
      overlayClassName="demo-word-tooltip"
    >
      <span
        className={`demo-word ${clickedWords.has(word) ? 'clicked' : ''}`}
        onClick={(e) => handleWordClick(e, word)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            handleWordClick(e, word)
          }
        }}
      >
        {children}
      </span>
    </Tooltip>
  )

  return (
    <section className="public-demo-interactive" id="how-it-works">
      <div className="demo-content">
        <h2>看一句真实的学习过程</h2>
        <div className="demo-stage">
          <div className="demo-sentence">
            <p>
              The discovery was{' '}
              <WordTooltip word="unexpected" meaning="意外的，令人惊讶的" pos="adj.">
                unexpected
              </WordTooltip>
              , but it{' '}
              <WordTooltip word="transformed" meaning="彻底改变，使转变" pos="v.">
                transformed
              </WordTooltip>
              {' '}our understanding.
            </p>
          </div>
          {showHint && (
            <p className="demo-hint">
              <span className="demo-hint-icon">💡</span>
              点击橙色单词试试
            </p>
          )}
        </div>
        <p className="demo-footnote">
          这只是一句。在拾页，每篇文章、每个视频都能这样逐句理解。
        </p>
      </div>
    </section>
  )
}
