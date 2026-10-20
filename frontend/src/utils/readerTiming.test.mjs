import test from 'node:test'
import assert from 'node:assert/strict'
import {buildReaderTimeline,timelineSentence,timelineWord,mediaSeconds,sentenceEnd,crossedSentenceEnd,playReaderMedia} from './readerTiming.mjs'

test('missing timestamps do not become zero or create playable sentences',()=>{
  for(const value of [null,undefined,'','bad',Infinity])assert.equal(mediaSeconds(value),null)
  assert.equal(mediaSeconds(0),0)
  assert.equal(sentenceEnd({end:null},{start:3}),3)
  assert.equal(timelineSentence(buildReaderTimeline([{start:null},{text:'text only'}]),0),-1)
})
test('sentence lookup handles intro, gaps, exact boundaries, backward seeks and final tail',()=>{
  const timeline=buildReaderTimeline([{start:1,end:2},{start:5,end:7},{start:9,end:10}])
  for(const [time,index] of [[0,0],[4,0],[5,1],[10,2],[1.5,0],[9,2],[7,1]])assert.equal(timelineSentence(timeline,time),index)
})
test('absolute word timestamps before sentence start never receive a guessed sentence offset',()=>{
  const timeline=buildReaderTimeline([{start:100,end:103,words:[{start:99.6,end:100.2},{start:100.3,end:101}]}])
  assert.equal(timelineWord(timeline,0,100),0)
  assert.equal(timelineWord(timeline,0,100.3),1)
})
test('short words switch at their own start even with overlapping end times',()=>{
  const timeline=buildReaderTimeline([{start:10,end:12,words:[{start:10,end:11},{start:10.06,end:10.12},{start:10.13,end:10.2}]}])
  assert.equal(timelineWord(timeline,0,9.99),-1)
  assert.equal(timelineWord(timeline,0,10.07),1)
  assert.equal(timelineWord(timeline,0,10.14),2)
  assert.equal(timelineWord(timeline,0,11.5),2)
})
test('untimed words are estimated only when timing is missing; aliases remain supported',()=>{
  const timeline=buildReaderTimeline([{start:10,end:14,words:[{startTime:10.2,endTime:11},{start:null,end:null},{text:'last'}]}])
  assert.equal(timelineWord(timeline,0,10),-1)
  assert.equal(timelineWord(timeline,0,10.3),0)
  assert.equal(timelineWord(timeline,0,11.5),1)
  assert.equal(timelineWord(timeline,0,13),2)
})
test('unsorted timestamps retain original sentence and word indices',()=>{
  const timeline=buildReaderTimeline([{start:8},{start:2,words:[{start:3},{start:2}]}])
  assert.equal(timelineSentence(timeline,2.5),1)
  assert.equal(timelineWord(timeline,1,2.5),1)
  assert.equal(timelineWord(timeline,1,3.5),0)
})
test('sentence pause waits for the real end and excludes seeks, pauses and duplicate stops',()=>{
  const sample={previous:4.95,time:5,end:5,playing:true,seeking:false,paused:false}
  assert.equal(crossedSentenceEnd(sample),true)
  for(const change of [{time:4.99},{seeking:true},{playing:false},{paused:true},{previous:5},{end:null}])assert.equal(crossedSentenceEnd({...sample,...change}),false)
  assert.equal(crossedSentenceEnd({...sample,previous:1,time:6}),true)
})
test('large timelines resolve exact positions without changing source data',()=>{
  const sentences=Array.from({length:10000},(_,i)=>({start:i*5,end:i*5+4,words:[{start:i*5},{start:i*5+2}]}))
  const timeline=buildReaderTimeline(sentences)
  for(let i=9999;i>=0;i-=13){assert.equal(timelineSentence(timeline,i*5+2.5),i);assert.equal(timelineWord(timeline,i,i*5+2.5),1)}
  assert.equal(sentences[0].words[0].end,undefined)
})

test('rapid pause cancellation stays silent but real playback failures are reported',async()=>{
  const errors=[]
  for(const name of ['AbortError','NotAllowedError','NotSupportedError'])await playReaderMedia({play:()=>Promise.reject({name})},error=>errors.push(error.name))
  assert.deepEqual(errors,['NotAllowedError','NotSupportedError'])
})
