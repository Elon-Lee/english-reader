// Opt-in verification of the real independent local stack. No mocked APIs.
// Requires test-only Pillow/numpy and playwright-core (PLAYWRIGHT_MODULE).
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { spawnSync } = require('node:child_process')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core')
const root = path.resolve(__dirname, '..')
const base = 'http://127.0.0.1:4173'
assert.equal(process.env.SHIYUE_LOCAL_BROWSER_TEST, '1', 'Opt in with SHIYUE_LOCAL_BROWSER_TEST=1')
const config = JSON.parse(fs.readFileSync(path.join(root, '.local/local-dev/config.json'), 'utf8'))

;(async () => {
  const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true })
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
    const page = await context.newPage(), externalRequests = [], errors = []
    page.on('pageerror', error => errors.push(error.message))
    page.on('request', request => {
      const url = new URL(request.url())
      if (['http:', 'https:', 'ws:', 'wss:'].includes(url.protocol) && !['127.0.0.1', 'localhost'].includes(url.hostname)) externalRequests.push(url.hostname)
    })
    await page.goto(base + '/login')
    await page.getByLabel('邮箱', { exact: true }).fill(config.adminEmail)
    await page.getByLabel('密码', { exact: true }).fill(config.adminPassword)
    const generated = page.waitForResponse('**/api/auth/captcha/gen')
    await page.locator('form button[type="submit"]').click()
    const result = await (await generated).json()
    assert.equal(result.code, 200)
    await page.locator('#tianai-captcha-slider-bg-img').waitFor({ state: 'visible' })
    // Only the known bundled image is matched by a test helper. Production exposes
    // no captcha answers, bypass endpoints, or saved platform credentials.
    const solver = spawnSync(path.join(root, '.local/local-dev/test-venv/bin/python'), ['-c', `
import json,sys
from pathlib import Path
sys.path.insert(0,'tools')
from test_auth_captcha_browser import AuthCaptchaBrowserTests
test=AuthCaptchaBrowserTests()
test.root=Path.cwd()
print(test.solve_test_photo(json.load(sys.stdin)))
`], { cwd: root, input: JSON.stringify(result.data), encoding: 'utf8' })
    assert.equal(solver.status, 0, 'Test image matching failed')
    const angle = Number(solver.stdout.trim())
    assert.ok(Number.isFinite(angle) && angle >= 0 && angle < 360)
    const box = await page.locator('#tianai-captcha-slider-move-btn').boundingBox()
    const x = box.x + box.width / 2, y = box.y + box.height / 2
    const loggedIn = page.waitForResponse(response => response.url().endsWith('/api/auth/login'))
    await page.mouse.move(x, y)
    await page.mouse.down()
    for (let i = 1; i <= 40; i++) {
      const progress = 1 - (1 - i / 40) ** 3
      await page.mouse.move(x + angle / 360 * 242 * progress, y + i % 3)
      await page.waitForTimeout(8 + i * 2)
    }
    await page.mouse.up()
    const login = await loggedIn
    assert.equal(login.status(), 200)
    assert.equal((await login.json()).user.isAdmin, true)
    await page.waitForURL(url => !url.pathname.includes('login'))
    await page.getByRole('menuitem', { name: '平台与部署' }).waitFor()
    // GET config reads local node settings. Do not request remote release lists
    // or navigate to the deployment page, which deliberately contacts the node.
    const deployment = await context.request.get(base + '/api/deployment/config')
    assert.equal(deployment.status(), 200)
    assert.ok(Array.isArray((await deployment.json()).targets))
    const settings = await context.request.get(base + '/api/admin/auth-config')
    assert.equal(settings.status(), 200)
    assert.equal((await settings.json()).captchaEnabled, true)
    assert.deepEqual(externalRequests, [])
    assert.deepEqual(errors, [])
    await page.screenshot({ path: path.join(root, '.local/local-dev/login-verified.png') })
    console.log('PASS independent local login: real captcha, admin permissions, local deployment config, no external browser requests')
    await context.close()
  } finally { await browser.close() }
})().catch(error => {
  console.error('Local browser verification failed:', String(error.message).replaceAll(config.adminPassword, '[redacted]'))
  process.exitCode = 1
})
