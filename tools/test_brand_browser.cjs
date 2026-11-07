// Public pages use real read-only APIs; account interactions use isolated fixtures.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core')
const base = process.env.READER_TEST_BASE || 'http://127.0.0.1:4173'
const output = process.env.READER_TEST_OUTPUT || '/private/tmp/english-reader-ryn-sync/browser'
const slogan = 'Every Page, A Deeper Understanding.'

;(async () => {
  fs.mkdirSync(output, { recursive: true })
  const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true })
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
    const page = await context.newPage(), errors = []
    page.on('pageerror', error => errors.push(error.message))
    for (const path of ['/', '/login', '/register', '/pricing', '/support', '/terms', '/privacy', '/content-policy', '/refunds', '/copyright', '/reset-password', '/verify-email']) {
      await page.goto(base + path, { waitUntil: 'domcontentloaded' })
      await page.locator('.ryn-brand-mark').first().waitFor()
      await page.waitForFunction(() => [...document.querySelectorAll('.ryn-brand-mark')].every(image => image.complete && image.naturalWidth > 0))
      assert.ok((await page.title()).includes('RynEnglish'), `${path}: title`)
      assert.ok(!(await page.locator('body').innerText()).includes('拾页'), `${path}: old brand copy`)
      assert.equal(await page.locator('.ryn-brand-slogan').first().textContent(), slogan)
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false, `${path}: overflow`)
      if (path === '/') {
        assert.equal(await page.locator('meta[property="og:site_name"]').getAttribute('content'), 'RynEnglish')
        await page.getByText(slogan, { exact: true }).last().waitFor()
        for (const name of ['workspace-current.jpg', 'vocabulary-review-20261026.webp']) {
          const source = page.locator(`img[src*="${name}"]`)
          const response = await page.request.get(base + await source.getAttribute('src'))
          assert.equal(response.status(), 200)
          assert.deepEqual(await response.body(), fs.readFileSync(`frontend/public/product/${name}`))
        }
      }
      if (['/', '/login'].includes(path)) await page.screenshot({ path: `${output}/${path === '/' ? 'home' : 'login'}.png`, fullPage: true })
    }
    assert.deepEqual(errors, [])
    await context.close()
    console.log('PASS real public routes: titles, full official logo/slogan, Open Graph, branded product screenshots, legal/auth pages')

    const account = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
    const app = await account.newPage(), writes = []
    let failClear = true, pending = { phase: 'departed', name: '进阶', slug: 'plus' }
    app.on('pageerror', error => errors.push(error.message))
    await account.route(`${base}/api/**`, async route => {
      const request = route.request(), path = new URL(request.url()).pathname
      let result = {}
      if (path === '/api/auth/me') result = { user: { id: 'brand-fixture', email: 'brand@example.test', isAdmin: false } }
      else if (path === '/api/health') result = { status: 'ok', saasEnabled: true, redisReady: true }
      else if (path === '/api/auth/devices') result = { devices: [{ id: 'current', current: true, label: 'Test Chrome' }] }
      else if (path === '/api/workspace/books') result = { books: [] }
      else if (path === '/api/library') result = { items: [] }
      else if (path === '/api/workspace/learning') result = {
        days: [], learningStreak: 0,
        today: { day: '2026-11-07', readingSeconds: 0, reviewedWords: 0, newWords: 0 },
        week: { start: '2026-11-02', readingSeconds: 0 },
        review: { active: null, stats: { total: 0, due: 0 } },
        plan: { readingMinutes: 10, reviewWords: 10, weeklyMinutes: 60 },
      }
      else if (path === '/api/workspace/journey') {
        if (request.method() === 'POST') {
          const body = request.postDataJSON(); writes.push(body)
          assert.equal(body.action, 'clear_purchase')
          if (failClear) return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: '暂时无法关闭提醒，请重试' }) })
          pending = null
        }
        result = { pendingPurchase: pending, guide: { hasBook: false, hasRead: false, hasWord: false } }
      }
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify(result) })
    })
    await app.goto(`${base}/app?screen=settings`)
    await app.getByText('账号操作', { exact: true }).waitFor()
    assert.equal(await app.getByText('危险区域', { exact: true }).count(), 0)
    assert.equal(await app.getByRole('button', { name: '导出账户数据', exact: true }).count(), 0)
    assert.equal(await app.getByRole('button', { name: '申请注销账户', exact: true }).count(), 1)
    assert.ok(await app.getByRole('button', { name: '退出登录', exact: true }).count())
    await app.screenshot({ path: `${output}/settings.png`, fullPage: true })
    await app.goto(`${base}/app?screen=workspace`)
    await app.getByText('第一次使用 RynEnglish', { exact: true }).waitFor()
    const dismiss = app.locator('.purchase-recovery button').filter({ hasText: '不再提醒' })
    await dismiss.click()
    await app.getByText('暂时无法关闭提醒，请重试', { exact: true }).waitFor()
    failClear = false
    await dismiss.click()
    await dismiss.waitFor({ state: 'detached' })
    assert.equal(writes.length, 2)
    assert.deepEqual(errors, [])
    await account.close()
    console.log('PASS isolated account operations and purchase reminder: existing POST, failure/retry, no real account mutations')
  } finally { await browser.close() }
})().catch(error => { console.error(error); process.exitCode = 1 })
