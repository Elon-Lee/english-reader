// Exercise the real local SDK/Python/Java/Redis chain, without logging in or sending mail.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core')
const base = process.env.READER_TEST_BASE || 'http://127.0.0.1:4173'
assert.ok(['127.0.0.1', 'localhost'].includes(new URL(base).hostname), 'Local development only')

;(async () => {
  const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true })
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
    const page = await context.newPage(), errors = []
    page.on('pageerror', error => errors.push(error.message))
    for (const mode of ['login', 'register', 'forgot']) {
      await page.goto(base + (mode === 'register' ? '/register' : '/login'), { waitUntil: 'domcontentloaded' })
      if (mode === 'forgot') await page.getByText('找回密码', { exact: true }).click()
      await page.getByLabel('邮箱', { exact: true }).fill('local-dev-check@example.invalid')
      if (mode !== 'forgot') await page.getByLabel('密码', { exact: true }).fill('unused-local-ui-test-password')
      if (mode === 'register') await page.getByLabel('邀请码', { exact: true }).fill('unused-local-ui-test-code')
      const generated = page.waitForResponse(response => response.url().endsWith('/api/auth/captcha/gen'))
      await page.locator('form button[type="submit"]').click()
      const response = await generated, result = await response.json()
      assert.equal(response.status(), 200)
      assert.equal(result.code, 200)
      assert.equal(result.data.type, 'ROTATE')
      assert.ok(result.data.templateImage.startsWith('data:image/'))
      await page.locator('#tianai-captcha-slider-bg-img').waitFor({ state: 'visible' })
      await page.waitForFunction(() => {
        const image = document.querySelector('#tianai-captcha-slider-bg-img')
        return image.complete && image.naturalWidth > 0
      })
      assert.equal(await page.locator('.auth-captcha-status[role="alert"]').count(), 0)
      if (mode === 'login') {
        fs.mkdirSync('.local/local-dev', { recursive: true })
        await page.screenshot({ path: '.local/local-dev/captcha-loaded.png' })
      }
      await page.keyboard.press('Escape')
      await page.locator('.auth-captcha-dialog').waitFor({ state: 'detached' })
      console.log(`PASS real local ${mode} captcha: SDK, generated image, visible panel, cancel`)
    }
    assert.deepEqual(errors, [])
    await context.close()
  } finally { await browser.close() }
})().catch(error => { console.error(error); process.exitCode = 1 })
