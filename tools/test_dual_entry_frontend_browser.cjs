// Isolated browser fixtures verify presentation and requests, never real payments.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const http = require('node:http')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core')
const root = path.resolve(__dirname, '..')
const output = process.env.READER_TEST_OUTPUT || '/private/tmp/english-reader-dual-entry-check'

async function serve(directory) {
  const server = http.createServer((request, response) => {
    const pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname)
    let file = path.resolve(directory, `.${pathname}`)
    if (!file.startsWith(`${directory}/`) || !fs.existsSync(file) || !fs.statSync(file).isFile()) file = path.join(directory, 'index.html')
    const types = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.webp': 'image/webp', '.jpg': 'image/jpeg' }
    response.setHeader('Content-Type', types[path.extname(file)] || 'application/octet-stream')
    response.end(fs.readFileSync(file))
  })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  return { base: `http://127.0.0.1:${server.address().port}`, close: () => new Promise(resolve => server.close(resolve)) }
}

const product = { id: 'fixture-pro-v1', slug: 'fixture-pro', family: 'pro', planVersion: 'fixture-pro-v1', name: '浏览器测试方案', shortName: '测试 Pro', tagline: '仅用于隔离浏览器测试', description: '测试数据', amountCents: 100, originalAmountCents: 100, discountPercent: 100, durationDays: 30, paymentMethods: ['alipay'], redemptionEnabled: true, featureLimits: { storage_bytes: 10, video_library_capacity: 20, audio_library_capacity: 20, devices: 3 }, benefits: [] }
const free = { ...product, id: 'fixture-free', slug: 'free', family: 'free', name: '测试免费方案', shortName: '测试 Free', amountCents: 0, paymentMethods: [], planVersion: 'fixture-free' }

