const assert = require('node:assert/strict')
const fs = require('node:fs')
const { zipSync, strToU8 } = require('fflate')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core')
const base = process.env.READER_TEST_BASE || 'http://127.0.0.1:4173'
const output = process.env.READER_TEST_OUTPUT || '/private/tmp/english-reader-interactions/browser'

function fixture(kind) {
  const blocks = [], sentences = []
  let body = ''
  for (let chapter = 1; chapter <= 2; chapter++) {
    body += `<h2 id="chapter-${chapter}">CHAPTER ${chapter}</h2>`
    for (let i = 0; i < 20; i++) {
      const text = i ? `Original paragraph ${chapter} number ${i}. The careful reader follows every word and keeps the original paragraphs and typography across pages.` : `CHAPTER ${chapter}`
      const id = `s-${sentences.length + 1}`, matches = [...text.matchAll(/[A-Za-z]+|\d+/g)]
      sentences.push({ id, text, section: 'body', words: matches.map(m => ({ text: m[0] })) })
      blocks.push({ id, text, type: i ? 'paragraph' : 'heading', section: 'body', words: matches.map((m, wordIndex) => ({ start: m.index, end: m.index + m[0].length, wordIndex, sentenceId: id })) })
      if (i) body += `<p>${text}</p>`
    }
  }
  const files = {
    'META-INF/container.xml': strToU8('<container><rootfiles><rootfile full-path="OPS/book.opf"/></rootfiles></container>'),
    'OPS/cover.xhtml': strToU8('<html><body>Cover</body></html>'),
    'OPS/body.xhtml': strToU8(`<html><head><style>body{font:20px/1.7 Georgia;margin:20px}p{margin:0 0 22px}</style></head><body>${body}</body></html>`),
    'OPS/book.opf': strToU8(`<package><manifest><item href="${kind === 'nav' ? 'nav.xhtml' : 'toc.ncx'}" ${kind === 'nav' ? 'properties="nav"' : 'media-type="application/x-dtbncx+xml"'}/></manifest></package>`),
    'OPS/nav.xhtml': strToU8('<html xmlns:epub="http://www.idpf.org/2007/ops"><body><nav epub:type="toc"><ol><li><a href="body.xhtml#chapter-1">First chapter</a></li><li><a href="body.xhtml#chapter-2">Second chapter</a></li></ol></nav></body></html>'),
    'OPS/toc.ncx': strToU8(`<ncx><navMap>${kind === 'fallback' ? '<navPoint><navLabel><text>Start</text></navLabel><content src="cover.xhtml"/></navPoint>' : [1, 2].map(i => `<navPoint><navLabel><text>${i === 1 ? 'First' : 'Second'} chapter</text></navLabel><content src="body.xhtml#chapter-${i}"/></navPoint>`).join('')}</navMap></ncx>`),
  }
  return { archive: Buffer.from(zipSync(files)), book: { id: 'interaction-test', title: 'Two chapters, one file', sentences, duration: 0, readingDocument: { version: 1, format: 'epub', blocks, source: { version: 1, layout: 'reflow', spine: [{ href: 'OPS/cover.xhtml', section: 'cover', layout: 'reflow' }, { href: 'OPS/body.xhtml', section: 'body', layout: 'reflow' }] } } } }
}

