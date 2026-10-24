import React,{useCallback,useEffect,useLayoutEffect,useMemo,useRef,useState}from'react'
import {flushSync} from 'react-dom'
import{Alert,Button,Card,Empty,Form,Modal,Select,Slider,Space,Spin,Switch,Tabs,Tag,Tooltip,Typography}from'antd'
import{AimOutlined,ArrowLeftOutlined,AudioOutlined,CaretRightFilled,CloseOutlined,ControlOutlined,EyeOutlined,FastBackwardOutlined,FastForwardOutlined,FontSizeOutlined,MenuFoldOutlined,MenuUnfoldOutlined,PauseOutlined,PoweroffOutlined,PlayCircleFilled,PushpinOutlined,ReloadOutlined,SaveOutlined,SettingOutlined}from'@ant-design/icons'
import{deleteJson,getJson,postJson}from'../api/client'
import { handleMembershipLimit } from '../api/membershipLimit'
import{DEFAULT_PREFERENCES,KEY_OPTIONS,keyboardKey}from'../config/preferences'
import PageSkeleton from'../components/PageSkeleton'
import ReaderWordPanel from '../components/ReaderWordPanel'
import ReaderSentence from '../components/ReaderSentence'
import ReaderHoverCard from '../components/ReaderHoverCard'
import ReaderFlowControl from '../components/ReaderFlowControl'
import ReaderMediaPosition from '../components/ReaderMediaPosition'
import {buildReaderTimeline,timelineSentence,timelineWord,sentenceStart,sentenceEnd,crossedSentenceEnd,playReaderMedia} from '../utils/readerTiming.mjs'
import useReaderSession from '../hooks/useReaderSession'
import { createReaderRequests, readerWordMeaning } from '../utils/readerLearning.mjs'
import { learningDuration, openReview } from '../utils/presentation.mjs'
import { readerAppearance, readerScrollTop, sentenceIndex, sentencePlaybackRange, mediaCompletionProgress } from '../utils/readerPresentation.mjs'
import { createWordAudioCache, createWordAudioOutput, playWordFromStart } from '../utils/wordPronunciation.mjs'
const{Paragraph,Text,Title}=Typography
const clock=value=>{const n=Math.max(0,Number(value)||0);return`${String(Math.floor(n/60)).padStart(2,'0')}:${String(Math.floor(n%60)).padStart(2,'0')}`}
const startOf=sentenceStart
const endOf=sentenceEnd
function mediaOptions(book){const assets=book?.mediaAssets||[],all=assets.flatMap(a=>[{...a,name:a.name||a.kind||'original'},...(a.variants||[]).map(v=>({...v,assetId:a.id}))]),videoAssets=assets.filter(a=>String(a.contentType).startsWith('video/')||(a.variants||[]).some(v=>String(v.contentType).startsWith('video/'))),canonicalVideoAssets=videoAssets.some(a=>a.kind!=='generated')?videoAssets.filter(a=>a.kind!=='generated'):videoAssets,videos=canonicalVideoAssets.flatMap(a=>{const variants=(a.variants||[]).filter(v=>String(v.contentType).startsWith('video/')).map(v=>({...v,assetId:a.id})),hasHigh=variants.some(v=>/high|1080|720|高清/i.test(v.name));return[...(!hasHigh&&String(a.contentType).startsWith('video/')?[{...a,name:'high'}]:[]),...variants]});return{videos:videos.map(x=>({...x,quality:String(x.name).toLowerCase()==='low'?'low':/high|1080|720|高清/i.test(x.name)?'high':x.name})),audio:all.find(x=>String(x.contentType).startsWith('audio/')),image:all.find(x=>String(x.contentType).startsWith('image/')),document:all.find(x=>x.contentType==='application/pdf')}}

