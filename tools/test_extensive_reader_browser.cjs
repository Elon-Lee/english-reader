// Isolated browser contract test; all API responses belong to this test context.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core')
const base = process.env.READER_TEST_BASE || 'http://127.0.0.1:4173'
const output = process.env.READER_TEST_OUTPUT || '/private/tmp/english-reader-extensive-check'

function fixture() {
  if (process.env.READER_TEST_BOOK) return JSON.parse(fs.readFileSync(process.env.READER_TEST_BOOK, 'utf8'))
  const sentences = [], blocks = []
  for (let i = 0; i < 90; i++) {
    const text = i % 30 === 0 ? `Chapter ${i / 30 + 1}` : `“Reading keeps the original punctuation,” she said. This paragraph ${i} continues across the paper with enough natural words to check pagination and preserve the original document structure.`
    const id = `s-${i + 1}`, tokens = [...text.matchAll(/[A-Za-z]+(?:['’][A-Za-z]+)?|\d+/g)]
    sentences.push({ id, text, start: i * 2, end: i * 2 + 1.8, words: tokens.map(m => ({ text: m[0] })) })
    blocks.push({ id: `b-${i}`, text, type: i % 30 === 0 ? 'heading' : 'paragraph', section: `section-${Math.floor(i / 30)}`, words: tokens.map((m, wordIndex) => ({ start: m.index, end: m.index + m[0].length, sentenceId: id, wordIndex })) })
  }
  return { id: 'test-book', title: 'A Place for Reading', duration: 200, sentences, readingDocument: { version: 1, format: 'epub', blocks }, mediaAssets: [{ id: 'audio', contentType: 'audio/wav', url: '/api/media/test-audio' }], progress: {} }
}

function pdfFixture() {
  const objects = [null, '<< /Type /Catalog /Pages 2 0 R >>', '<< /Type /Pages /Kids [3 0 R 5 0 R 7 0 R] /Count 3 >>']
  for (let i = 0; i < 3; i++) {
    const text = i === 1 ? '' : `BT /F1 22 Tf 50 700 Td (Original PDF page ${i + 1}) Tj ET`
    objects.push(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 9 0 R >> >> /Contents ${4 + i * 2} 0 R >>`)
    objects.push(`<< /Length ${text.length} >>\nstream\n${text}\nendstream`)
  }
  objects.push('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')
  let pdf = '%PDF-1.4\n', offsets = [0]
  for (let i = 1; i < objects.length; i++) { offsets.push(Buffer.byteLength(pdf)); pdf += `${i} 0 obj\n${objects[i]}\nendobj\n` }
  const xref = Buffer.byteLength(pdf)
  pdf += `xref\n0 ${objects.length}\n0000000000 65535 f \n${offsets.slice(1).map(n => `${String(n).padStart(10, '0')} 00000 n \n`).join('')}trailer\n<< /Size ${objects.length} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`
  return Buffer.from(pdf)
}

function audioFixture() {
  const buffer = Buffer.alloc(44 + 16000 * 2)
  buffer.write('RIFF'); buffer.writeUInt32LE(buffer.length - 8, 4); buffer.write('WAVEfmt ', 8); buffer.writeUInt32LE(16, 16); buffer.writeUInt16LE(1, 20); buffer.writeUInt16LE(1, 22); buffer.writeUInt32LE(16000, 24); buffer.writeUInt32LE(32000, 28); buffer.writeUInt16LE(2, 32); buffer.writeUInt16LE(16, 34); buffer.write('data', 36); buffer.writeUInt32LE(buffer.length - 44, 40)
  return buffer
}

;(async () => {
  fs.mkdirSync(output, { recursive: true })
  const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true, args: ['--autoplay-policy=no-user-gesture-required'] })
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
    const page = await context.newPage(), errors = [], progress = [], calls = []
    let book = fixture(), pdfUnavailable = false, positionUnavailable = false, prefs = { focusMode: true, readerFontSize: 20, readerLineHeight: 1.8, readerContentWidth: 760, wordAutoPronounce: true }
    page.on('pageerror', error => { errors.push(error.message); console.error('BROWSER', error.message) })
    page.on('console', message => { if (message.type() === 'error') console.error('CONSOLE', message.text()) })
    page.on('requestfailed', request => console.error('NETWORK', request.url(), request.failure()?.errorText))
    await context.route(`${base}/api/**`, async route => {
      const request = route.request(), url = new URL(request.url()), path = url.pathname
      calls.push(path)
      let response = {}
      if (path === '/api/auth/me') response = { user: { id: 'browser-test', displayName: 'Reader test', email: 'reader@example.test', role: 'user' } }
      else if (path === '/api/preferences') {
        if (request.method() === 'POST') { Object.assign(prefs, request.postDataJSON()); response = { preferences: prefs } } else response = prefs
      } else if (path.endsWith('/reader')) response = { book }
      else if (path === '/api/workspace/progress' && positionUnavailable) return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: 'Test position storage failure' }) })
      else if (path === '/api/workspace/progress') { progress.push(request.postDataJSON()); response = { status: 'saved' } }
      else if (path === '/api/media/test-pdf') return route.fulfill(pdfUnavailable ? { status: 503, body: 'Unavailable' } : { status: 200, contentType: 'application/pdf', body: pdfFixture() })
      else if (path === '/api/media/test-audio') return route.fulfill({ status: 200, contentType: 'audio/wav', body: audioFixture() })
      else if (path === '/api/word-context') response = { meaning: '本句释义' }
      else if (path === '/api/word-dictionary') response = { word: url.searchParams.get('word'), meanings: ['词典释义'] }
      else if (path.includes('vocabulary') || path.includes('annotations')) response = { items: [] }
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(response) })
    })
    const open = async (id, trial=false) => { await page.goto(`${base}/app?screen=reader&id=${id}&reader=${trial?'official':'workspace'}${trial?'&trial=1':''}`); try { await page.getByRole('button', { name: /进入泛读模式|退出泛读模式/ }).waitFor({ timeout: 15000 }) } catch (error) { await page.screenshot({ path: `${output}/failure.png` }); console.error((await page.locator('body').innerText()).slice(0, 2500)); throw error } }
    await open('epub')
    await page.waitForFunction(() => document.querySelector('.extensive-flow')?.style.visibility === 'visible')
    assert.equal(await page.locator('.reader-player').count(), 0)
    assert.equal(await page.locator('.extensive-flow > p,.extensive-flow > h1,.extensive-flow > h2').count(), book.readingDocument.blocks.length)
    assert.equal(await page.locator('.extensive-flow > p,.extensive-flow > h1,.extensive-flow > h2').nth(3).textContent(), book.readingDocument.blocks[3].text)
    await page.screenshot({ path: `${output}/epub.png` })
    positionUnavailable = true
    await page.getByRole('button', { name: '下一页', exact: true }).click()
    await page.getByRole('button', { name: '重试保存进度', exact: true }).waitFor()
    positionUnavailable = false
    await page.getByRole('button', { name: '重试保存进度', exact: true }).click()
    await page.getByText('进度已保存', { exact: true }).waitFor()
    assert.equal(await page.getByRole('spinbutton', { name: '跳转页码' }).inputValue(), '2')
    await page.keyboard.press('ArrowRight')
    assert.equal(await page.getByRole('spinbutton', { name: '跳转页码' }).inputValue(), '3')
    await page.waitForFunction(() => !document.querySelector('.book-turn-leaf'))
    const savedId = progress.at(-1)?.lastSentenceId
    assert.ok(savedId)
    // Reflow keeps a word on the previously visible page anchored after a font change.
    await page.getByRole('button', { name: '阅读设置', exact: true }).click()
    await page.locator('.reader-appearance-modal .ant-slider').first().click({ position: { x: 300, y: 6 } })
    await page.getByRole('button', { name: '保存阅读设置', exact: true }).click()
    await page.waitForTimeout(300)
    await page.setViewportSize({ width: 1280, height: 820 })
    await page.waitForTimeout(200)
    const anchored = await page.evaluate(id => {
      const viewport = document.querySelector('.extensive-viewport').getBoundingClientRect()
      return [...document.querySelectorAll(`[data-sentence-id="${id}"]`)].some(node => {
        const rect = node.getBoundingClientRect(); return rect.left >= viewport.left - 1 && rect.right <= viewport.right + 1
      })
    }, savedId)
    assert.equal(anchored, true)
    assert.equal(await page.locator('audio').evaluate(el => el.paused), true)
    await page.keyboard.press('s'); await page.keyboard.press('q')
    assert.equal(await page.locator('audio').evaluate(el => el.paused), true)
    // Click an actually visible word, preserving real lookup sentence/word IDs.
    const word = await page.locator('.extensive-word').evaluateAll(nodes => {
      const bounds = document.querySelector('.extensive-viewport').getBoundingClientRect()
      const node = nodes.find(n => { const r = n.getBoundingClientRect(); return r.left >= bounds.left && r.right <= bounds.right && r.top >= bounds.top && r.bottom < bounds.bottom })
      return node?.dataset.readingWord
    })
    const lookupWord = page.locator(`[data-reading-word="${word}"]`)
    // CDP box models can report an earlier fragment for an inline in CSS columns.
    // Click the visible DOM rectangle, matching a user's actual mouse position.
    const lookupBox = await lookupWord.evaluate(node => node.getBoundingClientRect().toJSON())
    assert.ok(lookupBox && lookupBox.x >= 0 && lookupBox.y >= 0 && lookupBox.x + lookupBox.width <= 1280 && lookupBox.y + lookupBox.height <= 820, JSON.stringify(lookupBox))
    await page.mouse.click(lookupBox.x + lookupBox.width / 2, lookupBox.y + lookupBox.height / 2)
    try { await page.getByRole('dialog', { name: /查词/ }).waitFor() } catch (error) {
      await page.screenshot({ path: `${output}/lookup-failure.png` })
      console.error('LOOKUP', await page.evaluate(({ x, y }) => ({ hit: document.elementFromPoint(x, y)?.outerHTML.slice(0,500), text: document.body.innerText.slice(-1200) }), { x: lookupBox.x + lookupBox.width / 2, y: lookupBox.y + lookupBox.height / 2 }))
      throw error
    }
    assert.ok(calls.includes('/api/word-context'))
    assert.equal(calls.includes('/api/word-tts'), false, 'extensive lookup must not automatically pronounce')
    await page.getByRole('button', { name: '关闭词卡' }).click()
    await page.getByRole('button', { name: /目\s*录/, exact: false }).first().click()
    await page.locator('.extensive-contents nav button').last().click()
    await page.screenshot({ path: `${output}/epub-chapter.png` })
    await page.getByRole('button', { name: '退出泛读模式' }).click()
    await page.locator('.reader-player').waitFor()
    await page.locator('audio').evaluate(el => el.play())
    await page.getByRole('button', { name: '进入泛读模式' }).click()
    assert.equal(await page.locator('audio').evaluate(el => el.paused), true)
    // Unsupported resource types stay in normal mode even with default extensive enabled.
    for (const resourceType of ['audio', 'video', 'youtube', 'text', 'epub']) {
      book = { ...fixture(), resourceType, readingDocument: undefined }
      prefs.focusMode = true
      await open(resourceType)
      assert.equal(await page.getByRole('button', { name: '进入泛读模式' }).isDisabled(), true)
      assert.equal(await page.locator('.extensive-reader').count(), 0)
    }
    book = fixture()
    const previewBlocks = book.readingDocument.blocks.slice(0, 4)
    const previewIds = new Set(previewBlocks.flatMap(block => block.words.map(word => word.sentenceId)))
    book = { ...book, trial: true, sentences: book.sentences.filter(sentence => previewIds.has(sentence.id)), readingDocument: { ...book.readingDocument, blocks: previewBlocks } }
    const progressBeforeTrial = progress.length
    await open('epub-trial', true)
    await page.locator('.extensive-reader').waitFor()
    await page.getByText('试读进度不保存', { exact: true }).waitFor()
    assert.equal(await page.locator('.extensive-trial-end').count(), 1)
    assert.equal(progress.length, progressBeforeTrial)
    book = { ...book, readingDocument: { version: 1, format: 'pdf', blocks: [] }, mediaAssets: [{ contentType: 'application/pdf', url: '/api/media/test-pdf', variants: [{ contentType: 'audio/wav', url: '/api/media/test-audio' }] }] }
    await open('pdf-trial', true)
    assert.equal(await page.getByRole('button', { name: '进入泛读模式' }).isDisabled(), true)
    assert.equal(await page.locator('.extensive-reader').count(), 0)
    const pdfSentences = [1, 3].map(page => ({ id: `pdf-${page}`, text: `Original PDF page ${page}`, page, words: ['Original', 'PDF', 'page', String(page)].map(text => ({ text })) }))
    const pdfBlocks = pdfSentences.map(sentence => ({ text: sentence.text, page: sentence.page, words: sentence.words.map((_, wordIndex) => ({ sentenceId: sentence.id, wordIndex })) }))
    book = { id: 'pdf', title: 'Original pages', sentences: pdfSentences, readingDocument: { version: 1, format: 'pdf', blocks: pdfBlocks }, mediaAssets: [{ contentType: 'application/pdf', url: '/api/media/test-pdf' }], progress: {} }
    prefs.focusMode = true
    await open('pdf')
    await page.locator('.extensive-pdf-page:visible').waitFor()
    await page.getByText('Original PDF page 1', { exact: true }).waitFor()
    assert.match(await page.locator('.extensive-page-info').textContent(), /\/3页/)
    const originalWord = await page.locator('.textLayer span').first().evaluate(node => {
      const range = document.createRange(); range.setStart(node.firstChild, 0); range.setEnd(node.firstChild, 'Original'.length)
      return range.getBoundingClientRect().toJSON()
    })
    const lookupCalls = calls.filter(path => path === '/api/word-context').length
    await page.mouse.move(originalWord.x + originalWord.width / 2, originalWord.y + originalWord.height / 2)
    await page.waitForFunction(() => CSS.highlights.get('reader-word-hover')?.size === 1 && [...document.querySelectorAll('.textLayer span')].some(node => node.style.cursor === 'pointer'))
    await page.mouse.click(originalWord.x + originalWord.width / 2, originalWord.y + originalWord.height / 2)
    await page.getByRole('dialog', { name: /查词/ }).waitFor()
    assert.ok(calls.filter(path => path === '/api/word-context').length > lookupCalls)
    await page.getByRole('button', { name: '关闭词卡' }).click()
    await page.getByRole('button', { name: '下一页', exact: true }).click()
    await page.waitForFunction(() => document.querySelector('.book-turn-leaf')?.getAnimations().length > 0)
    await page.locator('[aria-label="PDF 原文第 2 页"]:visible').waitFor()
    assert.equal(await page.evaluate(() => CSS.highlights.has('reader-word-hover')), false)
    assert.equal(await page.locator('.textLayer span').count(), 0)
    await page.getByText('进度已保存', { exact: true }).waitFor()
    assert.deepEqual(progress.at(-1).readingLocation, { format: 'pdf', page: 2 })
    await page.getByRole('button', { name: '退出泛读模式' }).click()
    await page.getByRole('button', { name: '进入泛读模式' }).click()
    await page.locator('[aria-label="PDF 原文第 2 页"]:visible').waitFor()
    book.progress = { lastSentenceId: progress.at(-1).lastSentenceId, readingLocation: progress.at(-1).readingLocation }
    await open('pdf-blank-restored')
    await page.locator('[aria-label="PDF 原文第 2 页"]:visible').waitFor()
    assert.equal(await page.locator('.textLayer span').count(), 0)
    await page.getByRole('button', { name: '下一页', exact: true }).click()
    await page.getByText('Original PDF page 3', { exact: true }).waitFor()
    await page.screenshot({ path: `${output}/pdf-page3.png` })
    assert.equal(await page.getByRole('button', { name: '下一页', exact: true }).isDisabled(), true)
    pdfUnavailable = true
    book.progress = {}
    await open('pdf-retry')
    await page.getByText('原文页面加载失败', { exact: true }).waitFor()
    pdfUnavailable = false
    await page.getByRole('button', { name: '重新加载', exact: true }).click()
    await page.getByText('Original PDF page 1', { exact: true }).waitFor()
    assert.deepEqual(errors, [])
    console.log('PASS: EPUB paragraphs, pagination, reflow anchors, lookup, no audio sync, resource guards, PDF original pages including blank page; zero browser exceptions')
  } finally { await browser.close() }
})().catch(error => { console.error(error); process.exitCode = 1 })