;(async () => {
  fs.mkdirSync(output, { recursive: true })
  const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true })
  try {
    for (const kind of ['nav', 'ncx', 'fallback', ...(process.env.READER_REAL_EPUB && process.env.READER_REAL_BOOK ? ['real'] : [])]) {
      const data = kind === 'real' ? { archive: fs.readFileSync(process.env.READER_REAL_EPUB), book: JSON.parse(fs.readFileSync(process.env.READER_REAL_BOOK)) } : fixture(kind)
      data.book.mediaAssets = [{ id: 'source', contentType: 'application/epub+zip', url: '/api/media/source' }]
      data.book.readingDocument.source.assetId = 'source'
      data.book.progress = {}
      const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } }), page = await context.newPage()
      const errors = [], writes = []
      page.on('pageerror', error => errors.push(error.message))
      await context.route(`${base}/api/**`, async route => {
        const request = route.request(), path = new URL(request.url()).pathname
        let result = {}
        if (path === '/api/auth/me') result = { user: { id: 'test', role: 'user', email: 'test@example.test' } }
        else if (path === '/api/preferences') result = { focusMode: true }
        else if (path.endsWith('/reader')) result = { book: data.book }
        else if (path === '/api/media/source') return route.fulfill({ contentType: 'application/epub+zip', body: data.archive })
        else if (path === '/api/workspace/progress') {
          const payload = request.postDataJSON(); writes.push(payload)
          data.book.progress = { lastSentenceId: payload.lastSentenceId, readingLocation: payload.readingLocation }
        } else if (/vocabulary|annotations/.test(path)) result = { items: [] }
        return route.fulfill({ contentType: 'application/json', body: JSON.stringify(result) })
      })
      const ready = () => page.waitForFunction(() => document.querySelector('iframe[title="EPUB 原文书页"]')?.style.visibility === 'visible')
      const toc = async index => {
        await page.getByRole('button', { name: '目录', exact: true }).click()
        const entries = page.getByRole('navigation', { name: '章节目录' }).getByRole('button')
        assert.equal(await entries.count(), 2, `${kind}: actual chapters, not spine items`)
        await entries.nth(index).click()
        await ready(); await page.waitForTimeout(1000)
      }
      await page.goto(`${base}/app?screen=reader&id=${data.book.id}&reader=workspace`)
      await ready()
      assert.equal(await page.getByRole('button', { name: '退出泛读模式' }).innerText(), '精读模式')
      await toc(1)
      const second = Number(await page.getByRole('spinbutton', { name: '跳转页码' }).inputValue())
      assert.ok(second > 1, `${kind}: second heading must be on later page`)
      assert.match(await page.locator('.extensive-running-head').innerText(), /(?:Second chapter|CHAPTER (?:TWO|2))/)
      await toc(0)
      assert.equal(await page.getByRole('spinbutton', { name: '跳转页码' }).inputValue(), '1')
      await toc(1)
      assert.equal(Number(await page.getByRole('spinbutton', { name: '跳转页码' }).inputValue()), second)
      await page.getByText('进度已保存', { exact: true }).waitFor()
      const footer = await page.evaluate(() => {
        const group = document.querySelector('.extensive-page-info > div').getBoundingClientRect()
        const status = document.querySelector('.extensive-footnote [role="status"]').getBoundingClientRect()
        const number = document.querySelector('.extensive-page-number')
        const input = number.querySelector('input').getBoundingClientRect()
        const suffix = number.lastElementChild.getBoundingClientRect()
        const paper = document.querySelector('.extensive-paper')
        const frame = paper.querySelector('iframe')
        return { center: Math.abs(group.x + group.width / 2 - status.x - status.width / 2), gap: suffix.left - input.right,
          suffix: number.lastElementChild.textContent, paper: getComputedStyle(paper).backgroundColor, frame: getComputedStyle(frame).backgroundColor }
      })
      assert.ok(footer.center < 2, `${kind}: saved status centered under page count`)
      assert.ok(footer.gap >= 0 && footer.gap < 4, `${kind}: compact page count`)
      assert.match(footer.suffix, /^\/\d+页$/)
      assert.equal(footer.paper, footer.frame, `${kind}: one continuous paper background`)
      await page.reload(); await ready(); await page.waitForTimeout(200)
      assert.equal(Number(await page.getByRole('spinbutton', { name: '跳转页码' }).inputValue()), second)
      await toc(0)
      const coordinates = await page.locator('iframe[title="EPUB 原文书页"]').evaluate(frame => {
        const doc = frame.contentDocument, walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT)
        let node
        while ((node = walker.nextNode())) {
          const match = /\b(?:Original|At|The)\b/.exec(node.textContent)
          if (!match) continue
          const range = doc.createRange(); range.setStart(node, match.index); range.setEnd(node, match.index + match[0].length)
          const r = range.getBoundingClientRect(), bounds = frame.getBoundingClientRect()
          if (r.left > 0 && r.right < frame.clientWidth && r.top > 0 && r.bottom < frame.clientHeight) return { x: bounds.left + (r.left + r.right) / 2, y: bounds.top + (r.top + r.bottom) / 2 }
        }
      })
      assert.ok(coordinates, `${kind}: visible real word`)
      await page.mouse.move(coordinates.x, coordinates.y)
      await page.waitForFunction(() => {
        const doc = document.querySelector('iframe').contentDocument
        return doc.defaultView.CSS.highlights.get('reader-word-hover')?.size === 1 && [...doc.querySelectorAll('[style]')].some(node => node.style.cursor === 'pointer')
      })
      await page.screenshot({ path: `${output}/${kind}-hover.png` })
      await page.getByRole('button', { name: '下一页', exact: true }).click()
      await page.waitForFunction(() => document.querySelector('.book-turn-leaf')?.getAnimations().length > 0)
      assert.equal(await page.locator('.book-turn-leaf').evaluate(node => node.getAnimations()[0].effect.getTiming().duration), 900)
      await page.screenshot({ path: `${output}/${kind}-turn.png` })
      await page.waitForFunction(() => !document.querySelector('.book-turn-leaf'))
      assert.equal(await page.locator('.book-turn-leaf').count(), 0)
      await page.emulateMedia({ reducedMotion: 'reduce' })
      await page.getByRole('button', { name: '上一页', exact: true }).click()
      assert.equal(await page.locator('.book-turn-leaf').count(), 0)
      assert.ok(writes.length)
      assert.deepEqual(errors, [])
      console.log(`PASS ${kind}: two actual chapters in one XHTML, repeated jumps, restore, word highlight/pointer, animated turn, reduced motion`)
      await context.close()
    }
  } finally { await browser.close() }
})().catch(error => { console.error(error); process.exitCode = 1 })
