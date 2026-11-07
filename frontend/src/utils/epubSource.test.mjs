import test from 'node:test'
import assert from 'node:assert/strict'
import { zipSync, strToU8 } from 'fflate'
import { archivePath, openEpubArchive } from './epubSource.mjs'

test('resolves only archive-contained relative resource paths', () => {
  assert.equal(archivePath('OPS/text/chapter.xhtml', '../images/picture.png'), 'OPS/images/picture.png')
  assert.equal(archivePath('OPS/a.xhtml', 'fonts/name%20one.woff'), 'OPS/fonts/name one.woff')
  for (const value of ['../../secret', '/api/auth/me', '//evil.test/x', 'https://evil.test', 'javascript:alert(1)', '%zz']) assert.equal(archivePath('OPS/a.xhtml', value), null)
})

test('rejects ZIP traversal and oversized entries before decompression', () => {
  assert.throws(() => openEpubArchive(zipSync({ '../outside.xhtml': strToU8('bad') })), /路径/)
  assert.throws(() => openEpubArchive(zipSync({ 'large.xhtml': new Uint8Array(21 * 1024 * 1024) })), /大小/)
})

test('encrypted books fail explicitly and archive disposal is safe', () => {
  assert.throws(() => openEpubArchive(zipSync({ 'META-INF/encryption.xml': strToU8('<encryption/>') })), /加密/)
  const book = openEpubArchive(zipSync({ 'chapter.xhtml': strToU8('<p>Original.</p>') }))
  book.close(); book.close()
})
