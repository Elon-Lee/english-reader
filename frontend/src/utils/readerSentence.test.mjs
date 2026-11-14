import test from 'node:test'
import assert from 'node:assert/strict'
import {sentenceParts,wordIsSpoken,sentenceOnlyHighlight} from './readerSentence.mjs'

test('sentence 37 preserves punctuation, spaces and word indices',()=>{
  const text='The Stranger-man (and he was a Tewara) thought, "This is a very, very wonderful child.'
  const sentence={text,words:[...text.matchAll(/[A-Za-z]+(?:['’][A-Za-z]+)?|\d+/g)].map(m=>({text:m[0]}))}
  const parts=sentenceParts(sentence)
  assert.equal(parts.map(p=>p.text).join(''),text)
  assert.deepEqual(parts.filter(p=>p.wordIndex!==undefined).map(p=>p.wordIndex),sentence.words.map((_,i)=>i))
  assert.equal(sentenceParts({text:'No words.'})[0].text,'No words.')
})
test('incompatible historical tokens remain separated without losing lookup indices',()=>{
  const parts=sentenceParts({text:'a different transcript',words:[{text:'Hello',punctuationAfter:','},{text:'world',punctuationAfter:'!'}]})
  assert.equal(parts.map(p=>p.text).join(''),'Hello, world!')
  assert.deepEqual(parts.filter(p=>p.wordIndex!==undefined).map(p=>p.wordIndex),[0,1])
})
test('compound groups highlight together; existing untimed Kokoro sentences highlight as a sentence',()=>{
  const words=[{text:'The',start:0},{text:'Stranger',start:1,timingGroup:'compound'},{text:'man',start:1,timingGroup:'compound'},{text:'came',start:2}]
  assert.deepEqual(words.map((_,i)=>wordIsSpoken(words,i,2)),[false,true,true,false])
  assert.equal(wordIsSpoken(words,1,-1),false)
  const sentence={timingPolicy:'kokoro-sentence-audio',words:[{text:'Unknown'},{text:'name'}]}
  assert.equal(sentenceOnlyHighlight(sentence,true),true)
  assert.equal(sentenceOnlyHighlight(sentence,false),false)
  assert.equal(sentenceOnlyHighlight({...sentence,words},true),false)
  assert.equal(sentenceOnlyHighlight({...sentence,timingPolicy:'acoustic-only'},true),false)
})
