const assert = require('node:assert/strict')
const fs = require('node:fs')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core')
const base = process.env.READER_TEST_BASE || 'http://127.0.0.1:4173'
const output = process.env.READER_TEST_OUTPUT || '/private/tmp/english-reader-polish/browser'

;(async () => {
  fs.mkdirSync(output, { recursive: true })
  const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true })
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } }), page = await context.newPage()
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    await page.goto(`${base}/login`, { waitUntil: 'domcontentloaded' })
    await page.locator('form').waitFor()
    assert.ok((await page.title()).includes('RynEnglish'))
    assert.ok(!(await page.title()).includes('拾页'))
    const icon = page.locator('link[rel="icon"][type="image/svg+xml"]')
    assert.match(await icon.getAttribute('href'), /rynenglish-mark\.svg/)
    assert.equal((await page.request.get(base + await icon.getAttribute('href'))).status(), 200)
    assert.ok(await page.locator('.modern-auth-brand img').evaluate(node => node.complete && node.naturalWidth > 0))
    assert.ok((await page.locator('.modern-auth-brand').innerText()).includes('RynEnglish'))
    await page.screenshot({ path: `${output}/local-brand.png` })
    let tall = true, layout = 'side'
    await context.route(`${base}/api/**`, async route => {
      const path = new URL(route.request().url()).pathname
      let result = {}
      if (path === '/api/auth/me') result = { user: { id: 'test', role: 'user', email: 'test@example.test' } }
      else if (path === '/api/preferences') result = { focusMode: false, readerLayout: layout }
      else if (path.endsWith('/reader')) result = { book: { id: 'image-reader', title: 'Original image', sentences: [{ id: 's-1', text: 'The original image fills the reading column.', words: ['The', 'original', 'image', 'fills', 'the', 'reading', 'column'].map(text => ({ text })) }], mediaAssets: [{ id: 'image', contentType: 'image/svg+xml', url: '/api/media/polish-image' }], progress: {} } }
      else if (path === '/api/media/polish-image') return route.fulfill({ contentType: 'image/svg+xml', body: `<svg xmlns="http://www.w3.org/2000/svg" width="600" height="${tall ? 1400 : 240}" viewBox="0 0 600 ${tall ? 1400 : 240}"><rect width="100%" height="100%" fill="#faf8ef"/><rect x="20" y="20" width="560" height="180" fill="#d9e7d4"/><text x="40" y="90" font-size="32" fill="#285c45">Original page</text></svg>` })
      else if (/vocabulary|annotations/.test(path)) result = { items: [] }
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify(result) })
    })
    for (layout of ['side', 'stack']) {
      for (tall of [true, false]) {
        await page.goto(`${base}/app?screen=reader&id=image-reader&reader=workspace`)
        await page.locator('.reader-original-image').waitFor()
        await page.waitForFunction(() => document.querySelector('.reader-original-image').naturalWidth > 0)
        const geometry = await page.locator('.reader-original-image').evaluate(image => {
          const stage = image.closest('.reader-media-stage'), r = image.getBoundingClientRect(), s = stage.getBoundingClientRect()
          return { width: Math.abs(r.width - stage.clientWidth), offset: Math.abs(r.left - s.left), ratio: r.width / r.height, sourceRatio: image.naturalWidth / image.naturalHeight,
            height: stage.clientHeight, scrollHeight: stage.scrollHeight, background: getComputedStyle(stage).backgroundColor }
        })
        assert.ok(geometry.width < 2 && geometry.offset < 2, `${layout}/${tall}: image fills full width`)
        assert.ok(Math.abs(geometry.ratio - geometry.sourceRatio) < .01, 'source aspect ratio preserved')
        assert.notEqual(geometry.background, 'rgb(14, 19, 16)')
        assert.ok(geometry.height > 0)
        if (tall) assert.ok(geometry.scrollHeight > geometry.height, 'long image scrolls without cropping')
        await page.screenshot({ path: `${output}/image-${layout}-${tall ? 'tall' : 'wide'}.png` })
      }
    }
    assert.deepEqual(errors, [])
    console.log('PASS RynEnglish title/icon/login brand and intensive original images: full width, preserved ratio, scrollable long page in side/top layouts')
    await context.close()
  } finally { await browser.close() }
})().catch(error => { console.error(error); process.exitCode = 1 })
