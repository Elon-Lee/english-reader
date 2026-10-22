import React,{useLayoutEffect,useRef,useState} from 'react'
import {PauseOutlined} from '@ant-design/icons'

export default function ReaderHoverCard({lookup}) {
  const card=useRef(null),[position,setPosition]=useState(null)
  useLayoutEffect(()=>{
    const place=()=>{
      const {width,height}=card.current.getBoundingClientRect(),anchor=lookup.anchor
      const left=Math.max(12,Math.min(innerWidth-width-12,anchor.left+anchor.width/2-width/2))
      const above=anchor.top-height-10
      const top=above>=84?above:Math.min(innerHeight-height-12,anchor.bottom+10)
      setPosition({left,top:Math.max(12,top)})
    }
    place()
    addEventListener('resize',place)
    return()=>removeEventListener('resize',place)
  },[lookup])
  return <div ref={card} className="reader-word-hover reader-hover-card" style={position||{visibility:'hidden'}} role="tooltip" aria-busy={lookup.loading}>
    <div className="reader-hover-heading"><b>{lookup.word}</b><small>简明释义</small></div>
    <div className={'reader-hover-meanings '+(lookup.loading||lookup.error?'is-status':'')}><p>{lookup.entries.join('；')}</p></div>
    <div className="reader-hover-footer"><span>点击单词查看详解</span>{lookup.paused&&<span className="reader-hover-paused"><PauseOutlined aria-hidden="true"/>原音已暂停</span>}</div>
  </div>
}
