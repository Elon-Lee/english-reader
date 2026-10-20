import test from 'node:test'
import assert from 'node:assert/strict'
import { createReaderRequests, createReaderDraftStore, readerWordMeaning } from './readerLearning.mjs'

function deferred() { let resolve,reject; const promise=new Promise((yes,no)=>{resolve=yes;reject=no}); return {promise,resolve,reject} }
function storage() { const values=new Map(); return {values,getItem:key=>values.get(key),setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)} }

test('dictionary renders before a slow context service and survives its failure',async()=>{
  const requests=createReaderRequests(),context=deferred(),shown=[]
  requests.select()
  const slow=requests.run('context',()=>context.promise,value=>shown.push(value),error=>shown.push(error.message))
  await requests.run('dictionary',async()=>({meaning:'garden'}),value=>shown.push(value),()=>assert.fail())
  assert.deepEqual(shown,[{meaning:'garden'}])
  context.reject(new Error('context unavailable'));await slow
  assert.deepEqual(shown,[{meaning:'garden'},'context unavailable'])
})
test('older words and older retries cannot overwrite the current selection',async()=>{
  const requests=createReaderRequests(),old=deferred(),retry=deferred(),shown=[]
  requests.select();const first=requests.run('context',()=>old.promise,value=>shown.push(value),()=>assert.fail())
  requests.select();const second=requests.run('context',()=>retry.promise,value=>shown.push(value),()=>assert.fail())
  await requests.run('context',async()=>'newest',value=>shown.push(value),()=>assert.fail())
  old.resolve('old word');retry.resolve('old retry');await Promise.all([first,second])
  assert.deepEqual(shown,['newest'])
})
test('saved private meaning wins and dictionary fallback stays available without AI',()=>{
  const info={context:{meaning:'context'},dictionary:{groups:[{translations:['dictionary']}]}}
  assert.equal(readerWordMeaning(info,{payload:{meaning:'private'}}),'private')
  assert.equal(readerWordMeaning(info),'context')
  assert.equal(readerWordMeaning({dictionary:info.dictionary}),'dictionary')
  assert.equal(readerWordMeaning({}),'')
})
test('draft recovery preserves frozen retry payload and separates account, book and kind',()=>{
  const memory=storage(),draft=createReaderDraftStore(memory,'alice','book','workspace')
  const pending={bookId:'book',readingSeconds:42,lastSentenceId:'s2',idempotencyKey:'modern-reader-fixed'}
  assert.equal(draft.write({seconds:42.8,visited:['s1','s2'],newWordIds:['v1'],counters:{lookups:2},pending}),true)
  assert.deepEqual(draft.read().pending,pending)
  assert.equal(createReaderDraftStore(memory,'bob','book','workspace').read(),null)
  assert.equal(createReaderDraftStore(memory,'alice','other','workspace').read(),null)
  assert.equal(createReaderDraftStore(memory,'alice','book','official').read(),null)
  draft.clear();assert.equal(draft.read(),null)
})
test('corrupt, expired and foreign pending drafts are rejected',()=>{
  const memory=storage(),draft=createReaderDraftStore(memory,'alice','book','workspace')
  draft.write({seconds:2,visited:['s1'],newWordIds:[]})
  const key=[...memory.values.keys()][0],valid=JSON.parse(memory.getItem(key))
  for(const invalid of [{...valid,seconds:-1},{...valid,ownerId:'bob'},{...valid,updatedAt:0},{...valid,updatedAt:'invalid'},{...valid,counters:'invalid'},{...valid,counters:{lookups:-1}},{...valid,pending:{bookId:'foreign',readingSeconds:2,idempotencyKey:'modern-reader-key'}}]){
    memory.setItem(key,JSON.stringify(invalid));assert.equal(draft.read(),null)
  }
  memory.setItem(key,'broken json');assert.equal(draft.read(),null)
})
test('storage restrictions fail safely and expose unsuccessful persistence',()=>{
  const blocked={getItem(){throw Error('blocked')},setItem(){throw Error('quota')},removeItem(){throw Error('blocked')}}
  const draft=createReaderDraftStore(blocked,'alice','book','workspace')
  assert.equal(draft.read(),null);assert.equal(draft.write({}),false);assert.doesNotThrow(()=>draft.clear())
})
