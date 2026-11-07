const assert = require('node:assert/strict')
const fs = require('node:fs')
const { zipSync, strToU8 } = require('fflate')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core')
const base = process.env.READER_TEST_BASE || 'http://127.0.0.1:4176'
const output = process.env.READER_TEST_OUTPUT || '/private/tmp/english-reader-source-browser'
const wordPattern = /[A-Za-z]+(?:['’][A-Za-z]+)?|\d+/g

function fixture(fixed = false) {
  const blocks = [], sentences = [], files = {}, spine = []
  for (let chapter = 0; chapter < 2; chapter++) {
    let body = `<h1>Chapter ${chapter + 1}</h1>`
    const values = [`Chapter ${chapter + 1}`, ...Array.from({ length: fixed ? 2 : 30 }, (_, i) => `“Original paragraph ${chapter}-${i},” she said. The careful reader follows the original spacing, illustrations and typography throughout the chapter. This paragraph keeps every sentence and its source location.`)]
    for (let i = 0; i < values.length; i++) {
      const id = `s-${sentences.length + 1}`, words = [...values[i].matchAll(wordPattern)]
      sentences.push({ id, text: values[i], section: `section-${chapter + 1}`, words: words.map(m => ({ text: m[0] })) })
      blocks.push({ id: `b-${blocks.length + 1}`, type: i ? 'paragraph' : 'heading', text: values[i], section: `section-${chapter + 1}`, words: words.map((m, wordIndex) => ({ start: m.index, end: m.index + m[0].length, sentenceId: id, wordIndex })) })
      if (i) body += `<p class="original" id="p-${i}">${values[i].replace('careful', '<em>careful</em>')}</p>`
    }
    const href = `OPS/chapter-${chapter}.xhtml`
    spine.push({ href, section: `section-${chapter + 1}`, layout: fixed ? 'fixed' : 'reflow' })
    files[href] = strToU8(`<html><head><meta name="viewport" content="width=600,height=900"/><link rel="stylesheet" href="styles/book.css"/></head><body>${body}<img id="illustration" src="images/one.svg"/><a href="chapter-${1 - chapter}.xhtml">Next chapter</a><script>parent.__epubExecuted=true</script><img src="https://epub-external.invalid/steal" onerror="parent.__epubExecuted=true"/><iframe src="/api/auth/me"></iframe><form action="/api/auth/logout"><input name="secret"/></form></body></html>`)
  }
  files['OPS/styles/book.css'] = strToU8('@import "nested.css"; body{font-family:Georgia,serif;font-size:19px;background:white}p.original{margin:0 0 23px;text-indent:31px;line-height:1.7}p.original>em{color:rgb(118,42,63)}#illustration{width:140px;height:70px}h1{font-size:26px}.external{background:url(https://epub-external.invalid/track)}')
  files['OPS/styles/nested.css'] = strToU8('p.original{text-align:justify} @font-face{font-family:SourceFixture;src:url(../fonts/regular.ttf)}')
  files['OPS/images/one.svg'] = strToU8('<svg xmlns="http://www.w3.org/2000/svg" width="140" height="70"><rect width="140" height="70" fill="#355b45"/></svg>')
  files['OPS/fonts/regular.ttf'] = new Uint8Array(fs.readFileSync('node_modules/pdfjs-dist/standard_fonts/LiberationSans-Regular.ttf'))
  return { archive: Buffer.from(zipSync(files)), book: { id: 'source-test', title: 'Original Source', sentences, duration: 0, mediaAssets: [{ id: 'source', contentType: 'application/epub+zip', url: '/api/media/source' }], readingDocument: { version: 1, format: 'epub', blocks, source: { version: 1, layout: fixed ? 'fixed' : 'reflow', spine } }, progress: {} } }
}

;(async () => {
  fs.mkdirSync(output, { recursive: true })
  const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true })
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } }), page = await context.newPage()
    let data = fixture(), unavailable = false, positionUnavailable = false
    const errors = [], writes = [], external = []
    page.on('pageerror', e => { errors.push(e.message); console.error('PAGE', e.message) })
    page.on('console', m => { if (m.type() === 'error') console.error('CONSOLE', m.text()) })
    page.on('request', r => { if (r.url().includes('epub-external.invalid')) external.push(r.url()) })
    await context.route(`${base}/api/**`, async route => {
      const request = route.request(), path = new URL(request.url()).pathname
      let result = {}
      if (path === '/api/auth/me') result = { user: { id: 'source-owner', role: 'user', displayName: 'Source test', email: 'source@example.test' } }
      else if (path === '/api/preferences') result = { focusMode: true }
      else if (path.endsWith('/reader')) result = { book: data.book }
      else if (path === '/api/media/source') return route.fulfill(unavailable ? { status: 403, body: 'Denied' } : { status: 200, contentType: 'application/epub+zip', body: data.archive })
      else if (path === '/api/workspace/progress') {
        if (positionUnavailable) return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: 'Position unavailable' }) })
        const payload = request.postDataJSON(); writes.push(payload)
        data.book.progress = { lastSentenceId: payload.lastSentenceId, readingLocation: payload.readingLocation || data.book.progress.readingLocation }
      } else if (path === '/api/word-context') result = { meaning: '原文语境' }
      else if (path === '/api/word-dictionary') result = { meanings: ['原文'] }
      else if (path.includes('vocabulary') || path.includes('annotations')) result = { items: [] }
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(result) })
    })
    const open = async () => {
      await page.goto(`${base}/app?screen=reader&id=source-test&reader=workspace`, { waitUntil: 'domcontentloaded' })
      await page.frameLocator('iframe[title="EPUB 原文书页"]').locator('p.original').first().waitFor({ timeout: 15000 })
      await page.getByRole('button', { name: '下一页', exact: true }).waitFor()
      await page.waitForFunction(() => document.querySelector('iframe[title="EPUB 原文书页"]')?.style.visibility === 'visible')
    }
    await open()
    const frame = page.frames().find(f => f !== page.mainFrame())
    assert.equal(await frame.locator('p.original').count(), 30)
    assert.equal(await frame.locator('p.original>em').first().textContent(), 'careful')
    const styles = await frame.locator('p.original').first().evaluate(n => { const s = getComputedStyle(n); return [s.textIndent, s.marginBottom, s.textAlign] })
    assert.deepEqual(styles, ['31px', '23px', 'justify'])
    assert.equal(await frame.locator('script,iframe,form,input').count(), 0)
    assert.equal(await page.evaluate(() => window.__epubExecuted), undefined)
    assert.deepEqual(external, [])
    assert.equal(await frame.locator('#illustration').evaluate(n => n.complete && n.naturalWidth), 140)
    assert.ok(await frame.locator('style').evaluateAll(nodes => nodes.some(n => n.textContent.includes('font-face') && n.textContent.includes('blob:'))))
    await frame.locator('p.original>em').first().click()
    await page.getByRole('dialog', { name: 'careful 查词' }).waitFor()
    await page.getByRole('button', { name: '查看更多用法', exact: true }).click()
    await page.locator('.reader-title-group h3').click()
    await page.keyboard.press('ArrowRight')
    assert.equal(await page.getByRole('spinbutton', { name: '跳转页码' }).inputValue(), '2')
    await page.getByRole('button', { name: /定位原句/ }).click()
    await page.waitForFunction(() => document.querySelector('[aria-label="跳转页码"]').value === '1')
    await page.getByRole('button', { name: '收起阅读工具', exact: true }).click()
    await page.screenshot({ path: `${output}/original-epub.png` })
    positionUnavailable = true
    await page.getByRole('button', { name: '下一页', exact: true }).click()
    await page.getByRole('button', { name: '重试保存进度', exact: true }).waitFor()
    positionUnavailable = false
    await page.getByRole('button', { name: '重试保存进度', exact: true }).click()
    await page.getByText('进度已保存', { exact: true }).waitFor()
    assert.ok(writes.at(-1).readingLocation.offset > 0)
    const pageNumber = await page.getByRole('spinbutton', { name: '跳转页码' }).inputValue()
    await page.getByRole('button', { name: '退出泛读模式' }).click()
    await page.getByRole('button', { name: '进入泛读模式' }).click()
    await page.waitForFunction(() => document.querySelector('iframe[title="EPUB 原文书页"]')?.style.visibility === 'visible')
    assert.equal(await page.getByRole('spinbutton', { name: '跳转页码' }).inputValue(), pageNumber)
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.waitForFunction(() => document.querySelector('iframe[title="EPUB 原文书页"]')?.style.visibility === 'visible')
    assert.equal(await page.getByRole('spinbutton', { name: '跳转页码' }).inputValue(), pageNumber)
    await page.setViewportSize({ width: 1280, height: 820 })
    await page.waitForTimeout(600)
    assert.ok(data.book.progress.readingLocation.offset >= 0)
    await page.screenshot({ path: `${output}/after-resize.png` })
    const chapterSaved = page.waitForRequest(request => request.url().endsWith('/api/workspace/progress') && request.method() === 'POST' && request.postDataJSON().readingLocation?.chapter === 1)
    await page.getByRole('button', { name: '目录', exact: true }).click()
    await page.getByRole('navigation', { name: '章节目录' }).getByRole('button').nth(1).click()
    await chapterSaved
    await page.getByText('进度已保存', { exact: true }).waitFor()
    assert.equal(data.book.progress.readingLocation.chapter, 1)
    // An explicit learning link takes priority over a previously saved chapter.
    await page.goto(`${base}/app?screen=reader&id=source-test&reader=workspace&sentence=s-2`, { waitUntil: 'domcontentloaded' })
    await page.waitForFunction(() => document.querySelector('iframe[title="EPUB 原文书页"]')?.style.visibility === 'visible')
    assert.equal(await page.frameLocator('iframe[title="EPUB 原文书页"]').locator('h1').textContent(), 'Chapter 1')
    assert.equal(await page.getByRole('spinbutton', { name: '跳转页码' }).inputValue(), '1')
    // Fixed-layout pages keep their declared canvas and one spine item per page.
    data = fixture(true); await open()
    assert.match(await page.locator('.source-reader').innerText(), /原文第 1 \/ 2 页/)
    const canvas = await page.locator('iframe[title="EPUB 原文书页"]').evaluate(n => [n.style.width, n.style.height])
    assert.deepEqual(canvas, ['600px', '900px'])
    await page.getByRole('button', { name: '下一页', exact: true }).click()
    await page.waitForTimeout(700)
    assert.match(await page.locator('.source-reader').innerText(), /原文第 2 \/ 2 页/)
    await page.screenshot({ path: `${output}/fixed-epub.png` })
    unavailable = true
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.getByText('原版书页加载失败', { exact: true }).waitFor()
    unavailable = false
    await page.getByRole('button', { name: '重新加载', exact: true }).click()
    await page.waitForFunction(() => document.querySelector('iframe[title="EPUB 原文书页"]')?.style.visibility === 'visible')
    assert.deepEqual(errors, [])
    assert.deepEqual(external, [])
    console.log('PASS: original DOM/CSS/imported styles/images/fonts, sandbox and network isolation, exact position persistence/retry, chapter navigation, fixed original canvas/pages, load failure/retry; no page exceptions')
  } catch (error) { console.error(error); throw error } finally { await browser.close() }
})().catch(() => { process.exitCode = 1 })
