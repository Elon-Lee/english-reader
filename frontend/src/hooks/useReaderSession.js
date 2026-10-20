import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { postJson } from '../api/client'
import { createReaderDraftStore } from '../utils/readerLearning.mjs'

export default function useReaderSession({ ownerId, bookId, kind, enabled, currentId, mediaRef, paused, hasUnsavedEditor }) {
  const studyClock = useRef({seconds:0,lastAction:Date.now(),visited:new Set()})
  const counters = useRef({lookups:0,reviews:0,shadowAttempts:0})
  const newWordIds = useRef(new Set())
  const finishAttempt = useRef(null)
  const saved = useRef(false), saving = useRef(false), initialized = useRef(null)
  const latest = useRef({currentId,paused,hasUnsavedEditor}); latest.current={currentId,paused,hasUnsavedEditor}
  const [finishing,setFinishing] = useState(false),[completed,setCompleted] = useState(false)
  const [seconds,setSeconds] = useState(0),[restored,setRestored] = useState(false),[saveError,setSaveError] = useState(''),[draftUnavailable,setDraftUnavailable] = useState(false)
  const store = useMemo(() => { let storage; try { storage=window.sessionStorage } catch {} return createReaderDraftStore(storage,ownerId,bookId,kind) },[ownerId,bookId,kind])
  const dirty = useCallback(() => !saved.current && (studyClock.current.seconds >= 1 || newWordIds.current.size > 0 || Object.values(counters.current).some(value=>value>0) || !!finishAttempt.current),[])
  const checkpoint = useCallback(() => {
    if (!enabled || !ownerId || initialized.current !== store || saved.current) return
    if (!dirty()) return
    if (!store.write({seconds:studyClock.current.seconds,visited:[...studyClock.current.visited],counters:counters.current,newWordIds:[...newWordIds.current],pending:finishAttempt.current,lastSentenceId:latest.current.currentId})) setDraftUnavailable(true)
  },[store,enabled,ownerId,dirty])
  useEffect(() => {
    if (!enabled || !ownerId) return
    if (initialized.current !== store) {
      studyClock.current={seconds:0,lastAction:Date.now(),visited:new Set()}
      counters.current={lookups:0,reviews:0,shadowAttempts:0};newWordIds.current=new Set()
      finishAttempt.current=null;saved.current=false;saving.current=false
      setSeconds(0);setRestored(false);setCompleted(false);setFinishing(false);setSaveError('');setDraftUnavailable(false)
      const draft = store.read()
      if (draft) {
        studyClock.current={seconds:draft.seconds,lastAction:Date.now(),visited:new Set(draft.visited)}
        counters.current={lookups:0,reviews:0,shadowAttempts:0,...draft.counters}
        newWordIds.current=new Set(draft.newWordIds);finishAttempt.current=draft.pending||null
        setSeconds(Math.floor(draft.seconds));setRestored(true)
        if(draft.pending)setSaveError('已恢复上次未确认的保存，请重试保存。重试不会重复计入。')
      }
      initialized.current=store
    }
    const touch=()=>{studyClock.current.lastAction=Date.now()}
    let last=performance.now()
    const timer=setInterval(()=>{
      const now=performance.now(),elapsed=Math.min(2,(now-last)/1000);last=now
      if(!saved.current&&!finishAttempt.current&&!latest.current.paused&&document.visibilityState==='visible'&&document.hasFocus()&&((mediaRef.current&&!mediaRef.current.paused)||Date.now()-studyClock.current.lastAction<60000)) {
        studyClock.current.seconds+=elapsed;setSeconds(Math.floor(studyClock.current.seconds))
      }
      checkpoint()
    },1000)
    const beforeUnload=event=>{checkpoint();if(dirty()||latest.current.hasUnsavedEditor){event.preventDefault();event.returnValue=''}}
    const hidden=()=>{if(document.visibilityState==='hidden')checkpoint()}
    addEventListener('pointerdown',touch);addEventListener('keydown',touch);addEventListener('wheel',touch,{passive:true})
    addEventListener('beforeunload',beforeUnload);addEventListener('pagehide',checkpoint);document.addEventListener('visibilitychange',hidden)
    return()=>{checkpoint();clearInterval(timer);removeEventListener('pointerdown',touch);removeEventListener('keydown',touch);removeEventListener('wheel',touch);removeEventListener('beforeunload',beforeUnload);removeEventListener('pagehide',checkpoint);document.removeEventListener('visibilitychange',hidden)}
  },[enabled,ownerId,store,checkpoint,dirty,mediaRef])
  const visit = useCallback(id=>{if(enabled&&!saved.current&&!finishAttempt.current&&id!==undefined&&id!==null){studyClock.current.visited.add(String(id));checkpoint()}},[enabled,checkpoint])
  useEffect(()=>{if(currentId!==undefined)visit(currentId)},[currentId,visit])
  const reset = () => {
    store.clear();saved.current=false;finishAttempt.current=null
    studyClock.current={seconds:0,lastAction:Date.now(),visited:new Set(currentId!==undefined&&currentId!==null?[String(currentId)]:[])}
    counters.current={lookups:0,reviews:0,shadowAttempts:0};newWordIds.current=new Set()
    setSeconds(0);setCompleted(false);setSaveError('');setRestored(false)
  }
  const discard = () => {saved.current=true;store.clear();setCompleted(true)}
  const save = async () => {
    if(!enabled||!ownerId||initialized.current!==store||saving.current||saved.current)return null
    mediaRef.current?.pause();saving.current=true;setFinishing(true);setSaveError('')
    if(!finishAttempt.current)finishAttempt.current={bookId,readingSeconds:Math.floor(studyClock.current.seconds),sentences:studyClock.current.visited.size,lookups:counters.current.lookups,reviews:counters.current.reviews,shadowAttempts:counters.current.shadowAttempts,sessions:1,lastSentenceId:latest.current.currentId,idempotencyKey:'modern-reader-'+crypto.randomUUID()}
    checkpoint()
    try {
      await postJson('/api/workspace/activity',finishAttempt.current)
      if(initialized.current!==store){store.clear();return null}
      const result={...finishAttempt.current,newWordIds:[...newWordIds.current]}
      saved.current=true;store.clear();setCompleted(true);setRestored(false)
      return result
    } catch(error) {if(initialized.current===store){setSaveError((error.message||'保存失败')+'；请重试保存，本次记录不会重复计入。');checkpoint()}return null}
    finally {if(initialized.current===store){saving.current=false;setFinishing(false)}}
  }
  return {studyClock,counters,newWordIds,finishAttempt,finishing,completed,seconds,restored,saveError,draftUnavailable,dirty,checkpoint,visit,reset,discard,save}
}
