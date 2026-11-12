// Only fixture API writes are used. No real account or email is created.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core')
const base = process.env.READER_TEST_BASE || 'http://127.0.0.1:4173'
const output = process.env.READER_TEST_OUTPUT || '/private/tmp/paper-glow-browser'
const commercial = /\/api\/(?:admin\/)?(?:membership|commerce|billing|payments|payment-config|payment-orders|subscriptions|manual-orders)\b/

;(async () => {
  fs.mkdirSync(output, { recursive: true })
  const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true })
  const errors = [], commercialRequests = []
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
    let registration = null
    await context.route(`${base}/api/**`, async route => {
      const request = route.request(), path = new URL(request.url()).pathname
      if (commercial.test(path)) commercialRequests.push(path)
      if (path === '/api/auth/me') return route.fulfill({ status: 401, json: { code: 'authentication_required' } })
      if (path === '/api/auth/config') return route.fulfill({ json: { captchaEnabled: false } })
      if (path === '/api/auth/register') {
        registration = request.postDataJSON()
        return route.fulfill({ status: 201, json: { emailDelivery: true } })
      }
      return route.fulfill({ status: 404, json: { error: 'fixture route not found' } })
    })
    const page = await context.newPage()
    page.on('pageerror', error => errors.push(error.message))
    for (const path of ['/', '/login', '/register', '/support', '/terms', '/privacy', '/content-policy', '/copyright', '/reset-password', '/verify-email']) {
      await page.goto(base + path, { waitUntil: 'domcontentloaded' })
      await page.locator('.ryn-brand-mark').first().waitFor()
      await page.waitForFunction(() => [...document.querySelectorAll('.ryn-brand-mark')].every(image => image.complete && image.naturalWidth > 0))
      assert.ok((await page.title()).includes('纸间微光'), `${path}: title`)
      const text = await page.locator('body').innerText()
      for (const retired of ['RynEnglish', '会员中心', '云猫', '支付宝', '购买 / 兑换']) assert.equal(text.includes(retired), false, `${path}: ${retired}`)
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false, `${path}: overflow`)
    }
    await page.goto(`${base}/register`)
    await page.getByLabel('邮箱', { exact: true }).fill('invited@example.test')
    await page.getByLabel('密码', { exact: true }).fill('fixture-password-2026')
    await page.locator('button[type="submit"]').click()
    await page.getByText('请输入邀请码', { exact: true }).waitFor()
    assert.equal(registration, null, 'missing invitation must not submit')
    await page.getByLabel('邀请码', { exact: true }).fill('TEST-INVITATION')
    await page.locator('button[type="submit"]').click()
    await page.getByText('账号已创建，请先验证邮箱', { exact: true }).waitFor()
    assert.equal(registration.invitationCode, 'TEST-INVITATION')
    await page.screenshot({ path: `${output}/invitation.png`, fullPage: true })
    for (const path of ['/pricing', '/purchase/pro-30', '/refunds', '/app?screen=membership']) {
      await page.goto(base + path)
      await page.getByText('页面不存在', { exact: true }).waitFor()
    }
    await page.goto(base)
    await page.getByRole('heading', { name: '纸间微光', exact: true }).waitFor()
    await page.screenshot({ path: `${output}/home.png`, fullPage: true })
    await context.close()

    const account = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
    await account.route(`${base}/api/**`, async route => {
      const path = new URL(route.request().url()).pathname
      if (commercial.test(path)) commercialRequests.push(path)
      let result = {}
      if (path === '/api/auth/me') result = { user: { id: 'fixture', email: 'fixture@example.test', isAdmin: true, canManagePlatform: false } }
      else if (path === '/api/health') result = { saasEnabled: true }
      else if (path === '/api/auth/devices') result = { devices: [{ id: 'current', current: true, label: 'Fixture Chrome' }] }
      else if (path === '/api/workspace/books') result = { books: [] }
      else if (path === '/api/library') result = { items: [] }
      else if (path === '/api/workspace/learning') result = { days: [], learningStreak: 0, today: { day: '2026-11-09', readingSeconds: 0, reviewedWords: 0, newWords: 0 }, week: { start: '2026-11-09', readingSeconds: 0 }, review: { active: null, stats: { total: 0, due: 0 } }, plan: { readingMinutes: 10, reviewWords: 10, weeklyMinutes: 60 } }
      else if (path === '/api/workspace/journey') result = { guide: { hasBook: false, hasRead: false, hasWord: false } }
      else if (path === '/api/admin/dashboard') result = { users: { total: 1, active: 1, verified: 1, suspended: 0 }, activeInvitations: 1, catalog: { published: 0, total: 0 } }
      else if (path === '/api/admin/users') result = { users: [{ id: 'fixture', email: 'fixture@example.test', status: 'active', emailVerified: true, devices: 1 }] }
      return route.fulfill({ json: result })
    })
    const app = await account.newPage()
    app.on('pageerror', error => errors.push(error.message))
    await app.goto(`${base}/app?screen=settings`)
    await app.getByText('账号操作', { exact: true }).waitFor()
    assert.equal(await app.getByRole('button', { name: '申请注销账户', exact: true }).count(), 1)
    await app.goto(`${base}/app?screen=workspace`)
    await app.getByText('第一次使用 纸间微光', { exact: true }).waitFor()
    assert.equal(await app.locator('.purchase-recovery').count(), 0)
    await app.goto(`${base}/app?screen=admin`)
    await app.getByRole('tab', { name: '用户管理', exact: true }).waitFor()
    for (const label of ['套餐管理', '支付方式', '支付宝订单', '兑换码库存', '用户与订阅']) assert.equal(await app.getByRole('tab', { name: label, exact: true }).count(), 0)
    await app.screenshot({ path: `${output}/admin.png`, fullPage: true })
    assert.deepEqual(commercialRequests, [], 'no commercial APIs may be requested')
    assert.deepEqual(errors, [], 'browser runtime errors')
    await account.close()
    console.log('PASS private brand, invitation validation, retired routes, account and admin surfaces; no commercial requests')
  } finally { await browser.close() }
})().catch(error => { console.error(error); process.exitCode = 1 })
