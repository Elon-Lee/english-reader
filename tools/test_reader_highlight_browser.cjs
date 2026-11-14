// Isolated API fixtures; optional read-only export of the reported local book.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const http = require('node:http')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core')
const root = path.resolve(__dirname, '..')
const output = process.env.READER_TEST_OUTPUT || '/private/tmp/english-reader-highlight-browser'
const text = 'The Stranger-man (and he was a Tewara) thought, "This is a very, very wonderful child.'
const fixture = process.env.READER_TEST_BOOK ? JSON.parse(fs.readFileSync(process.env.READER_TEST_BOOK)) : {
  id: 'highlight-fixture', title: 'Sentence highlighting', duration: 82,
  sentences: Array.from({ length: 41 }, (_, i) => ({
    id: `s-${i + 1}`, text: i === 36 ? text : 'A quiet morning.', start: i * 2, end: i * 2 + 2,
    timingPolicy: 'kokoro-sentence-audio',
    words: i === 36 ? text.match(/[A-Za-z]+/g).map(text => ({ text })) :
      ['A', 'quiet', 'morning'].map((text, j) => ({ text, start: i * 2 + j * .5, end: i * 2 + j * .5 + .4 })),
  })),
}
const duration = Math.ceil(fixture.duration + 1), sampleRate = 8000
const audio = Buffer.alloc(44 + duration * sampleRate * 2)
audio.write('RIFF'); audio.writeUInt32LE(audio.length - 8, 4); audio.write('WAVEfmt ', 8)
audio.writeUInt32LE(16, 16); audio.writeUInt16LE(1, 20); audio.writeUInt16LE(1, 22)
audio.writeUInt32LE(sampleRate, 24); audio.writeUInt32LE(sampleRate * 2, 28)
audio.writeUInt16LE(2, 32); audio.writeUInt16LE(16, 34); audio.write('data', 36); audio.writeUInt32LE(audio.length - 44, 40)

async function serve(directory) {
  const server = http.createServer((request, response) => {
    const pathname = new URL(request.url, 'http://localhost').pathname
    let file = path.resolve(directory, `.${decodeURIComponent(pathname)}`)
    if (!file.startsWith(directory + '/') || !fs.existsSync(file) || !fs.statSync(file).isFile()) file = path.join(directory, 'index.html')
    response.setHeader('Content-Type', ({ '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml' })[path.extname(file)] || 'application/octet-stream')
    response.end(fs.readFileSync(file))
  })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  return { base: `http://127.0.0.1:${server.address().port}`, close: () => new Promise(resolve => server.close(resolve)) }
}

