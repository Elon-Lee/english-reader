import React, { useEffect, useRef, useState } from 'react'
import { Alert, Button, Popover } from 'antd'
import { CloseOutlined } from '@ant-design/icons'
import ReaderWordPanel from './ReaderWordPanel'

// Public preview transcribed from the supplied reader screenshots, not account data.
const words = {
  correct: {
    brief: '正确；改正；对', phonetic: '/kəˈrekt/',
    sentence: "Don't stop to correct yourself.",
    meaning: 'correct 在此上下文中，correct 指的是在说话或写作过程中发现并修改错误的行为。它强调的是即时性的自我修正，而不是事后才进行修改。 correct（纠正）',
  },
  language: {
    brief: '语言；语；言语', phonetic: '/ˈlæŋɡwɪdʒ/',
    sentence: 'Just keep going and let the language flow.',
    meaning: 'language（语言）：在此上下文中，“language”指代的是说话或写作的特定方式，强调的是自然、流畅的表达，而非语法上的完美。它鼓励使用者不必拘泥于纠错，而是让表达自然流淌。',
  },
}

export default function InteractiveDemo({ authenticated = false }) {
  const [hoveredWord, setHoveredWord] = useState(null)
  const [activeWord, setActiveWord] = useState(null)
  const [expanded, setExpanded] = useState(false)
  const [visited, setVisited] = useState(new Set())
  const [speaking, setSpeaking] = useState(false)
  const [audioError, setAudioError] = useState('')
  const [cardLayout, setCardLayout] = useState({ placement: 'bottom', height: 600 })
  const triggerRefs = useRef({})
  const audioRef = useRef(null)
  const audioUrl = useRef(null)
  const audioRequest = useRef(0)

  const stopAudio = () => {
    audioRequest.current += 1
    audioRef.current?.pause()
    audioRef.current = null
    if (audioUrl.current) URL.revokeObjectURL(audioUrl.current)
    audioUrl.current = null
  }
  const close = () => {
    triggerRefs.current[activeWord]?.focus()
    setActiveWord(null)
    setHoveredWord(null)
    setExpanded(false)
    setAudioError('')
    stopAudio()
    setSpeaking(false)
  }

  useEffect(() => {
    const onEscape = event => { if (event.key === 'Escape') close() }
    const onOutside = event => {
      if (!event.target.closest('.demo-reader-popover, .demo-word')) {
        setActiveWord(null)
        setHoveredWord(null)
        setExpanded(false)
        setAudioError('')
        stopAudio()
        setSpeaking(false)
      }
    }
    document.addEventListener('keydown', onEscape)
    document.addEventListener('pointerdown', onOutside)
    return () => {
      document.removeEventListener('keydown', onEscape)
      document.removeEventListener('pointerdown', onOutside)
    }
  }, [activeWord])
  useEffect(() => () => stopAudio(), [])

  const speak = async word => {
    if (!authenticated) { setAudioError('登录后可播放单词发音。'); return }
    stopAudio()
    const requestId = audioRequest.current
    setSpeaking(true)
    setAudioError('')
    try {
      const response = await fetch(`/api/word-tts?word=${encodeURIComponent(word)}`, { credentials: 'include' })
      if (!response.ok) throw new Error('发音暂不可用，请重试。')
      const blob = await response.blob()
      if (requestId !== audioRequest.current) return
      audioUrl.current = URL.createObjectURL(blob)
      const audio = new Audio(audioUrl.current)
      audioRef.current = audio
      audio.onended = () => setSpeaking(false)
      audio.onerror = () => { setSpeaking(false); setAudioError('发音播放失败，请重试。') }
      await audio.play()
    } catch (error) {
      if (requestId === audioRequest.current) { setAudioError(error.message); setSpeaking(false) }
    }
  }

  const enterReader = () => { window.location.href = authenticated ? '/app?screen=catalog' : '/login' }
  const renderWord = word => {
    const data = words[word]
    const detailed = activeWord === word
    return <Popover
      key={word} trigger={['hover', 'focus']} placement={detailed ? cardLayout.placement : 'bottom'}
      autoAdjustOverflow={{ adjustX: 1, adjustY: 0, shiftX: true, shiftY: true }}
      mouseEnterDelay={0.15} mouseLeaveDelay={0.15}
      open={detailed || (!activeWord && hoveredWord === word)}
      onOpenChange={open => setHoveredWord(open ? word : null)}
      overlayClassName={`demo-reader-popover ${detailed ? 'is-detail' : 'is-brief'}`}
      content={detailed ? <div className="demo-reader-detail" style={{ maxHeight: cardLayout.height }} role="region" aria-label={`${word} 本句查词`}>
        <Button type="text" className="demo-close" aria-label="关闭单词释义" icon={<CloseOutlined />} onClick={close} />
        <ReaderWordPanel compact
          info={{ word, context: { phonetic: data.phonetic, meaning: data.meaning } }}
          sentence={{ text: data.sentence }} onSpeak={() => speak(word)} speaking={speaking}
          onSave={enterReader} onPractice={enterReader}
          onExpand={() => setExpanded(value => !value)} onLocate={close}
        />
        {expanded && <div className="demo-expanded-meaning"><b>词典简义</b><p>{data.brief}</p><a href={authenticated ? '/app?screen=catalog' : '/login'}>进入阅读器查看完整词典与更多用法 →</a></div>}
        {audioError && <Alert type="info" message={<>{audioError}{!authenticated && <a href="/login">去登录 →</a>}</>} />}
        <p className="demo-action-note">示例预览 · 收藏与练习请进入学习空间，选择原文。</p>
      </div> : <div className="demo-reader-brief" role="tooltip">
        <div><b>{word}</b><span>简明释义</span></div>
        <p>{data.brief}</p><footer>点击单词查看详解</footer>
      </div>}
    >
      <button type="button" ref={node => { triggerRefs.current[word] = node }}
        className={`demo-word ${visited.has(word) ? 'clicked' : ''}`}
        aria-label={`查看 ${word} 的释义`} aria-expanded={detailed}
        onClick={event => {
          if (detailed) { close(); return }
          const rect = event.currentTarget.getBoundingClientRect()
          const below = window.innerHeight - rect.bottom - 24
          const above = rect.top - 96
          const placement = below >= 320 || below >= above ? 'bottom' : 'top'
          setCardLayout({ placement, height: Math.max(160, Math.min(680, placement === 'bottom' ? below : above)) })
          stopAudio()
          setSpeaking(false)
          setAudioError('')
          setExpanded(false)
          setActiveWord(word)
          setHoveredWord(null)
          setVisited(previous => new Set([...previous, word]))
        }}
      >{word}</button>
    </Popover>
  }

  return <section className="public-demo-interactive" id="how-it-works">
    <div className="demo-content">
      <h2>看一句真实的学习过程</h2>
      <div className="demo-stage">
        <div className="demo-sentence"><p>Don't stop to {renderWord('correct')} yourself.<br />Just keep going and let the {renderWord('language')} flow.</p></div>
        <p className="demo-hint">悬停看简义，点击看本句含义 · 试试 correct 和 language</p>
      </div>
      <p className="demo-footnote">这只是一句。在拾页，每篇文章、每个视频都能这样逐句理解。</p>
    </div>
  </section>
}
