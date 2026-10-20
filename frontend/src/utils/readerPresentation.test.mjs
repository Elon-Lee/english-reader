import test from 'node:test'
import assert from 'node:assert/strict'
import { readerAppearance, dictionaryGroups, sentenceIndex, sentencePlaybackRange, mediaSentenceIndex } from './readerPresentation.mjs'

test('appearance accepts supported values and replaces invalid persisted values', () => {
  assert.deepEqual(readerAppearance({ readerFontSize: 24, readerLineHeight: 2, readerContentWidth: 920 }), { readerFontSize: 24, readerLineHeight: 2, readerContentWidth: 920 })
  assert.deepEqual(readerAppearance({ readerFontSize: Infinity, readerLineHeight: 0, readerContentWidth: null }), readerAppearance())
})
test('dictionary removes duplicate generic translations while retaining distinct senses and parts of speech', () => {
  const groups = [{pos:'ANY',translations:['好奇心','奇事','好奇心']},{pos:'noun',translations:['好奇心','好奇心']},{pos:'verb',translations:['奇事']}]
  assert.deepEqual(dictionaryGroups(groups), [{pos:'noun',translations:['好奇心']},{pos:'verb',translations:['奇事']}])
  assert.equal(groups[0].translations.length, 3)
  assert.deepEqual(dictionaryGroups([{pos:'ANY',translations:['唯一释义']}]), [{pos:'ANY',translations:['唯一释义']}])
})
test('selected sentence resolves independently from playback fallback', () => {
  const sentences = [{id:1},{id:2},{id:3}]
  assert.equal(sentenceIndex(sentences,'2',2), 1)
  assert.equal(sentenceIndex(sentences,null,2), 2)
  assert.equal(sentenceIndex(sentences,'missing',20), 2)
})
test('practice requires real usable sentence boundaries and supports next start or media duration', () => {
  assert.deepEqual(sentencePlaybackRange([{start:0},{start:3,end:5}],0,8), {start:0,end:3})
  assert.deepEqual(sentencePlaybackRange([{start:3}],0,8), {start:3,end:8})
  assert.equal(sentencePlaybackRange([{text:'No timestamps'}],0,8), null)
  assert.equal(sentencePlaybackRange([{start:null,end:3}],0,8), null)
  assert.equal(sentencePlaybackRange([{start:4,end:2}],0,8), null)
})
test('media seeking resolves the first sentence, timestamp gaps and the final sentence', () => {
  const sentences = [{start:1,end:3},{start:5,end:7}]
  assert.equal(mediaSentenceIndex(sentences,0),0)
  assert.equal(mediaSentenceIndex(sentences,4),0)
  assert.equal(mediaSentenceIndex(sentences,6),1)
  assert.equal(mediaSentenceIndex(sentences,10),1)
  assert.equal(mediaSentenceIndex([{start:null},{text:'No timing'}],0),-1)
})