;(async () => {
  fs.mkdirSync(output, { recursive: true })
  const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true })
  try {
    for (const site of ['cn', 'intl']) {
      const server = await serve(path.join(root, 'reader', site === 'cn' ? 'site' : 'site-intl'))
      const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } })
      const page = await context.newPage(), errors = [], lookups = []
      let prefs = { focusMode: false, readerContentWidth: 760, wordAutoPronounce: false, readerToolsPinned: false }
      page.on('pageerror', error => errors.push(error.message))
      await context.route(`${server.base}/api/**`, async route => {
        const request = route.request(), url = new URL(request.url()), pathname = url.pathname
        let data = {}
        if (pathname === '/api/auth/me') data = { user: { id: 'fixture', email: 'reader@example.test', isAdmin: true, role: 'admin' } }
        else if (pathname === '/api/preferences') {
          if (request.method() === 'POST') { prefs = { ...prefs, ...request.postDataJSON() }; data = { preferences: prefs } }
          else data = prefs
        } else if (pathname.endsWith('/reader')) data = { book: { ...fixture, mediaAssets: [
          { id: 'epub', contentType: 'application/epub+zip', variants: [{ name: 'audio', contentType: 'audio/wav', url: '/api/media/narration' }] },
        ], progress: {} } }
        else if (pathname === '/api/media/narration') {
          const range = request.headers().range?.match(/^bytes=(\d+)-(\d*)$/)
          const start = range ? Number(range[1]) : 0, end = range?.[2] ? Math.min(Number(range[2]), audio.length - 1) : audio.length - 1
          return route.fulfill({ status: range ? 206 : 200, contentType: 'audio/wav', body: audio.subarray(start, end + 1), headers: {
            'Accept-Ranges': 'bytes', 'Content-Length': String(end - start + 1),
            ...(range ? { 'Content-Range': `bytes ${start}-${end}/${audio.length}` } : {}),
          } })
        } else if (pathname.includes('/dictionary')) { lookups.push(url.toString()); data = { word: 'Stranger', translation: '陌生人' } }
        else if (/vocabulary|annotations/.test(pathname)) data = { items: [] }
        return route.fulfill({ json: data })
      })
      try {
        const reader = site === 'cn' ? 'official' : 'workspace'
        await page.goto(`${server.base}/app?screen=reader&id=${fixture.id}&reader=${reader}&sentence=s-37`)
        const sentence = page.getByRole('article', { name: '第 37 句', exact: true })
        await sentence.waitFor()
        await page.waitForFunction(() => document.querySelector('audio')?.readyState >= 1)
        assert.equal(await sentence.locator('p').textContent(), fixture.sentences[36].text)
        await sentence.locator('.reader-spoken-sentence').waitFor()
        assert.equal(await sentence.locator('.spoken').count(), 0, 'no fabricated per-word timings')
        const settings = page.getByRole('button', { name: '阅读设置', exact: true })
        assert.equal((await settings.innerText()).trim(), '阅读设置')
        assert.equal(await settings.locator('[aria-label="read"]').count(), 1)
        await settings.click()
        const dialog = page.getByRole('dialog', { name: '阅读设置', exact: true })
        const widthSlider = dialog.locator('.ant-form-item').filter({ hasText: '正文宽度' }).getByRole('slider')
        await widthSlider.focus(); await widthSlider.press('End')
        await dialog.getByRole('button', { name: '保存阅读设置' }).click()
        await page.locator('.reader-width-full').waitFor()
        assert.equal(prefs.readerContentWidth, 1040)
        const dimensions = await page.locator('.reader-story').evaluate(node => {
          const r = node.getBoundingClientRect()
          return { left: r.left, right: innerWidth - r.right, width: r.width, overflow: document.documentElement.scrollWidth - innerWidth }
        })
        assert(dimensions.left <= 40 && dimensions.right <= 40, JSON.stringify(dimensions))
        assert(dimensions.width > 1800 && dimensions.overflow <= 1)
        await page.screenshot({ path: path.join(output, `${site}-sentence-37.png`) })
        // Seek to the adjacent sentence: fallback clears and native word timing resumes.
        const next = fixture.sentences[37]
        await page.locator('audio').evaluate((node, time) => { node.currentTime = time; node.dispatchEvent(new Event('timeupdate')) }, next.start + .5)
        await page.waitForFunction(() => document.querySelector('.reader-sentence.active')?.getAttribute('aria-label') === '第 38 句')
        assert.equal(await sentence.locator('.reader-spoken-sentence').count(), 0)
        assert(await page.getByRole('article', { name: '第 38 句', exact: true }).locator('.spoken').count() > 0)
        await page.screenshot({ path: path.join(output, `${site}-full-width.png`) })
        // Tools can open at full width without horizontal overflow.
        await page.locator('button[aria-controls="reader-tools"]').click()
        assert(await page.locator('.reader-inspector').isVisible())
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1))
        await page.setViewportSize({ width: 1280, height: 900 })
        assert(await settings.isVisible())
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1))
        await page.screenshot({ path: path.join(output, `${site}-1280-tools.png`) })
        assert.deepEqual(errors, [])
        console.log(`${site}: sentence 37, original punctuation/spacing, sentence/word highlights, settings save, full width and tools passed`)
      } catch (error) {
        await page.screenshot({ path: path.join(output, `${site}-failure.png`) })
        throw error
      } finally { await context.close(); await server.close() }
    }
  } finally { await browser.close() }
})().catch(error => { console.error(error); process.exitCode = 1 })
