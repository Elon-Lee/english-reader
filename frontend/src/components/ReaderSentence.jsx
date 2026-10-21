import React,{memo,useCallback} from 'react'
import {Button,Typography} from 'antd'

// Only the old/new sentence and old/new word repaint on playback updates.
// actions is a stable ref whose current handlers are refreshed after each commit.
export default memo(function ReaderSentence({sentence,index,active,spoken,selected,expanded,showTranslation,lookupIndex,annotations,hasSource,trial,actions,sentenceRefs}) {
  const bind=useCallback(node=>{sentenceRefs.current[index]=node},[sentenceRefs,index])
  const s=sentence
  return <article ref={bind} aria-label={'第 '+(index+1)+' 句'} className={'reader-sentence '+(active?'active ':'')+(selected?'learning-selected':'')} onClick={()=>actions.current.select(s,index)}>
    <small>{index+1}</small>
    <p>{s.words?.length?s.words.map((w,n)=>{
      const word=String(w?.text||w?.word||w?.form||''),key=s.id+'-'+n
      return <button key={key} aria-haspopup="dialog" aria-expanded={lookupIndex===n} className={'reader-word '+(n===spoken?'spoken ':'')+(annotations?.has(n)?'annotated':'')} onMouseEnter={e=>{if(!trial)actions.current.hoverStart(key,word,e.currentTarget)}} onMouseLeave={()=>actions.current.hoverEnd(key)} onBlur={()=>actions.current.hoverEnd(key)} onClick={e=>{e.stopPropagation();actions.current.lookup(s,n,word,e.currentTarget)}}>{word}</button>
    }):s.text}</p>
    <div className="reader-sentence-inline-actions">
      <Typography.Text className="reader-sentence-position">{active?(hasSource?'播放位置':'阅读位置'):selected?'正在查看':''}</Typography.Text>
      <Button className="reader-sentence-action" onClick={e=>{e.stopPropagation();actions.current.practice(s.id,e.currentTarget)}}>练这一句</Button>
      <Button className="reader-sentence-action" onClick={e=>{e.stopPropagation();actions.current.analyze(s,e.currentTarget)}}>语法</Button>
      {showTranslation&&<Button className={'reader-sentence-action reader-translation-action '+(expanded?'is-expanded':'')} aria-expanded={expanded} onClick={e=>{e.stopPropagation();actions.current.translate(s)}}>{expanded?'收起翻译':'翻译'}</Button>}
    </div>
    {expanded&&showTranslation&&<div className="reader-sentence-translation" onClick={e=>e.stopPropagation()}>{s.translation}</div>}
  </article>
})