function PanelLoading({children}){return<div className="reader-panel-loading"><Spin/><Text type="secondary">{children}</Text></div>}
function Grammar({data}){if(!data)return<div className="reader-panel-state"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="点击字幕旁的句法分析"/></div>;if(data.loading)return<PanelLoading>正在分析当前句法…</PanelLoading>;if(data.error)return<Alert type="error" message={data.error}/>;const s=data.structure||data,tokens=s.tokens||[];return<div className="reader-grammar-panel"><Text className="eyebrow">SENTENCE GRAMMAR · {data.source||'平台句法服务'}</Text><Title level={4}>{s.sentenceType||'句法分析'}</Title>{tokens.length>0&&<Paragraph className="grammar-colored-sentence">{tokens.map((t,i)=><span key={i} className={`grammar-role-${t.role||'token'}`} title={`${t.posZh||t.pos||''} · ${t.relation||''}`}>{t.text}{' '}</span>)}</Paragraph>}{s.pattern&&<Card size="small" title="基本句型">{s.pattern}</Card>}<div className="grammar-core-grid">{[['主语',s.subject],['谓语',s.predicate],['宾语 / 补语',s.object]].filter(([,v])=>v).map(([k,v])=><div key={k}><Text type="secondary">{k}</Text><b>{v}</b></div>)}</div>{(s.clauses||[]).length>0&&<Card size="small" title="从句结构"><ul>{s.clauses.map((x,i)=><li key={i}><b>{x.type}</b> · {x.text}{x.marker?` · 引导词 ${x.marker}`:''}</li>)}</ul></Card>}{(s.grammarPoints||[]).length>0&&<Space wrap>{s.grammarPoints.map(x=><Tag key={x}>{x}</Tag>)}</Space>}<Card size="small" title="中文讲解"><Paragraph className="grammar-copy">{data.aiExplanation||data.explanation||data.payload?.text||'暂无讲解'}</Paragraph></Card></div>}
export default function ReaderPage({preferences:stored,onPreferencesChange,messageApi,currentUser}){
 const params=useMemo(()=>new URLSearchParams(location.search),[]),kind=params.get('reader')==='official'?'official':'workspace',trial=params.get('trial')==='1',bookId=params.get('id')||'',prefs={...DEFAULT_PREFERENCES,...(stored||{})}
 const[book,setBook]=useState(null),[loading,setLoading]=useState(true),[loadError,setLoadError]=useState(''),[active,setActive]=useState(0),[activeWord,setActiveWord]=useState(-1),[learningSentenceId,setLearningSentenceId]=useState(null),[wordInfo,setWordInfo]=useState(null),[hoverWord,setHoverWord]=useState(null),[grammar,setGrammar]=useState(null),[expandedTranslations,setExpandedTranslations]=useState(()=>new Set()),[vocab,setVocab]=useState([]),[annotations,setAnnotations]=useState([]),[meaning,setMeaning]=useState(''),[note,setNote]=useState(''),[panel,setPanel]=useState('word'),[playing,setPlaying]=useState(false),[currentTime,setCurrentTime]=useState(0),[duration,setDuration]=useState(0),[rate,setRate]=useState(Number(prefs.playbackRate)||1),[placement,setPlacement]=useState(prefs.readerLayout==='stack'?'top':'side'),[mediaVisible,setMediaVisible]=useState(true),[eye,setEye]=useState(Boolean(prefs.eyeComfort)),[focus,setFocus]=useState(Boolean(prefs.focusMode)),[autoPause,setAutoPause]=useState(Boolean(prefs.sentenceAutoPause)),[toolsCollapsed,setToolsCollapsed]=useState(Boolean(prefs.focusMode)||!prefs.readerToolsPinned),[toolsPinned,setToolsPinned]=useState(Boolean(prefs.readerToolsPinned)),[appearance,setAppearance]=useState(()=>readerAppearance(prefs)),[readerFlowMode,setReaderFlowMode]=useState(prefs.readerFlowMode==='screen'?'screen':'line'),[quality,setQuality]=useState('low'),[mediaError,setMediaError]=useState(''),[recording,setRecording]=useState(false),[recordingUrl,setRecordingUrl]=useState(''),[shadowStatus,setShadowStatus]=useState('先听原音，再录制自己的跟读。'),[shadowLoading,setShadowLoading]=useState(false),[quickSettingsOpen,setQuickSettingsOpen]=useState(false),[quickSettingsSaving,setQuickSettingsSaving]=useState(false),[appearanceOpen,setAppearanceOpen]=useState(false),[wordSpeaking,setWordSpeaking]=useState(false),[savingWordDetails,setSavingWordDetails]=useState(false)
 const[quickSettingsForm]=Form.useForm()
 const[appearanceForm]=Form.useForm()
 const [focusMediaOpen,setFocusMediaOpen]=useState(false)
 const normalWorkspace=useRef({toolsCollapsed:!prefs.readerToolsPinned,panel:'word'})
 const [appearanceSaving,setAppearanceSaving]=useState(false),[preferenceSaving,setPreferenceSaving]=useState(false),[shortcutFeedback,setShortcutFeedback]=useState(null),[practiceId,setPracticeId]=useState(null)
 const shortcutFeedbackId=useRef(0),shortcutFeedbackTimer=useRef(null),practiceBoundary=useRef(null),hoverTimer=useRef(null),hoverReleaseTimer=useRef(null),hoverTarget=useRef(null),hoverSuppressed=useRef(false),layoutAnchor=useRef(null),preferencesLock=useRef(false),recordingPlaybackRef=useRef(null)
 const [savingWord,setSavingWord]=useState(false),[wordSaveError,setWordSaveError]=useState('')
 const wordRequests=useRef(createReaderRequests()),grammarRequest=useRef(0),wordSaveLock=useRef(false),editorDirty=useRef({meaning:false,note:false}),editorKey=useRef(''),focusOrigin=useRef(null),wordSelection=useRef(null)
 const[removingFromShelf,setRemovingFromShelf]=useState(false)
 const[trialEnded,setTrialEnded]=useState(false),[addingTrial,setAddingTrial]=useState(false),[lightLookupOpen,setLightLookupOpen]=useState(false),[wordAnchor,setWordAnchor]=useState(null)
 const[guideVisible,setGuideVisible]=useState(params.get('onboarding')==='1')
 const [leaveOpen,setLeaveOpen]=useState(false)
 const initialWordIds=useRef(new Set())
 const [savedSession,setSavedSession]=useState(null),[summaryOpen,setSummaryOpen]=useState(false)
 const trialAdding=useRef(false)
 const endTrial=useCallback(()=>{mediaRef.current?.pause();setPlaying(false);setTrialEnded(true)},[])

 const mediaRef=useRef(null),mediaRestore=useRef(null),lastMediaTime=useRef(0),wordAudioRef=useRef(null),storyRef=useRef(null),inspectorRef=useRef(null),sentenceRefs=useRef([]),pausedSentence=useRef(''),hoverResume=useRef(null),hoverRequest=useRef(0),hoverCache=useRef(new Map()),recorderRef=useRef(null),chunks=useRef([])
 const wordAudioCache=useRef(null),wordPlayback=useRef(null),wordAudioOutput=useRef(null)
 if(!wordAudioCache.current)wordAudioCache.current=createWordAudioCache()
 if(!wordAudioOutput.current)wordAudioOutput.current=createWordAudioOutput()
 const stopWordPronunciation=()=>{
  const playback=wordPlayback.current
  wordPlayback.current=null
  playback?.abort.abort()
  const audio=wordAudioRef.current
  if(audio){audio.onended=null;audio.onerror=null;audio.pause()}
  wordAudioRef.current=null;setWordSpeaking(false)
 }
 const load=useCallback(async()=>{setLoading(true);setLoadError('');try{const endpoint=kind==='official'?`/api/catalog/books/${encodeURIComponent(bookId)}/reader${trial?'?trial=1':''}`:`/api/workspace/books/${encodeURIComponent(bookId)}/reader`,[r,v,a]=await Promise.all([getJson(endpoint),trial?Promise.resolve({items:[]}):getJson(`/api/workspace/vocabulary?bookId=${encodeURIComponent(bookId)}`,{items:[]}),kind==='workspace'?getJson(`/api/workspace/annotations?bookId=${encodeURIComponent(bookId)}`,{items:[]}):{items:[]}]);if(!r?.book)throw new Error('阅读器返回的数据不完整');setBook(r.book);setVocab(v.items||[]);initialWordIds.current=new Set((v.items||[]).map(item=>item.id));setAnnotations(a.items||[]);const resume=(!trial&&params.get('sentence'))||r.book.progress?.lastSentenceId,index=Math.max(0,r.book.sentences?.findIndex(x=>String(x.id)===String(resume))??0),time=(!trial&&Number(params.get('resume'))>0?Number(params.get('resume')):startOf(r.book.sentences?.[index]))||0;setActive(index);setLearningSentenceId(r.book.sentences?.[index]?.id||null);setCurrentTime(time);lastMediaTime.current=time;mediaRestore.current={time,resume:false,rate:Number(stored?.playbackRate)||1}}catch(e){setLoadError(e.message||'无法加载读物')}finally{setLoading(false)}},[bookId,kind,trial])
 useEffect(()=>{load()},[load]);useEffect(()=>()=>{if(recordingUrl)URL.revokeObjectURL(recordingUrl);stopWordPronunciation();wordAudioCache.current.clear();wordAudioOutput.current.clear();recorderRef.current?.stream?.getTracks?.().forEach(t=>t.stop())},[recordingUrl])
 const sentences=book?.sentences||[],current=sentences[active]||sentences[0],displayTitle=String(book?.title||'').replace(/\+/g,' '),media=useMemo(()=>mediaOptions(book),[book]),availableVideos=book?.canWatchHdVideo?media.videos:media.videos.filter(x=>x.quality==='low'),video=availableVideos.find(x=>x.url===quality)||availableVideos.find(x=>x.quality===quality)||availableVideos[0],source=video||media.audio,hasVisual=Boolean(video||media.image||media.document),savedWord=wordInfo&&vocab.find(x=>String(x.sentenceId)===String(wordInfo.sentenceId)&&Number(x.wordIndex)===Number(wordInfo.wordIndex)),savedNote=wordInfo&&annotations.find(x=>String(x.sentenceId)===String(wordInfo.sentenceId)&&Number(x.wordIndex)===Number(wordInfo.wordIndex))
 const activeRef=useRef(active),syncRef=useRef(null),pendingSeek=useRef(null),progressPaint=useRef(0),rowActions=useRef({})
 const timeline=useMemo(()=>buildReaderTimeline(sentences),[book?.sentences])
 const annotationIndex=useMemo(()=>{const map=new Map();for(const item of annotations){const key=String(item.sentenceId);if(!map.has(key))map.set(key,new Set());map.get(key).add(Number(item.wordIndex))}return map},[annotations])
 useLayoutEffect(()=>{activeRef.current=active},[active])
 useEffect(()=>{
  if(!playing)return
  let frame
  const tick=()=>{const el=mediaRef.current;if(el&&!el.paused&&!el.ended)syncRef.current?.(el,false);frame=requestAnimationFrame(tick)}
  frame=requestAnimationFrame(tick)
  return()=>cancelAnimationFrame(frame)
 },[playing,source?.url])
 const session=useReaderSession({ownerId:currentUser?.id,bookId,kind,enabled:!!book&&!loading&&!trial,currentId:current?.id,mediaRef,paused:summaryOpen||leaveOpen,hasUnsavedEditor:editorDirty.current.meaning||editorDirty.current.note})
 const {counters,newWordIds,finishAttempt,finishing,completed}=session
 useEffect(()=>{const key=wordInfo?String(wordInfo.sentenceId)+'-'+wordInfo.wordIndex:'';if(editorKey.current!==key){editorKey.current=key;editorDirty.current={meaning:false,note:false};setWordSaveError('')}if(!editorDirty.current.meaning)setMeaning(readerWordMeaning(wordInfo,savedWord));if(!editorDirty.current.note)setNote(savedNote?.payload?.note||savedWord?.payload?.note||'')},[savedWord,savedNote,wordInfo]);useEffect(()=>{if(mediaRef.current)mediaRef.current.playbackRate=rate},[rate,source])
 useEffect(()=>{if(stored?.sentenceAutoPause!==undefined)setAutoPause(Boolean(stored.sentenceAutoPause));if(stored?.eyeComfort!==undefined)setEye(Boolean(stored.eyeComfort));if(stored?.focusMode!==undefined)setFocus(Boolean(stored.focusMode));if(stored?.playbackRate!==undefined)setRate(Number(stored.playbackRate)||1);if(stored?.readerLayout)setPlacement(stored.readerLayout==='stack'?'top':'side');if(stored?.readerFlowMode)setReaderFlowMode(stored.readerFlowMode==='screen'?'screen':'line');if(stored?.readerToolsPinned!==undefined)setToolsPinned(Boolean(stored.readerToolsPinned));setAppearance(readerAppearance(stored||{}))},[stored?.sentenceAutoPause,stored?.eyeComfort,stored?.focusMode,stored?.playbackRate,stored?.readerLayout,stored?.readerFlowMode,stored?.readerToolsPinned,stored?.readerFontSize,stored?.readerLineHeight,stored?.readerContentWidth])
 useEffect(()=>()=>{clearTimeout(hoverTimer.current);clearTimeout(hoverReleaseTimer.current);hoverResume.current=null;clearTimeout(shortcutFeedbackTimer.current)},[])

 useEffect(()=>{if(!lightLookupOpen)return;const close=e=>{if(!e.target.closest?.('.reader-lookup-card,.reader-word'))setLightLookupOpen(false)};const resize=()=>setLightLookupOpen(false);document.addEventListener('pointerdown',close);window.addEventListener('resize',resize);return()=>{document.removeEventListener('pointerdown',close);window.removeEventListener('resize',resize)}},[lightLookupOpen])
 useEffect(()=>{const anchor=layoutAnchor.current;if(!anchor)return;const frame=requestAnimationFrame(()=>{const container=storyRef.current,node=sentenceRefs.current[anchor.index];if(container&&node)container.scrollTop+=node.getBoundingClientRect().top-container.getBoundingClientRect().top-anchor.offset;layoutAnchor.current=null});return()=>cancelAnimationFrame(frame)},[toolsCollapsed,appearance,focus,placement,mediaVisible])
 useEffect(()=>{if(!book||!current?.id||trial)return undefined;const timer=setTimeout(()=>{postJson('/api/workspace/progress',{bookId,lastSentenceId:current.id}).catch(()=>{})},350);return()=>clearTimeout(timer)},[book,bookId,current?.id,trial])


 const continueAfterSave=()=>{setSummaryOpen(false);session.reset();initialWordIds.current=new Set(vocab.map(item=>item.id))}
 const persist=async update=>{if(['focusMode','readerLayout','readerFontSize','readerLineHeight','readerContentWidth','readerFlowMode'].some(key=>key in update))rememberAnchor();if(trial){onPreferencesChange?.(update);return true}try{const result=await postJson('/api/preferences',update);onPreferencesChange?.(result.preferences||update);return true}catch(e){messageApi.error(e.message||'设置保存失败，请重试');return false}}
 const rememberAnchor=()=>{const container=storyRef.current;if(!container)return;const top=container.getBoundingClientRect().top;const index=sentenceRefs.current.findIndex(node=>node&&node.getBoundingClientRect().bottom>top+4);if(index>=0)layoutAnchor.current={index,offset:sentenceRefs.current[index].getBoundingClientRect().top-top}}
 const saveReaderPreference=async(update,apply)=>{if(preferencesLock.current)return;preferencesLock.current=true;setPreferenceSaving(true);try{if(await persist(update)){rememberAnchor();apply?.();messageApi.success(trial?'已应用于本次试读':'阅读偏好已保存')}}finally{preferencesLock.current=false;setPreferenceSaving(false)}}
 const openAppearance=()=>{appearanceForm.setFieldsValue({...appearance,readerFlowMode,wordAutoPronounce:prefs.wordAutoPronounce,wordHoverPause:prefs.wordHoverPause});setAppearanceOpen(true)}
 const saveAppearance=async values=>{setAppearanceSaving(true);const flowMode=values.readerFlowMode==='screen'?'screen':'line',update={...readerAppearance(values),readerFlowMode:flowMode,wordAutoPronounce:Boolean(values.wordAutoPronounce),wordHoverPause:Boolean(values.wordHoverPause)};if(await persist(update)){rememberAnchor();setAppearance(readerAppearance(update));setReaderFlowMode(flowMode);setAppearanceOpen(false);messageApi.success(trial?'已应用于本次试读':'阅读设置已保存')}setAppearanceSaving(false)}
 const switchFocus=()=>{if(recording||shadowLoading||preferencesLock.current)return;const entering=!focus,snapshot={toolsCollapsed,panel};saveReaderPreference({focusMode:entering},()=>{rememberAnchor();hoverEnd(hoverResume.current?.key);setLightLookupOpen(false);setFocusMediaOpen(false);if(entering){normalWorkspace.current=snapshot;setToolsCollapsed(true)}else{setToolsCollapsed(normalWorkspace.current.toolsCollapsed);setPanel(normalWorkspace.current.panel)}setFocus(entering)})}
 const addTrialBook=async()=>{if(trialAdding.current)return;trialAdding.current=true;setAddingTrial(true);const resume=mediaRef.current?.currentTime||currentTime;try{await postJson('/api/library/items',{bookId,shelfState:'active'});messageApi.success('已加入书架，正在打开完整内容');location.replace(`/app?screen=reader&reader=official&id=${encodeURIComponent(bookId)}&resume=${resume}${guideVisible?'&onboarding=1':''}`)}catch(e){if(!handleMembershipLimit(e,{onClose:()=>setTrialEnded(false),onContinue:addTrialBook}))messageApi.error(e.message||'加入书架失败')}finally{trialAdding.current=false;setAddingTrial(false)}}
 const removeFromShelf=()=>{Modal.confirm({title:'确认移出书架？',content:'移出后将刷新当前读物并进入试读模式。',okText:'移出书架',cancelText:'取消',okButtonProps:{danger:true},onOk:async()=>{setRemovingFromShelf(true);try{await deleteJson(`/api/library/items/${encodeURIComponent(bookId)}`);messageApi.success('已移出书架，正在进入试读');location.replace(`/app?screen=reader&reader=official&id=${encodeURIComponent(bookId)}&trial=1`)}catch(error){messageApi.error(error.message||'移出书架失败')}finally{setRemovingFromShelf(false)}}})}
 const captureMediaState=()=>{const el=mediaRef.current;return{time:el?.currentTime??currentTime,resume:Boolean(el&&!el.paused),rate:el?.playbackRate||rate,volume:el?.volume??1,muted:Boolean(el?.muted)}}
 const saveMediaCompletion=async progress=>{messageApi.loading({key:'reader-completion',duration:0,content:'正在保存完成进度…'});try{await postJson('/api/workspace/progress',{bookId,...progress});messageApi.success({key:'reader-completion',content:'已播放完毕，阅读进度已更新为 100%'})}catch(error){messageApi.error({key:'reader-completion',duration:0,content:<Space>完成进度保存失败：{error.message||'请重试'}<Button size="small" onClick={()=>saveMediaCompletion(progress)}>重试</Button></Space>})}}
 const mediaEnded=event=>{setPlaying(false);if(trial){endTrial();return}const progress=mediaCompletionProgress({ended:event.currentTarget.ended,trial,sentences});if(progress){activeRef.current=sentences.length-1;setActive(sentences.length-1);saveMediaCompletion(progress)}}
 const mediaLoaded=e=>{const el=e.currentTarget,restore=mediaRestore.current;setDuration(el.duration||Number(book.duration)||0);el.playbackRate=restore?.rate||rate;el.volume=restore?.volume??1;el.muted=restore?.muted??false;const target=restore?.time??currentTime;if(target>0&&Math.abs(el.currentTime-target)>.15)el.currentTime=target;lastMediaTime.current=target;if(restore){setCurrentTime(target);mediaRestore.current=null;if(restore.resume)playReaderMedia(el,()=>{setPlaying(false);setMediaError('清晰度已切换，请点击播放按钮继续。')});else setPlaying(false)}}
 const openQuickSettings=()=>{quickSettingsForm.setFieldsValue({shortcutPrevious:prefs.shortcutPrevious,shortcutRepeat:prefs.shortcutRepeat,shortcutNext:prefs.shortcutNext,shortcutPlay:prefs.shortcutPlay,sentenceAutoPause:autoPause});setQuickSettingsOpen(true)}
 const resumeAfterSentencePause=()=>{const player=mediaRef.current,shouldResume=Boolean(pausedSentence.current&&player?.paused);pausedSentence.current='';if(shouldResume)playReaderMedia(player,()=>setMediaError('无法自动继续播放，请点击播放按钮继续。'))}
 const saveQuickSettings=async values=>{const shortcuts=[values.shortcutPrevious,values.shortcutRepeat,values.shortcutNext,values.shortcutPlay];if(new Set(shortcuts).size!==shortcuts.length){messageApi.error('四个阅读快捷键不能重复');return}setQuickSettingsSaving(true);const update={shortcutPrevious:values.shortcutPrevious,shortcutRepeat:values.shortcutRepeat,shortcutNext:values.shortcutNext,shortcutPlay:values.shortcutPlay,sentenceAutoPause:Boolean(values.sentenceAutoPause)},resumePlayback=!update.sentenceAutoPause&&Boolean(pausedSentence.current&&mediaRef.current?.paused);setAutoPause(update.sentenceAutoPause);if(await persist(update)){if(resumePlayback)resumeAfterSentencePause();else pausedSentence.current='';setQuickSettingsOpen(false);messageApi.success('播放与快捷键设置已保存')}setQuickSettingsSaving(false)}
 const scrollSentence=useCallback((index,behavior='smooth')=>{const container=storyRef.current,target=sentenceRefs.current[index];if(!container||!target)return;const containerRect=container.getBoundingClientRect(),targetRect=target.getBoundingClientRect(),top=readerScrollTop({mode:readerFlowMode,scrollTop:container.scrollTop,viewportHeight:container.clientHeight,targetTop:targetRect.top-containerRect.top,targetHeight:targetRect.height});if(top!==null)container.scrollTo({top,behavior})},[readerFlowMode])
 useEffect(()=>{if(!book)return;const frame=requestAnimationFrame(()=>scrollSentence(activeRef.current,'auto'));return()=>cancelAnimationFrame(frame)},[book,readerFlowMode,scrollSentence])
 const seekSentence=useCallback((index,play=false)=>{if(recording||shadowLoading)return;if(!sentences.length)return;if(trial&&index>=sentences.length){endTrial();return}const i=Math.max(0,Math.min(sentences.length-1,index)),s=sentences[i];practiceBoundary.current=null;activeRef.current=i;const t=startOf(s);flushSync(()=>{setActive(i);setActiveWord(t===null?-1:timelineWord(timeline,i,t))});pausedSentence.current='';scrollSentence(i,'instant');if(mediaRef.current&&t!==null){pendingSeek.current={index:i,time:Math.max(0,t)};lastMediaTime.current=Math.max(0,t);mediaRef.current.currentTime=Math.max(0,t);setCurrentTime(t);if(play)playReaderMedia(mediaRef.current,()=>setMediaError('浏览器阻止了自动播放，请手动点击播放。'))}},[scrollSentence,sentences,trial,endTrial,recording,shadowLoading,timeline])
 const togglePlay=useCallback(()=>{if(recording||shadowLoading)return;clearTimeout(hoverReleaseTimer.current);hoverResume.current=null;stopWordPronunciation();recordingPlaybackRef.current?.pause();practiceBoundary.current=null;const el=mediaRef.current;if(!el)return;el.paused?playReaderMedia(el,()=>setMediaError('无法播放原始媒体，请检查资源。')):el.pause()},[recording,shadowLoading]),repeat=useCallback(()=>seekSentence(activeRef.current,true),[seekSentence]),previous=useCallback(()=>seekSentence(activeRef.current-1,true),[seekSentence]),next=useCallback(()=>seekSentence(activeRef.current+1,true),[seekSentence])
 useEffect(()=>{const keydown=e=>{if(recording||shadowLoading||e.ctrlKey||e.metaKey||e.altKey)return;const target=e.target;if(target instanceof HTMLInputElement||target instanceof HTMLTextAreaElement||target?.isContentEditable||target?.closest?.('select,[role="combobox"],.ant-select-dropdown:not(.ant-select-dropdown-hidden),.reader-media-drag-handle'))return;const key=e.key===' '?' ':e.key.toLowerCase();if(key==='q'&&source){e.preventDefault();const value=!autoPause;setAutoPause(value);if(quickSettingsOpen)quickSettingsForm.setFieldValue('sentenceAutoPause',value);if(value)pausedSentence.current='';else resumeAfterSentencePause();persist({sentenceAutoPause:value});const id=++shortcutFeedbackId.current;setShortcutFeedback({id,text:'Q · 句末暂停 · '+(value?'已开启':'已关闭')});clearTimeout(shortcutFeedbackTimer.current);shortcutFeedbackTimer.current=setTimeout(()=>setShortcutFeedback(current=>current?.id===id?null:current),1100);return}const action=[[keyboardKey(prefs.shortcutPrevious),previous,'上一句'],[source?keyboardKey(prefs.shortcutRepeat):null,repeat,'复读当前句'],[keyboardKey(prefs.shortcutNext),next,'下一句'],[source?keyboardKey(prefs.shortcutPlay):null,togglePlay,'播放/暂停']].find(([k])=>k===key);if(action){e.preventDefault();action[1]();const shortcut=key===' '?'空格':key==='arrowleft'?'←':key==='arrowright'?'→':key.toUpperCase(),id=++shortcutFeedbackId.current;setShortcutFeedback({id,text:shortcut+' · '+action[2]});clearTimeout(shortcutFeedbackTimer.current);shortcutFeedbackTimer.current=setTimeout(()=>setShortcutFeedback(current=>current?.id===id?null:current),1100)}};addEventListener('keydown',keydown,true);return()=>removeEventListener('keydown',keydown,true)},[recording,shadowLoading,source,autoPause,quickSettingsOpen,next,prefs.shortcutNext,prefs.shortcutPlay,prefs.shortcutPrevious,prefs.shortcutRepeat,previous,repeat,togglePlay])
 const syncMedia=(el,force=false)=>{
  let time=el.currentTime
  const pending=pendingSeek.current
  if(pending){
   // Keep the requested row while the decoder is seeking, ignoring stale callbacks.
   if(el.seeking||Math.abs(time-pending.time)>.15)return
   pendingSeek.current=null
  }
  const previous=lastMediaTime.current
  lastMediaTime.current=time
  if(trial&&book?.trialEndSeconds>0&&time>=book.trialEndSeconds){
   el.pause();time=book.trialEndSeconds;if(el.currentTime>time)el.currentTime=time;setTrialEnded(true)
  }
  const index=activeRef.current,sentence=sentences[index],end=endOf(sentence,sentences[index+1]),token=String(sentence?.id??'')
  const practice=practiceBoundary.current
  if(practice&&!el.seeking&&!el.paused&&time>=practice.end){
   el.pause();time=Math.max(practice.start,practice.end-.001);el.currentTime=time;practiceBoundary.current=null;setShadowStatus('原句播放结束，接下来录一句。')
  }else if(autoPause&&sentence&&crossedSentenceEnd({previous,time,end,playing:!el.paused,seeking:el.seeking,paused:pausedSentence.current===token})){
   pausedSentence.current=token;time=Math.max(startOf(sentence)||0,end-.001);el.pause();el.currentTime=time
  }
  lastMediaTime.current=time
  // The progress slider does not need to repaint at word/animation-frame frequency.
  const now=performance.now()
  if(force||el.paused||now-progressPaint.current>=100){progressPaint.current=now;setCurrentTime(time)}
  const i=timelineSentence(timeline,time)
  if(i>=0){
   if(i!==activeRef.current){activeRef.current=i;setActive(i);scrollSentence(i)}
   const word=timelineWord(timeline,i,time)
   setActiveWord(current=>current===word?current:word)
  }else setActiveWord(-1)
 }
 useLayoutEffect(()=>{syncRef.current=syncMedia})
 const sync=e=>syncMedia(e.currentTarget,true)
 const seeking=e=>{const el=e.currentTarget,preservePause=pausedSentence.current&&el.paused&&Math.abs(el.currentTime-lastMediaTime.current)<.005;lastMediaTime.current=el.currentTime;if(!preservePause)pausedSentence.current='';if(!pendingSeek.current)syncMedia(el,true)}
 const seeked=e=>{pendingSeek.current=null;lastMediaTime.current=e.currentTarget.currentTime;syncMedia(e.currentTarget,true)}
 const switchQuality=value=>{
  if(recording||shadowLoading)return
  const selected=media.videos.find(item=>item.url===value)
  if(!selected||value===video?.url)return
  if(!book?.canWatchHdVideo&&selected.quality!=='low'){
   handleMembershipLimit({code:'video_quality_membership_required',message:'高清画质需要付费会员，升级后可继续切换。'}, {onContinue:async()=>{
    const endpoint=kind==='official'?'/api/catalog/books/'+encodeURIComponent(bookId)+'/reader'+(trial?'?trial=1':''):'/api/workspace/books/'+encodeURIComponent(bookId)+'/reader'
    const latest=await getJson(endpoint)
    if(!latest?.book?.canWatchHdVideo)throw new Error('会员权益尚未生效，请稍后重试。')
    mediaRestore.current=captureMediaState();setBook(latest.book);setQuality(value)
   }})
   return
  }
  mediaRestore.current=captureMediaState();setQuality(value)
 }
 const resumeMedia=session=>{if(session?.resume&&mediaRef.current?.paused)mediaRef.current.play().catch(()=>setMediaError('无法继续播放原始媒体，请手动点击播放。'))}
 const playWordPronunciation=word=>{
  if(!word||recording||shadowLoading)return
  const mediaElement=mediaRef.current,shouldResume=Boolean(hoverResume.current?.resume||wordPlayback.current?.resume||(mediaElement&&!mediaElement.paused))
  // Transfer the pause directly from hover/previous pronunciation; never briefly resume the video.
  clearTimeout(hoverReleaseTimer.current);clearTimeout(hoverTimer.current)
  hoverResume.current=null;hoverTarget.current=null;hoverRequest.current+=1;setHoverWord(null)
  stopWordPronunciation()
  if(mediaElement&&!mediaElement.paused)mediaElement.pause()
  const audio=wordAudioCache.current.prepare(word),abort=new AbortController(),playback={audio,abort,resume:shouldResume}
  wordPlayback.current=playback;wordAudioRef.current=audio;setWordSpeaking(true)
  const finish=()=>{
   if(wordPlayback.current!==playback)return false
   abort.abort()
   audio.onended=null;audio.onerror=null;wordPlayback.current=null;wordAudioRef.current=null;setWordSpeaking(false)
   if(shouldResume&&mediaRef.current===mediaElement&&mediaElement?.paused){
    if(hoverResume.current)hoverResume.current.resume=true
    else resumeMedia({resume:true})
   }
   return true
  }
  audio.onended=finish
  const failed=error=>{
   if(error.name==='AbortError')return
   if(finish())messageApi.error(error.name==='NotAllowedError'?'浏览器阻止了单词发音，请点击发音按钮重试。':error.message||'单词发音加载失败')
  }
  audio.onerror=()=>failed(new Error('单词发音加载失败'))
  playWordFromStart(audio,abort.signal,15000,wordAudioOutput.current).catch(failed)
 }
 const hoverStart=(key,word,element)=>{
  if(hoverSuppressed.current||lightLookupOpen||recording||shadowLoading)return
  clearTimeout(hoverReleaseTimer.current)
  clearTimeout(hoverTimer.current)
  hoverTarget.current=key
  // Carry the original playback intent across words, including their lookup delay.
  if(hoverResume.current)hoverResume.current={...hoverResume.current,key}
  hoverTimer.current=setTimeout(async()=>{
   if(!element.isConnected)return
   // Freeze an in-flight playback scroll so it cannot dismiss the hover and resume audio.
   const story=storyRef.current
   if(story)story.scrollTo({top:story.scrollTop,behavior:'instant'})
   const rect=element.getBoundingClientRect(),anchor={left:rect.left,top:rect.top,bottom:rect.bottom,width:rect.width},cached=hoverCache.current.get(word.toLocaleLowerCase())
   if(prefs.wordAutoPronounce)wordAudioCache.current.prepare(word)
   const requestId=++hoverRequest.current,el=mediaRef.current,resume=Boolean(hoverResume.current?.resume||(prefs.wordHoverPause&&el&&!el.paused))
   hoverResume.current={key,resume}
   if(resume&&el&&!el.paused)el.pause()
   const setResult=(entries,loading=false,error=false)=>setHoverWord({key,word,entries,anchor,paused:resume,loading,error})
   setResult(cached||['正在查询释义…'],!cached)
   if(cached)return
   try{
    const data=await getJson('/api/word-hover?word='+encodeURIComponent(word)),entries=(data.entries||[]).filter(Boolean)
    if(entries.length)hoverCache.current.set(word.toLocaleLowerCase(),entries)
    if(requestId===hoverRequest.current)setResult(entries.length?entries:['暂无简明释义'])
   }catch(e){if(requestId===hoverRequest.current)setResult(['暂时无法查询，请点击单词重试。'],false,true)}
  },300)
 }
 const hoverEnd=(key,delay=0)=>{
  if(delay&&key!==hoverTarget.current)return
  clearTimeout(hoverTimer.current);clearTimeout(hoverReleaseTimer.current)
  hoverTarget.current=null;hoverRequest.current+=1;setHoverWord(null)
  const session=hoverResume.current
  if(!session)return
  const finish=()=>{
   // A newer word, explicit playback action or page exit supersedes this release.
   if(hoverResume.current!==session||hoverTarget.current)return
   hoverResume.current=null;resumeMedia(session)
  }
  const release=()=>{
   if(hoverResume.current!==session||hoverTarget.current)return
   const wordAudio=wordAudioRef.current
   if(session.resume&&wordAudio&&wordPlayback.current){
    const done=()=>{wordAudio.removeEventListener('ended',done);wordAudio.removeEventListener('error',done);finish()}
    wordAudio.addEventListener('ended',done);wordAudio.addEventListener('error',done)
   }else finish()
  }
  if(delay)hoverReleaseTimer.current=setTimeout(release,delay)
  else release()
 }
 const resetInspector=()=>requestAnimationFrame(()=>inspectorRef.current?.scrollTo({top:0,behavior:'smooth'}))
 const showTools=(target,trigger)=>{if(recording||shadowLoading){messageApi.info('请先停止录音，再切换学习工具');return}rememberAnchor();focusOrigin.current=trigger||focusOrigin.current||document.activeElement;setPanel(target);setToolsCollapsed(false);setLightLookupOpen(false);hoverEnd(hoverResume.current?.key);resetInspector()}
 const closeTools=()=>{if(recording||shadowLoading){messageApi.info('请先停止录音再收起工具');return}rememberAnchor();setToolsCollapsed(true);setLightLookupOpen(false);restoreWordFocus()}
 const restoreWordFocus=()=>{hoverSuppressed.current=true;requestAnimationFrame(()=>{if(focusOrigin.current?.isConnected)focusOrigin.current.focus({preventScroll:true});hoverSuppressed.current=false})}
 const closeLookup=()=>{setLightLookupOpen(false);restoreWordFocus()}
 const locateSentence=id=>{setLightLookupOpen(false);const index=sentenceIndex(sentences,id,active);scrollSentence(index)}
 const practiceSentence=(id,trigger)=>{if(recording||shadowLoading){messageApi.info('请先停止录音，再切换练习句');return}const index=sentenceIndex(sentences,id,active),s=sentences[index];if(!s)return;if(String(practiceId)!==String(s.id)){recordingPlaybackRef.current?.pause();if(practiceBoundary.current)mediaRef.current?.pause();setRecordingUrl('');practiceBoundary.current=null;setShadowStatus('先听原音，再录制自己的跟读。')}setPracticeId(s.id);setLearningSentenceId(s.id);session.visit(s.id);showTools('shadow',trigger)}
 const playPractice=()=>{if(recording||shadowLoading)return;const index=sentenceIndex(sentences,practiceId,active),range=sentencePlaybackRange(sentences,index,duration||book?.duration);if(!source||!range)return;stopWordPronunciation();recordingPlaybackRef.current?.pause();hoverResume.current=null;seekSentence(index,true);practiceBoundary.current=range;setShadowStatus('正在听这一句原音，句末自动停止。')}
 const changePanel=value=>{if(recording||shadowLoading){messageApi.info('请先停止录音，再切换学习工具');return}if(value==='shadow')practiceSentence(learningSentenceId);else{setPanel(value);resetInspector()}}
 const requestWordSection=(section,selection)=>{
  const {word,sentenceId,wordIndex}=selection
  setWordInfo(info=>({...info,[section+'Loading']:true,[section+'Error']:''}))
  return wordRequests.current.run(section,
   ()=>section==='context'?postJson('/api/word-context',{bookId,sentenceId,wordIndex,word}):getJson('/api/word-dictionary?word='+encodeURIComponent(word)),
   data=>setWordInfo(info=>({...info,[section]:data,[section+'Loading']:false})),
   error=>{setWordInfo(info=>({...info,[section+'Loading']:false,[section+'Error']:error.message||'服务暂不可用，请重试'}));if(section==='context')handleMembershipLimit(error,{onClose:()=>mediaRef.current?.pause(),onContinue:()=>{const selected=wordSelection.current;if(selected&&selected.sentenceId===sentenceId&&selected.wordIndex===wordIndex)return requestWordSection(section,selected)}})}
  )
 }
 const selectWord=(s,index,word,trigger)=>{wordRequests.current.select();const selection={word,wordIndex:index,sentenceId:s.id};wordSelection.current=selection;editorDirty.current={meaning:false,note:false};setWordInfo({...selection,contextLoading:true,dictionaryLoading:true});setLearningSentenceId(s.id);focusOrigin.current=trigger;if(prefs.wordAutoPronounce)playWordPronunciation(word);hoverEnd(hoverResume.current?.key);if(!toolsCollapsed){showTools('word',trigger)}else{const rect=trigger?.getBoundingClientRect();setWordAnchor({left:Math.max(16,Math.min(innerWidth-392,rect?.left||16)),top:rect&&innerHeight-rect.bottom>355?rect.bottom+10:Math.max(84,(rect?.top||450)-350)});setLightLookupOpen(true)}session.visit(s.id);if(!finishAttempt.current&&!completed)counters.current.lookups++;requestWordSection('context',selection);requestWordSection('dictionary',selection)}
 const lookup=(s,index,word,trigger)=>{if(savingWord||savingWordDetails){messageApi.info('正在保存当前单词，请稍候。');return}if(editorDirty.current.meaning||editorDirty.current.note){Modal.confirm({title:'先保存当前单词的修改？',content:'当前私人释义或备注尚未保存。保存成功后会打开所选单词。',okText:'保存并切换',cancelText:'继续编辑',onOk:async()=>{if(!(await saveWordDetails()))return Promise.reject();selectWord(s,index,word,trigger)}});return}selectWord(s,index,word,trigger)}
 const analyze=async(s,trigger)=>{setLearningSentenceId(s.id);const request=++grammarRequest.current;showTools('grammar',trigger);session.visit(s.id);setGrammar({loading:true,sentence:s});try{const data=await postJson('/api/sentence-grammar',{bookId,sentenceId:s.id});if(request===grammarRequest.current)setGrammar({...data,sentence:s})}catch(e){if(request!==grammarRequest.current)return;setGrammar({error:e.message,sentence:s});handleMembershipLimit(e,{onClose:()=>mediaRef.current?.pause(),onContinue:()=>analyze(s)})}}
 const vocabPayload=rating=>{const intervals={again:1,hard:2,good:4,easy:8},days=intervals[rating]||Number(savedWord?.payload?.interval_days||1);return{...(savedWord?.payload||{}),word:wordInfo.word,meaning:editorDirty.current.meaning?meaning.trim():(meaning.trim()||readerWordMeaning(wordInfo,savedWord)),note:note.trim(),context:sentences.find(sentence=>String(sentence.id)===String(wordInfo.sentenceId))?.text||'',rating:rating||savedWord?.payload?.rating||'unknown',interval_days:days,due_at:!rating&&(savedWord?.payload?.due_at||savedWord?.payload?.dueAt)?(savedWord.payload.due_at||savedWord.payload.dueAt):new Date(Date.now()+(rating?days:0)*86400000).toISOString(),reviews:Number(savedWord?.payload?.reviews||0)+(rating?1:0)}}
 const saveWord=async(rating,silent=false)=>{
  if(trial){endTrial();return null}if(!wordInfo?.word||wordSaveLock.current||finishAttempt.current||completed)return null
  wordSaveLock.current=true;setSavingWord(true);setWordSaveError('');const selection=wordInfo
  try{const saved=await postJson('/api/workspace/vocabulary',{bookId,sentenceId:selection.sentenceId,wordIndex:selection.wordIndex,payload:vocabPayload(rating)});if(saved.isNew||!initialWordIds.current.has(saved.id))newWordIds.current.add(saved.id);setVocab(items=>[...items.filter(x=>!(String(x.sentenceId)===String(saved.sentenceId)&&Number(x.wordIndex)===Number(saved.wordIndex))),saved]);if(rating)counters.current.reviews++;session.checkpoint();if(!silent)messageApi.success(rating?'认识程度已记录':'已加入生词本，可稍后复习');return saved}
  catch(e){if(wordSelection.current?.sentenceId===selection.sentenceId&&wordSelection.current?.wordIndex===selection.wordIndex)setWordSaveError(e.message||'保存失败');messageApi.error(e.message||'保存失败');return null}
  finally{wordSaveLock.current=false;setSavingWord(false)}
 }
 const saveAnnotation=async(selection,noteValue)=>{if(kind!=='workspace'||!selection?.word)return null;try{const saved=await postJson('/api/workspace/annotations',{bookId,sentenceId:selection.sentenceId,wordIndex:selection.wordIndex,payload:{note:noteValue.trim(),word:selection.word,updatedAt:new Date().toISOString()}});setAnnotations(items=>[...items.filter(x=>!(String(x.sentenceId)===String(saved.sentenceId)&&Number(x.wordIndex)===Number(saved.wordIndex))),saved]);return saved}catch(e){if(wordSelection.current?.sentenceId===selection.sentenceId&&wordSelection.current?.wordIndex===selection.wordIndex)setWordSaveError('生词已保存，备注保存失败：'+e.message);messageApi.error(e.message);return null}}
 const saveWordDetails=async()=>{if(savingWordDetails||wordSaveLock.current)return false;const selection=wordInfo,noteValue=note;setSavingWordDetails(true);const wordSaved=await saveWord(undefined,true),noteSaved=wordSaved&&await saveAnnotation(selection,noteValue);if(wordSaved&&noteSaved){if(wordSelection.current?.sentenceId===selection.sentenceId&&wordSelection.current?.wordIndex===selection.wordIndex)editorDirty.current={meaning:false,note:false};messageApi.success('私人释义与备注已保存')}setSavingWordDetails(false);return Boolean(wordSaved&&noteSaved)}
 const record=async()=>{if(recording&&recorderRef.current){recorderRef.current.stop();return}if(finishing||completed||finishAttempt.current)return;practiceBoundary.current=null;stopWordPronunciation();recordingPlaybackRef.current?.pause();if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder){setShadowStatus('当前浏览器不支持录音。');return}setShadowLoading(true);try{mediaRef.current?.pause();setShadowStatus('正在申请麦克风权限…');const stream=await navigator.mediaDevices.getUserMedia({audio:true});chunks.current=[];const recorder=new MediaRecorder(stream);recorderRef.current=recorder;recorder.ondataavailable=e=>{if(e.data.size)chunks.current.push(e.data)};recorder.onstop=()=>{const blob=new Blob(chunks.current,{type:recorder.mimeType||'audio/webm'});if(recordingUrl)URL.revokeObjectURL(recordingUrl);setRecordingUrl(URL.createObjectURL(blob));stream.getTracks().forEach(t=>t.stop());setRecording(false);setShadowStatus('录音完成，可回放并与原始音频对比。');counters.current.shadowAttempts++};recorder.start();setRecording(true);setShadowStatus('正在录音，完成后点击停止。')}catch(e){setRecording(false);setShadowStatus(e.name==='NotAllowedError'?'麦克风权限被拒绝，请允许后重试。':`无法录音：${e.message}`)}finally{setShadowLoading(false)}}
 const goToWorkspace=()=>{location.href='/app?screen=workspace'}
 const finish=async(leave=false)=>{
  if(trial){endTrial();return false}if(finishing||savingWord||savingWordDetails)return false
  if(recording||shadowLoading){messageApi.info('请先停止录音，再保存学习。');return false}
  if((editorDirty.current.meaning||editorDirty.current.note)&&!(await saveWordDetails()))return false
  const result=await session.save();if(!result)return false
  setSavedSession(result);setLeaveOpen(false)
  if(leave)goToWorkspace();else setSummaryOpen(true)
  messageApi.success('本次学习记录已保存');return true
 }
 const requestLeave=()=>{if(finishing||savingWord||savingWordDetails){messageApi.info('正在保存，请稍候。');return}if(recording||shadowLoading){messageApi.info('请先停止录音再离开。');return}hoverResume.current=null;mediaRef.current?.pause();stopWordPronunciation();if(!trial&&(session.dirty()||editorDirty.current.meaning||editorDirty.current.note))setLeaveOpen(true);else goToWorkspace()}
 useLayoutEffect(()=>{rowActions.current={
  select:(s,i)=>{setLearningSentenceId(s.id);seekSentence(i,true)},
  hoverStart,hoverEnd,
  lookup:(...args)=>trial?messageApi.info('加入书架后可使用词汇学习功能'):lookup(...args),
  practice:practiceSentence,
  analyze:(...args)=>trial?messageApi.info('加入书架后可使用句法分析'):analyze(...args),
  translate:s=>{setLearningSentenceId(s.id);session.visit(s.id);setExpandedTranslations(current=>{const next=new Set(current),key=String(s.id);next.has(key)?next.delete(key):next.add(key);return next})},
 }})
 if(loading)return<PageSkeleton reader/>;if(loadError)return<div className="reader-loading"><Alert type="error" message="读物加载失败" description={loadError} action={<Button onClick={load}>重新加载</Button>}/></div>;if(!book||!sentences.length)return<Empty className="reader-loading" description="该读物没有可阅读的句子"/>
 const learningIndex=sentenceIndex(sentences,learningSentenceId,active),practiceIndex=sentenceIndex(sentences,practiceId,learningIndex),practice=sentences[practiceIndex],practiceRange=sentencePlaybackRange(sentences,practiceIndex,duration||book.duration)
 const wordProps={info:wordInfo,sentence:sentences.find(s=>String(s.id)===String(wordInfo?.sentenceId)),savedWord,meaning,note,onMeaning:value=>{editorDirty.current.meaning=true;setMeaning(value)},onNote:value=>{editorDirty.current.note=true;setNote(value)},onSpeak:()=>playWordPronunciation(wordInfo?.word),speaking:wordSpeaking,onSave:saveWord,onSaveDetails:saveWordDetails,saving:savingWord,savingDetails:savingWordDetails,saveError:wordSaveError,onRetry:section=>requestWordSection(section,wordInfo),privateBook:kind==='workspace',locked:finishing||completed||!!finishAttempt.current}
 const wordPanel=<ReaderWordPanel {...wordProps}/>
 const tabs=[{key:'word',label:<span className="reader-tab-label reader-tab-word">单词</span>,children:wordPanel},{key:'grammar',label:<span className="reader-tab-label reader-tab-grammar">句法</span>,children:<><section className="reader-source-sentence"><Text className="reader-section-label">分析原句</Text><Paragraph>{grammar?.sentence?.text||'选择一句正文开始分析'}</Paragraph></section>{grammar?.error?<Alert type="warning" showIcon message="句法分析暂不可用" description={grammar.error} action={<Button onClick={()=>analyze(grammar.sentence)}>重试句法</Button>}/>:<Grammar data={grammar}/>}</>},{key:'shadow',label:<span className="reader-tab-label reader-tab-shadow">跟读</span>,children:<div className="reader-shadow-panel"><Text className="eyebrow">SHADOWING · 原音练习</Text><Title level={4}>练这一句</Title><section className="reader-shadow-sentence"><Text className="reader-section-label">练习第 {practiceIndex+1} 句 · {displayTitle}</Text><Paragraph className="current-sentence-copy">{practice?.text}</Paragraph></section><ol className="reader-practice-steps"><li>听原句</li><li>录一句</li><li>回放对比</li></ol>{!source&&<Alert type="info" showIcon message={media.videos.length?'原音当前不可用':'此材料未附原音'} description="原音跟读需要材料自带的音视频。你仍可阅读、查词和收藏生词。"/>}{source&&!practiceRange&&<Alert type="info" message="此句缺少有效时间标记" description="暂不能截取这一句原音，可使用底部播放器听完整材料。"/>}<Space wrap><Button disabled={!source||!practiceRange||recording||shadowLoading} icon={<PlayCircleFilled/>} onClick={playPractice}>听这一句原音</Button><Button disabled={!source||!practiceRange||finishing||completed||!!finishAttempt.current} loading={shadowLoading} danger={recording} icon={<AudioOutlined/>} onClick={record}>{recording?'停止录音':recordingUrl?'重新录制':'录这一句'}</Button></Space>{source&&<Paragraph type="secondary" className="shadow-status" role="status">{shadowStatus}</Paragraph>}{recordingUrl&&<section className="reader-recording-result"><Text strong>我的录音 · 第 {practiceIndex+1} 句</Text><audio ref={recordingPlaybackRef} aria-label="回放我的录音" className="shadow-playback" src={recordingUrl} controls onPlay={()=>{mediaRef.current?.pause();stopWordPronunciation()}}/><Text type="secondary">回放后再听原句，对比节奏与发音。录音仅保留在本页。</Text></section>}<Button disabled={recording||shadowLoading||practiceIndex>=sentences.length-1} onClick={()=>practiceSentence(sentences[practiceIndex+1]?.id)}>练下一句</Button></div>}]
 const toolSentenceId=panel==='word'?wordInfo?.sentenceId:panel==='grammar'?grammar?.sentence?.id:practice?.id
 const toolIndex=sentenceIndex(sentences,toolSentenceId,learningIndex)
 const mediaPanel=hasVisual?<section className="reader-media-panel" aria-label="原始画面"><div className="reader-media-stage">{video&&<video key={video.url} ref={mediaRef} className="reader-media" src={video.url} controls muted={false} controlsList="nodownload noremoteplayback" disablePictureInPicture preload="metadata" onContextMenu={event=>event.preventDefault()} onEnded={mediaEnded} onSeeking={seeking} onSeeked={seeked} onTimeUpdate={sync} onLoadedMetadata={mediaLoaded} onRateChange={event=>setRate(event.currentTarget.playbackRate)} onPlay={e=>{if(recording||shadowLoading){e.currentTarget.pause();return}recordingPlaybackRef.current?.pause();setPlaying(true)}} onPause={()=>setPlaying(false)} onError={()=>setMediaError('视频加载失败，请切换清晰度或重新加载。')}/>} {!video&&media.image&&<img className="reader-original-image" src={media.image.url} alt={`${displayTitle} 原始页面`}/>} {!video&&!media.image&&media.document&&<iframe className="reader-document" src={media.document.url} title={`${displayTitle} 原始文档`}/>}<div className={`reader-media-toolbar ${video?'is-video':''}`}><Space size={4}>{hasVisual&&mediaVisible&&!focus&&<Tooltip title={placement==='side'?'切换后，画面会移到正文上方':'切换后，画面会移到正文左侧'}><Button className="reader-media-layout-switch" size="small" onClick={()=>{mediaRestore.current=captureMediaState();const value=placement==='side'?'top':'side';setPlacement(value);persist({readerLayout:value==='top'?'stack':'side'})}}>{placement==='side'?'画面移至上方':'画面移至左侧'}</Button></Tooltip>}{media.videos.length>1&&media.videos.map(item=><Button key={item.url} size="small" type={item.url===video?.url?'primary':'text'} onClick={()=>switchQuality(item.url)}>{item.quality==='low'?'流畅':item.quality==='high'?(book?.canWatchHdVideo?'高清':'高清 · 会员'):item.name}</Button>)}<Tooltip title="关闭媒体；可通过顶部媒体按钮重新打开"><Button size="small" type="text" aria-label="关闭媒体" disabled={recording||shadowLoading} icon={<CloseOutlined/>} onClick={()=>{rememberAnchor();if(focus)setFocusMediaOpen(false);else setMediaVisible(false)}}/></Tooltip></Space></div></div><ReaderMediaPosition value={prefs.readerMediaPosition} enabled={placement==='side'&&!focus&&mediaVisible} onSave={async value=>{const saved=await persist({readerMediaPosition:value});if(saved)messageApi.success(trial?'位置已应用于本次试读':'媒体位置已保存');return saved}}/></section>:null
 const floatingMediaPanel=mediaPanel?<div className="reader-media-float">{mediaPanel}</div>:null
 const storyPanel=<section ref={storyRef} className="reader-story" aria-label="阅读正文" onScroll={()=>{if(!layoutAnchor.current)setLightLookupOpen(false);hoverEnd(hoverResume.current?.key)}}><div className="reader-sentences">{sentences.map((s,i)=><ReaderSentence key={s.id} sentence={s} index={i} active={i===active} spoken={i===active?activeWord:-1} selected={i===learningIndex} expanded={expandedTranslations.has(String(s.id))} showTranslation={Boolean(s.translation?.trim())} lookupIndex={lightLookupOpen&&String(wordInfo?.sentenceId)===String(s.id)?wordInfo?.wordIndex:-1} annotations={annotationIndex.get(String(s.id))} hasSource={Boolean(source)} trial={trial} actions={rowActions} sentenceRefs={sentenceRefs}/>)} {trial&&<div className="reader-trial-inline"><Tag color="gold">试读前 10%</Tag><Title level={4}>喜欢这本读物？加入书架继续阅读</Title><Paragraph type="secondary">加入后解锁完整正文与原音，并保存学习进度。</Paragraph><Button type="primary" loading={addingTrial} onClick={addTrialBook}>加入书架继续阅读</Button></div>}</div></section>
 return <div className={`modern-reader reader-media-${placement} ${!hasVisual||!mediaVisible?'reader-without-media':''} ${eye?'eye-comfort':''} ${focus?'focus-mode':''} density-${prefs.density} reader-study-workspace reader-flow-${readerFlowMode} ${!mediaVisible?'reader-media-hidden':''} ${focusMediaOpen?'reader-focus-media-open':''} ${toolsCollapsed?'reader-tools-closed':'reader-tools-open'}`} style={{'--reader-font-size':appearance.readerFontSize+'px','--reader-line-height':appearance.readerLineHeight,'--reader-content-width':appearance.readerContentWidth+'px'}} onClickCapture={event=>{if(event.detail>0){const button=event.target.closest?.('button');if(button)requestAnimationFrame(()=>button.blur())}}}>
  <header className="reader-head">
   <Button icon={<ArrowLeftOutlined/>} onClick={requestLeave}>返回</Button>
   <div className="reader-title-group"><Text className="reader-mode-kicker">{focus?'专注阅读':`精读工作台 · ${kind==='official'?'官方读物':'私人读物'}`}</Text><Title level={3}>{displayTitle}</Title><Text className="reader-save-status" role="status">{source?'播放位置':'阅读位置'} {active+1}/{sentences.length} 句 · {trial?'试读':finishing?'保存中…':completed?'本段已保存':session.saveError?'保存待重试':session.restored?'已恢复未保存片段':session.seconds>0?'本段未保存':'阅读位置自动保留'}</Text></div>
   <Space wrap className="reader-head-actions">
    {!focus&&<Tooltip title={eye?'关闭护眼配色':'开启护眼配色'}><Button className={`reader-eye-switch ${eye?'active':''}`} aria-label={eye?'关闭护眼配色':'开启护眼配色'} aria-pressed={eye} icon={<EyeOutlined/>} loading={preferenceSaving} onClick={()=>saveReaderPreference({eyeComfort:!eye},()=>setEye(!eye))}>护眼</Button></Tooltip>}
    <Button className="reader-appearance-button" aria-label="Aa 阅读设置" icon={<FontSizeOutlined/>} onClick={openAppearance}>Aa</Button>
    {trial&&<><Tag color="gold">试读前 10%</Tag><Button type="primary" loading={addingTrial} onClick={addTrialBook}>加入书架继续阅读</Button></>}
    {!focus&&!trial&&kind==='official'&&book?.inLibrary&&<Button danger loading={removingFromShelf} onClick={removeFromShelf}>移出书架</Button>}
    {!focus&&hasVisual&&!mediaVisible&&<Button icon={<EyeOutlined/>} onClick={()=>{setMediaVisible(true);setPlacement('side')}}>显示画面</Button>}
    {!focus&&<Button aria-expanded={!toolsCollapsed} aria-controls="reader-tools" icon={toolsCollapsed?<MenuUnfoldOutlined/>:<MenuFoldOutlined/>} onClick={()=>toolsCollapsed?showTools(panel):closeTools()}>{toolsCollapsed?'学习工具':'收起工具'}</Button>}
    {focus&&hasVisual&&<Button aria-pressed={focusMediaOpen} disabled={recording||shadowLoading} onClick={()=>setFocusMediaOpen(value=>!value)}>{focusMediaOpen?'收起原画面':'显示原画面'}</Button>}
    <Tooltip title={focus?'退出专注，恢复普通模式的学习布局':'进入专注，原音继续播放，工具按需展开'}><Button aria-label={focus?'退出专注模式':'进入专注模式'} aria-pressed={focus} icon={<AimOutlined/>} loading={preferenceSaving} className={`reader-focus-switch ${focus?'active':''}`} disabled={recording||shadowLoading} onClick={switchFocus}>{focus?'退出专注':'专注模式'}</Button></Tooltip>
    <Button className={`reader-finish-button ${completed?'completed':''}`} icon={<SaveOutlined/>} type={completed?'primary':'default'} loading={finishing} disabled={completed||trial} onClick={()=>finish()}>{completed?'本次已保存':'保存本次学习'}</Button>
   </Space>
  </header>
  {session.saveError&&<Alert className="reader-media-alert" type="error" showIcon message="学习记录尚未保存" description={session.saveError} action={<Button loading={finishing} onClick={()=>finish()}>重试保存</Button>}/>}
  {session.draftUnavailable&&<Alert className="reader-media-alert" type="warning" showIcon message="浏览器无法保留活动草稿，请在离开前保存本次学习。"/>}
  <Modal title="保存这一段再离开？" open={leaveOpen} onCancel={()=>{if(!finishing&&!savingWordDetails&&!savingWord)setLeaveOpen(false)}} closable={!finishing&&!savingWordDetails&&!savingWord} maskClosable={!finishing&&!savingWordDetails&&!savingWord} footer={<Space wrap><Button disabled={finishing||savingWordDetails||savingWord} onClick={()=>setLeaveOpen(false)}>继续学习</Button><Button danger disabled={finishing||savingWordDetails||savingWord} onClick={()=>{session.discard();editorDirty.current={meaning:false,note:false};goToWorkspace()}}>放弃本段并离开</Button><Button type="primary" loading={finishing||savingWordDetails} onClick={()=>finish(true)}>保存并离开</Button></Space>}><Paragraph>本段有 {learningDuration(session.seconds)} 学习活动尚未保存。保存后会计入学习空间。</Paragraph><Paragraph type="secondary">放弃仅丢弃本段活动和未提交备注，已收藏的生词与阅读位置仍保留。</Paragraph>{session.saveError&&<Alert type="error" message={session.saveError}/>}</Modal>
  <Modal title="这一段，积累已保存" open={summaryOpen} onCancel={continueAfterSave} footer={<Space wrap><Button onClick={continueAfterSave}>{source?'继续听读':'继续阅读'}</Button><Button onClick={()=>{location.href='/app?screen=workspace'}}>回学习空间</Button>{!!savedSession?.newWordIds.length&&<Button type="primary" onClick={()=>openReview({ids:savedSession.newWordIds.slice(0,100),size:5})}>复习本次新词</Button>}</Space>}><div className="reader-session-results"><div><b>{learningDuration(savedSession?.readingSeconds)}</b><span>本次学习活动时间</span></div><div><b>{savedSession?.sentences||0}</b><span>本次学习句子 · 按句去重</span></div><div><b>{savedSession?.newWordIds.length||0}</b><span>新收藏生词</span></div></div><Paragraph type="secondary">学习记录已保存，阅读位置会保留。活动时间按页面使用情况估算，不代表注意力或掌握程度。</Paragraph></Modal>
  {guideVisible&&<Alert className="reader-first-learning" showIcon type={completed&&vocab.length?'success':'info'} closable onClose={()=>setGuideVisible(false)} message={trial?'先试读，合适再加入书架':completed&&vocab.length?'已完成首次听读与生词保存':vocab.length?'生词已保存，听读结束后点击右上方保存本次学习':'听读一句，再保存一个生词'} description={trial?'试读使用原始媒体。加入书架后可查词、记录认识程度并保存学习。':completed&&vocab.length?'学习记录和生词已保存。下次回到学习空间，从上次位置继续。':source?'点击底部播放或复读按钮听原音；点击正文单词，选择“加入生词本”收藏；认识程度可稍后填写。':'阅读正文，点击单词并选择“加入生词本”。'} action={completed&&vocab.length?<Button href="/app">回到学习空间</Button>:undefined}/>}
  {mediaError&&<Alert closable type="warning" message={mediaError} onClose={()=>setMediaError('')} className="reader-media-alert"/>}
  {!book?.canWatchHdVideo&&media.videos.length>0&&!media.videos.some(item=>item.quality==='low')&&<Alert type="warning" showIcon message="此视频的流畅版本尚未就绪，免费版暂不能播放视频。" action={<Button size="small" onClick={()=>switchQuality(media.videos.find(item=>item.quality!=='low')?.url)}>开通高清</Button>} className="reader-media-alert"/>}
  {!video&&media.audio&&<audio ref={mediaRef} src={media.audio.url} preload="metadata" onEnded={mediaEnded} onSeeking={seeking} onSeeked={seeked} onTimeUpdate={sync} onLoadedMetadata={mediaLoaded} onRateChange={event=>setRate(event.currentTarget.playbackRate)} onPlay={e=>{if(recording||shadowLoading){e.currentTarget.pause();return}recordingPlaybackRef.current?.pause();setPlaying(true)}} onPause={()=>setPlaying(false)} onError={()=>setMediaError('音频加载失败，请检查媒体资源。')}/>}
  <Button className="reader-skip-tools" onClick={()=>{showTools(panel);requestAnimationFrame(()=>inspectorRef.current?.focus())}}>跳到阅读工具</Button>
  <div className="reader-workspace"><div className="reader-content-row">{placement==='side'&&mediaPanel}{placement==='top'?<main className="reader-reading-column">{floatingMediaPanel}{storyPanel}</main>:storyPanel}{!toolsCollapsed&&<aside id="reader-tools" tabIndex={-1} aria-label="阅读工具" ref={inspectorRef} className={'reader-inspector reader-panel-'+panel}><div className="reader-tools-heading"><Text strong>阅读工具</Text><Space>{!focus&&<Tooltip title="仅决定下次进入阅读器时是否默认展开；收起后仍可使用词卡查词"><Button type="text" size="small" aria-label="下次进入默认展开阅读工具" aria-pressed={toolsPinned} loading={preferenceSaving} icon={<PushpinOutlined/>} onClick={()=>saveReaderPreference({readerToolsPinned:!toolsPinned},()=>setToolsPinned(!toolsPinned))}>{toolsPinned?'已固定':'固定'}</Button></Tooltip>}<Button size="small" type="text" aria-label="收起阅读工具" icon={<CloseOutlined/>} onClick={closeTools}/></Space></div><div className="reader-learning-target"><Text>正在查看第 {toolIndex+1} 句</Text><Text type="secondary">{source?'播放':'阅读'}位置：第 {active+1} 句</Text><Space wrap><Button size="small" icon={<AimOutlined/>} onClick={()=>locateSentence(toolSentenceId)}>定位原句</Button>{panel!=='shadow'&&<Button size="small" onClick={()=>practiceSentence(toolSentenceId)}>练这一句</Button>}</Space></div><Tabs activeKey={panel} onChange={changePanel} items={tabs}/></aside>}</div></div>
  {toolsCollapsed&&lightLookupOpen&&wordInfo&&wordAnchor&&<div className={'reader-lookup-card '+(eye?'eye-comfort':'')} style={wordAnchor} role="dialog" aria-modal="false" aria-label={wordInfo.word+' 查词'}><Button className="reader-lookup-close" type="text" size="small" aria-label="关闭词卡" icon={<CloseOutlined/>} onClick={closeLookup}/><ReaderWordPanel {...wordProps} compact onLocate={()=>locateSentence(wordInfo.sentenceId)} onPractice={()=>practiceSentence(wordInfo.sentenceId)} onExpand={()=>{showTools('word');requestAnimationFrame(()=>inspectorRef.current?.focus())}}/></div>}
  {hoverWord&&!lightLookupOpen&&<ReaderHoverCard lookup={hoverWord}/>}
  <Modal className="reader-appearance-modal" title="Aa 阅读设置" open={appearanceOpen} onCancel={()=>{if(!appearanceSaving)setAppearanceOpen(false)}} onOk={()=>appearanceForm.submit()} okText={trial?'应用于本次试读':'保存阅读设置'} cancelText="取消" confirmLoading={appearanceSaving} closable={!appearanceSaving} maskClosable={!appearanceSaving}>
   <Form className="reader-appearance-form" form={appearanceForm} layout="vertical" onFinish={saveAppearance}>
    <Form.Item label="正文字号" name="readerFontSize"><Slider min={16} max={28} step={1} marks={{16:'16',20:'20',24:'24',28:'28'}}/></Form.Item>
    <Form.Item label="行间距" name="readerLineHeight"><Slider min={1.4} max={2.4} step={.1} marks={{1.4:'紧凑',1.8:'舒适',2.4:'宽松'}}/></Form.Item>
    <Form.Item label="正文最大宽度" name="readerContentWidth"><Slider min={560} max={1040} step={40} marks={{560:'窄',760:'适中',1040:'宽'}}/></Form.Item>
    <Form.Item label="阅读推进方式" name="readerFlowMode"><ReaderFlowControl/></Form.Item>
    <Form.Item label="点击单词自动发音" name="wordAutoPronounce" valuePropName="checked"><Switch/></Form.Item>
    <Form.Item label="悬停查词时暂停原音" name="wordHoverPause" valuePropName="checked"><Switch/></Form.Item>
    <Text type="secondary">两种模式共享排版设置。正文宽度受当前窗口和工具栏限制。</Text>
    <Button type="link" onClick={()=>{setAppearanceOpen(false);openQuickSettings()}}>查看快捷键设置</Button>
   </Form>
  </Modal>
  <Modal className="reader-quick-settings-modal" title="播放与快捷键设置" open={quickSettingsOpen} okText="保存并生效" cancelText="取消" confirmLoading={quickSettingsSaving} onOk={()=>quickSettingsForm.submit()} onCancel={()=>setQuickSettingsOpen(false)} destroyOnHidden>
   <Form form={quickSettingsForm} layout="vertical" onFinish={saveQuickSettings} className="reader-quick-settings-form">
    <div className="reader-shortcut-grid">
     <Form.Item label="上一句" name="shortcutPrevious"><Select options={KEY_OPTIONS}/></Form.Item>
     <Form.Item label="复读当前句" name="shortcutRepeat"><Select options={KEY_OPTIONS}/></Form.Item>
     <Form.Item label="下一句" name="shortcutNext"><Select options={KEY_OPTIONS}/></Form.Item>
     <Form.Item label="播放 / 暂停" name="shortcutPlay"><Select options={KEY_OPTIONS}/></Form.Item>
    </div>
    <div className="reader-auto-pause-setting"><div><Text strong>句末自动暂停</Text><Text type="secondary">每句播放结束后暂停，方便跟读和复述。</Text></div><Form.Item name="sentenceAutoPause" valuePropName="checked" noStyle><Switch checkedChildren="开" unCheckedChildren="关"/></Form.Item></div>
    <Text type="secondary" className="reader-shortcut-setting-note">四个快捷键不能重复；保存后当前阅读页面立即生效。</Text>
   </Form>
  </Modal>
  <Modal title="试读已结束" open={trialEnded} onCancel={()=>setTrialEnded(false)} footer={<Space><Button onClick={()=>{setTrialEnded(false);seekSentence(0,false)}}>回看试读</Button><Button type="primary" loading={addingTrial} onClick={addTrialBook}>加入书架继续阅读</Button></Space>}><Paragraph>你已体验这本读物前 10% 的内容。加入书架，即可从这里继续观看、听读和学习。</Paragraph><Text type="secondary">收藏数量按当前套餐规则计算；加入失败时可在此重试。</Text></Modal>
  <footer className="reader-player">
   {source?<>
   <div className="reader-player-main">
    <Space className="reader-player-buttons"><Tooltip title="上一句"><Button aria-label="上一句" shape="circle" icon={<FastBackwardOutlined/>} onClick={previous} disabled={active===0||recording||shadowLoading}/></Tooltip><Tooltip title={playing?'暂停':'播放原始媒体'}><Button className={`reader-primary-play ${playing?'is-playing':'is-paused'}`} type="primary" shape="circle" aria-label={playing?'暂停':'播放原始媒体'} icon={playing?<PauseOutlined/>:<CaretRightFilled/>} onClick={togglePlay} disabled={!source||recording||shadowLoading}/></Tooltip><Tooltip title="复读当前句"><Button aria-label="复读当前句" shape="circle" icon={<ReloadOutlined/>} onClick={repeat} disabled={!source||recording||shadowLoading}/></Tooltip><Tooltip title="下一句"><Button aria-label="下一句" shape="circle" icon={<FastForwardOutlined/>} onClick={next} disabled={recording||shadowLoading||(!trial&&active>=sentences.length-1)}/></Tooltip></Space>
    <Text className="reader-time">{clock(currentTime)}</Text>
    <Slider aria-label="原音播放进度" className="reader-timeline" min={0} max={Math.max(1,(trial?Number(book.duration):duration)||Number(book.duration)||endOf(sentences.at(-1))||1)} step={.05} value={Math.min(currentTime,duration||Number(book.duration)||currentTime)} tooltip={{formatter:clock}} disabled={recording||shadowLoading} onChange={value=>{practiceBoundary.current=null;pendingSeek.current=null;pausedSentence.current='';lastMediaTime.current=value;setCurrentTime(value);if(mediaRef.current)mediaRef.current.currentTime=value}}/>
    <Text className="reader-time">{clock(trial?Number(book.duration):duration||Number(book.duration))}</Text>
    {focus&&<Button type="text" aria-label="打开播放与快捷键设置" icon={<SettingOutlined/>} onClick={openQuickSettings}/>}
    <Select aria-label="播放速度" className="reader-rate" suffixIcon={null}
     placement="topRight" popupMatchSelectWidth={112} listHeight={208} virtual={false}
     value={rate} onChange={value=>{setRate(value);if(mediaRef.current)mediaRef.current.playbackRate=value;persist({playbackRate:value})}}
     options={[.5,.75,1,1.25,1.5,2].map(value=>({value,label:`${value}×`}))}/>
   </div>
   </>:<div className="reader-text-navigation"><div><Text strong>第 {active+1} / {sentences.length} 句</Text><Text type="secondary">{media.videos.length?'原音当前不可用，可继续阅读正文':'此材料未附原音 · 阅读位置自动保留'}</Text></div><Space><Button icon={<FastBackwardOutlined/>} disabled={active===0} onClick={previous}>上一句</Button><Button icon={<FastForwardOutlined/>} disabled={!trial&&active>=sentences.length-1} onClick={next}>下一句</Button></Space></div>}
   {!focus&&<div className="reader-player-shortcuts"><ControlOutlined aria-hidden="true"/><span><kbd>{prefs.shortcutPrevious==='space'?'空格':String(prefs.shortcutPrevious).replace('arrowleft','←').replace('arrowright','→').toUpperCase()}</kbd> 上一句 <kbd>{prefs.shortcutNext==='space'?'空格':String(prefs.shortcutNext).replace('arrowleft','←').replace('arrowright','→').toUpperCase()}</kbd> 下一句 <kbd>{prefs.shortcutPlay==='space'?'空格':String(prefs.shortcutPlay).replace('arrowleft','←').replace('arrowright','→').toUpperCase()}</kbd> 播放/暂停 <kbd>Q</kbd> 句末暂停 <span className={`reader-auto-pause-status ${autoPause?'is-on':'is-off'}`} role="img" aria-label={`句末暂停${autoPause?'已开启':'已关闭'}`} title={`句末暂停${autoPause?'已开启':'已关闭'}`}><PoweroffOutlined/></span></span><Tooltip title="查看和修改阅读快捷键"><Button type="text" size="small" onClick={openQuickSettings}><SettingOutlined/> 快捷键</Button></Tooltip></div>}
   {shortcutFeedback&&<div key={shortcutFeedback.id} className="reader-shortcut-feedback" role="status" aria-live="polite"><ControlOutlined aria-hidden="true"/><span>{shortcutFeedback.text}</span></div>}
  </footer>
 </div>
}
