import test from 'node:test'
import assert from 'node:assert/strict'
import { blockParts, canReadExtensively, pageForOffset, readingBlocks, readingChapters } from './extensiveReading.mjs'

test('only authorized original PDFs and structured EPUBs support extensive reading', () => {
  assert.equal(canReadExtensively(null), false)
  for (const resourceType of ['audio', 'video', 'youtube', 'text', 'epub']) {
    assert.equal(canReadExtensively({ resourceType, mediaAssets: [{ contentType: 'audio/mpeg' }] }), false)
  }
  assert.equal(canReadExtensively({ mediaAssets: [{ contentType: 'application/pdf' }] }), true)
  assert.equal(canReadExtensively({ trial: true, mediaAssets: [{ contentType: 'application/pdf', variants: [{ contentType: 'audio/mpeg' }] }] }), false, 'paired audio does not authorize the full PDF in trial')
  assert.equal(canReadExtensively({ readingDocument: { version: 1, format: 'epub', blocks: [{ text: 'Original paragraph' }] } }), true)
  assert.equal(canReadExtensively({ readingDocument: { version: 1, format: 'pdf', blocks: [{}] } }), false, 'PDF trial without original asset cannot expose full pages')
  assert.equal(canReadExtensively({ readingDocument: { version: 1, format: 'txt', blocks: [{}] } }), false)
})

test('paragraph rendering preserves punctuation, newlines and Unicode code point offsets', () => {
  const block = { text: '🌿 “Hello,”\nworld!', words: [{ start: 3, end: 8, sentenceId: 's-1', wordIndex: 0 }, { start: 11, end: 16, sentenceId: 's-1', wordIndex: 1 }] }
  const parts = blockParts(block)
  assert.equal(parts.map(part => part.text).join(''), block.text)
  assert.equal(parts.find(part => part.wordIndex === 0).text, 'Hello')
  assert.equal(parts.find(part => part.wordIndex === 1).text, 'world')
})

test('column offsets retain the page at exact boundaries and account for gutters', () => {
  assert.equal(pageForOffset(0, 600), 0)
  assert.equal(pageForOffset(648, 600), 1)
  assert.equal(pageForOffset(1296, 600), 2)
  assert.equal(pageForOffset(-20, 600), 0)
})

test('new EPUB uses original blocks and historical books are only read without mutation', () => {
  const blocks = [{ id: 'b1', text: 'Chapter one', type: 'heading', section: 'a', words: [] }]
  assert.equal(readingBlocks({ readingDocument: { version: 1, blocks } }), blocks)
  const book = { sentences: [{ id: 'old', text: '“Hello,” she said.' }] }
  const before = JSON.stringify(book)
  const paragraphs = readingBlocks(book)
  assert.equal(blockParts(paragraphs[0]).map(p => p.text).join(''), book.sentences[0].text)
  assert.equal(JSON.stringify(book), before)
  assert.equal(readingChapters(blocks, 'Book')[0].title, 'Chapter one')
})