;(async () => {
  fs.mkdirSync(output, { recursive: true })
  const servers = await Promise.all(['site', 'site-intl'].map(site => serve(path.join(root, 'reader', site))))
  const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true })
  try {
    for (const [index, site] of ['cn', 'intl'].entries()) {
      const base = servers[index].base
      const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
      const page = await context.newPage(), errors = [], calls = []
      let authenticated = false, catalogFailure = false, paid = false, paymentPayload = null, pagePayment = false, importAllowed = false, importFailure = false, hasPrivateBook = false
      page.on('pageerror', error => errors.push(error.message))
      await context.route(`${base}/api/**`, async route => {
        const request = route.request(), pathname = new URL(request.url()).pathname
        calls.push(pathname)
        let data = {}
        if (pathname === '/api/auth/me') {
          if (!authenticated) return route.fulfill({ status: 401, json: { error: 'Fixture requires login' } })
          data = { user: { id: 'fixture-user', displayName: '隔离测试账号', email: 'browser@example.test', isAdmin: false }, csrfToken: 'fixture-csrf' }
        } else if (pathname === '/api/commerce/products') {
          if (catalogFailure) return route.fulfill({ status: 503, json: { error: '隔离测试：套餐暂不可用' } })
          data = { products: [free, product], support: { value: '测试支持' } }
        } else if (pathname === '/api/commerce/products/fixture-pro') data = { product, support: { value: '测试支持' } }
        else if (pathname === '/api/membership/change-preview') data = { changeType: 'upgrade', targetPlan: { name: product.name }, durationDays: 30, carryDays: 0, endsAt: '2027-01-01T00:00:00Z' }
        else if (pathname === '/api/membership/usage') data = { plan: { slug: 'free', name: '测试免费方案' }, usage: [{ feature: 'storage_bytes', used: 0, limit: 1024 }, { feature: 'ai_context_generations', available: 10 }, { feature: 'ai_grammar_generations', available: 10 }], mediaCapacity: { video: { used: 0, limit: 20 }, audio: { used: 0, limit: 20 } } }
        else if (pathname === '/api/membership/orders') data = { orders: [] }
        else if (pathname === '/api/workspace/journey') data = { guide: { hasRead: true, hasWord: true, dismissed: true } }
        else if (pathname === '/api/preferences') data = { theme: 'pine' }
        else if (pathname === '/api/health') data = { saasEnabled: true }
        else if (pathname === '/api/payments/alipay/orders' && request.method() === 'POST') {
          paymentPayload = request.postDataJSON()
          data = { orderId: 'fixture-order', amountCents: 100, status: 'pending', ...(pagePayment ? { paymentMode: 'page_pay', checkoutUrl: 'https://openapi.alipay.com/gateway.do?fixture=isolated' } : { qrCode: 'https://payment.example.test/fixture-only' }) }
        } else if (pathname === '/api/payments/alipay/orders/fixture-order') data = { orderId: 'fixture-order', status: paid ? 'paid' : 'pending', amountCents: 100, endsAt: '2027-01-01T00:00:00Z', ...(pagePayment && !paid ? { paymentMode: 'page_pay', checkoutUrl: 'https://openapi.alipay.com/gateway.do?fixture=isolated' } : {}) }
        else if (pathname === '/api/auth/config') data = { captchaEnabled: false }
        else if (pathname === '/api/resources') {
          if (importFailure) return route.fulfill({ status: 503, json: { error: '隔离测试：权限服务暂不可用' } })
          data = { privateImport: { allowed: importAllowed, storageLimit: importAllowed ? 1024 ** 3 : 0 } }
        }
        else if (pathname === '/api/workspace/books') data = { books: hasPrivateBook ? [{ id: 'fixture-existing-book', title: '已有私人读物', sourceType: 'text', status: 'ready', sentenceCount: 2 }] : [] }
        else if (pathname === '/api/library') data = { items: [] }
        else if (pathname === '/api/workspace/imports') data = { tasks: [] }
        else if (pathname === '/api/workspace/imports/match-audio') data = { matched: null }
        else if (pathname === '/api/workspace/learning') data = { today: { day: '2026-11-13', readingSeconds: 0, reviewedWords: 0 }, week: { start: '2026-11-09', readingSeconds: 0, reviewedWords: 0 }, review: { stats: { total: 0, due: 0 }, active: null }, plan: { readingMinutes: 10, reviewWords: 5, weeklyMinutes: 60 }, days: [], learningStreak: 0 }
        else if (pathname === '/api/auth/devices') data = { devices: [] }
        else if (pathname === '/api/account/deletion-status') data = { status: 'none' }
        else return route.fulfill({ status: 404, json: { error: `Unconfigured fixture ${pathname}` } })
        return route.fulfill({ json: data })
      })
      await page.goto(base)
      await page.getByRole('heading', { level: 1 }).first().waitFor()
      if (site === 'intl') {
        for (const image of await page.locator('img').all()) {
          await image.scrollIntoViewIfNeeded()
          await image.evaluate(element => element.decode())
        }
        await page.evaluate(() => scrollTo(0, 0))
      }
      await page.screenshot({ path: path.join(output, `${site}-home.png`), fullPage: true })
      if (site === 'cn') {
        assert.equal(await page.getByRole('heading', { level: 1 }).first().innerText(), '纸间微光')
        await page.goto(`${base}/login`)
        await page.getByLabel('密码', { exact: true }).waitFor()
        const record = page.getByRole('link', { name: '蜀ICP备2026071122号-1', exact: true })
        assert.equal(await record.getAttribute('href'), 'https://beian.miit.gov.cn/')
        await record.scrollIntoViewIfNeeded()
        assert(await record.isVisible())
        const footerBox = await page.locator('.cn-site-footer').boundingBox()
        assert(Math.abs(footerBox.x + footerBox.width / 2 - 720) < 1, 'domestic footer is centered')
        await page.screenshot({ path: path.join(output, 'cn-login-record.png'), fullPage: true })
        authenticated = true
        await page.goto(`${base}/app?screen=settings`)
        await page.getByRole('heading', { name: '系统设置', exact: true }).waitFor()
        await record.scrollIntoViewIfNeeded()
        assert(await record.isVisible())
        assert.equal(await page.getByText('页面暂时无法加载', { exact: true }).count(), 0)
        await page.screenshot({ path: path.join(output, 'cn-app-record.png'), fullPage: true })
        authenticated = false
        await page.goto(`${base}/pricing`)
        await page.getByText('页面不存在', { exact: true }).waitFor()
        assert(!calls.some(call => /\/api\/(commerce|membership|payments)/.test(call)))
      } else {
        await page.getByText('不是看过。', { exact: true }).waitFor()
        catalogFailure = true
        await page.goto(`${base}/pricing`)
        await page.getByText('隔离测试：套餐暂不可用', { exact: true }).waitFor()
        catalogFailure = false
        await page.getByRole('button', { name: /重\s*试|重新加载/ }).click()
        await page.getByRole('heading', { name: '测试 Pro', exact: true }).waitFor()
        await page.screenshot({ path: path.join(output, 'intl-pricing.png'), fullPage: true })
        await page.goto(`${base}/purchase/fixture-pro`)
        await page.getByRole('link', { name: '登录后核对方案', exact: true }).waitFor()
        assert((await page.getByRole('link', { name: '登录后核对方案', exact: true }).getAttribute('href')).startsWith('/login?next='))
        authenticated = true
        await page.goto(`${base}/app?screen=membership`)
        await page.getByRole('heading', { name: '会员中心', exact: true }).waitFor()
        await page.getByRole('heading', { name: '测试免费方案', exact: true }).waitFor()
        await page.getByText('暂无开通订单，免费方案也可开始学习。', { exact: true }).waitFor()
        await page.getByRole('button', { name: '升级会员', exact: true }).click()
        await page.getByRole('button', { name: '升级到测试 Pro', exact: true }).click()
        await page.getByRole('button', { name: /支付宝支付/ }).click()
        await page.getByText('fixture-order', { exact: true }).waitFor()
        assert.equal(paymentPayload.productVersionId, product.id)
        assert(paymentPayload.idempotencyKey.startsWith('alipay-'))
        paid = true
        await page.getByText('付款成功，会员权益已开通', { exact: true }).waitFor()
        await page.screenshot({ path: path.join(output, 'intl-membership-payment-fixture.png'), fullPage: true })
        pagePayment = true; paid = false
        await context.route('https://openapi.alipay.com/**', route => route.fulfill({ contentType: 'text/html; charset=utf-8', body: '<!doctype html><html><meta charset="utf-8"><h1>隔离支付宝收银台</h1></html>' }))
        await page.goto(`${base}/app?screen=membership`)
        await page.getByRole('button', { name: '升级会员', exact: true }).click()
        await page.getByRole('button', { name: '升级到测试 Pro', exact: true }).click()
        await page.getByRole('button', { name: /支付宝支付/ }).click()
        const checkout = page.getByRole('link', { name: '前往支付宝收银台', exact: true })
        await checkout.waitFor()
        assert.equal(await checkout.getAttribute('href'), 'https://openapi.alipay.com/gateway.do?fixture=isolated')
        const popupReady = page.waitForEvent('popup')
        await checkout.click()
        const popup = await popupReady
        await popup.getByRole('heading', { name: '隔离支付宝收银台' }).waitFor()
        await popup.close()
        await page.reload()
        await checkout.waitFor()
        await page.screenshot({ path: path.join(output, 'intl-page-payment-restored-fixture.png'), fullPage: true })
      }
      authenticated = true
      await page.goto(`${base}/app?screen=workspace`)
      await page.getByRole('heading', { name: '今天，从一小段开始', exact: true }).waitFor()
      const workspaceImport = page.getByRole('button', { name: /导入材料$/ })
      if (site === 'cn') {
        assert.equal(await workspaceImport.count(), 0, 'domestic workspace hides private import')
        assert.equal(await page.getByText('去书城找一篇感兴趣的内容，加入书架开始学习。', { exact: true }).count(), 1)
      } else {
        await workspaceImport.click()
        await page.getByRole('dialog', { name: '升级套餐后导入读物', exact: true }).waitFor()
        await page.getByRole('button', { name: '暂不升级', exact: true }).click()
      }
      await page.goto(`${base}/app?screen=library`)
      await page.getByRole('heading', { name: '我的书架', exact: true }).waitFor()
      const importButtons = page.getByRole('button', { name: /导入读物$/ })
      if (site === 'cn') {
        assert.equal(await importButtons.count(), 0, 'domestic populated/empty library hides private import')
        assert.equal(await page.getByRole('button', { name: '导入记录', exact: true }).count(), 0)
        hasPrivateBook = true
        await page.reload()
        await page.getByRole('heading', { name: '已有私人读物', exact: true }).waitFor()
        assert.equal(await importButtons.count(), 0, 'domestic existing books do not re-enable import')
        assert.equal(await page.getByRole('button', { name: '导入记录', exact: true }).count(), 0)
        assert(!calls.some(call => call.startsWith('/api/workspace/imports')))
      } else {
        await importButtons.first().click()
        await page.getByRole('dialog', { name: '升级套餐后导入读物', exact: true }).waitFor()
        assert.equal(await page.getByRole('dialog').filter({ hasText: '导入新的学习内容' }).count(), 0)
        await page.getByRole('button', { name: '查看套餐', exact: true }).click()
        await page.waitForURL(`${base}/pricing`)
        importFailure = true
        await page.goto(`${base}/app?screen=library`)
        await importButtons.first().click()
        await page.getByText('隔离测试：权限服务暂不可用', { exact: true }).waitFor()
        assert.equal(await page.getByText('导入新的学习内容', { exact: true }).count(), 0)
        importFailure = false; importAllowed = true
        await importButtons.first().click()
        await page.getByText('导入新的学习内容', { exact: true }).waitFor()
        await page.screenshot({ path: path.join(output, 'intl-paid-private-import-fixture.png'), fullPage: true })
        await page.getByLabel('学习文件', { exact: true }).setInputFiles({ name: 'fixture.txt', mimeType: 'text/plain', buffer: Buffer.from('Private import fixture.') })
        await page.getByText('未找到已上传的同名 MP3', { exact: false }).waitFor()
        importAllowed = false
        const writesBefore = calls.filter(call => call === '/api/workspace/imports').length
        await page.getByRole('button', { name: '创建导入任务', exact: true }).click()
        await page.getByRole('dialog', { name: '升级套餐后导入读物', exact: true }).waitFor()
        assert.equal(calls.filter(call => call === '/api/workspace/imports').length, writesBefore, 'expired entitlement is rechecked before task creation')
      }
      authenticated = false
      await page.goto(`${base}/register`)
      await page.getByLabel('邀请码', { exact: true }).waitFor()
      assert(await page.getByLabel('邀请码', { exact: true }).getAttribute('aria-required') === 'true')
      assert.equal(await page.getByRole('link', { name: '蜀ICP备2026071122号-1', exact: true }).count(), site === 'cn' ? 1 : 0)
      assert.deepEqual(errors, [], `${site} browser errors`)
      console.log(`${site}: browser route, API state and presentation checks passed (${calls.length} API calls)`)
      await context.close()
    }
    console.log(`Screenshots: ${output}; payment and user data were isolated fixtures.`)
  } finally {
    await browser.close()
    await Promise.all(servers.map(server => server.close()))
  }
})().catch(error => { console.error(error); process.exitCode = 1 })
