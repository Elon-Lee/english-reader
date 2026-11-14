// Isolated browser acceptance of the two shared admin views; no real user data.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const http = require('node:http')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core')
const root = path.resolve(__dirname, '..'), output = '/private/tmp/admin-observability-browser'
async function serve(directory) {
  const server = http.createServer((request, response) => {
    let file = path.resolve(directory, `.${new URL(request.url, 'http://localhost').pathname}`)
    if (!file.startsWith(directory + '/') || !fs.existsSync(file) || !fs.statSync(file).isFile()) file = path.join(directory, 'index.html')
    response.setHeader('Content-Type', ({ '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml' })[path.extname(file)] || 'application/octet-stream')
    response.end(fs.readFileSync(file))
  })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  return { base: `http://127.0.0.1:${server.address().port}`, close: () => new Promise(resolve => server.close(resolve)) }
}
const disk = { total: 1000000, used: 250000, free: 750000, percent: 25, available: true }
;(async () => {
  fs.mkdirSync(output, { recursive: true })
  const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true })
  try {
    for (const site of ['cn', 'intl']) {
      const server = await serve(path.join(root, 'reader', site === 'cn' ? 'site' : 'site-intl'))
      const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } }), page = await context.newPage()
      let statsFail = true, detailFail = true, metricsFail = true, empty = false
      const calls = [], errors = []
      page.on('pageerror', error => errors.push(error.message))
      await context.route(`${server.base}/api/**`, async route => {
        const url = new URL(route.request().url()), pathname = url.pathname
        calls.push(url.pathname + url.search)
        let data = {}
        if (pathname === '/api/auth/me') data = { user: { id: 'fixture', email: 'admin@example.test', isAdmin: true } }
        else if (pathname === '/api/preferences') data = {}
        else if (pathname === '/api/resources') data = { privateImport: { allowed: false } }
        else if (pathname === '/api/admin/media-assets/statistics') {
          if (statsFail) return route.fulfill({ status: 503, json: { error: '统计暂不可用' } })
          const period = url.searchParams.get('period')
          const dates = period === 'year' ? ['2024-01-01', '2025-01-01', '2026-01-01'] : period === 'month' ? ['2026-09-01', '2026-10-01', '2026-11-01'] : ['2026-11-12', '2026-11-13', '2026-11-14']
          data = { period, start: dates[0], end: '2026-11-14', timezone: 'Asia/Shanghai', summary: { assetCount: 1, ownerCount: 1, variantCount: 1, totalBytes: 120000, originalBytes: 20000, generatedBytes: 100000, privateBytes: 0, officialBytes: 120000 }, history: dates.map((date, index) => ({ date, assets: empty ? 0 : index, variants: empty ? 0 : index, bytes: empty ? 0 : index * 10000 })) }
        } else if (pathname === '/api/admin/media-assets') {
          if (url.searchParams.has('ownerId')) {
            if (detailFail) return route.fulfill({ status: 503, json: { error: '资源暂不可用' } })
            data = { total: 1, assets: [{ id: 'epub', title: '有声读物', filename: 'narrated.epub', contentType: 'application/epub+zip', scope: 'official', createdAt: '2026-11-14T00:00:00Z', originalBytes: 20000, generatedBytes: 100000, storagePath: 'imports/narrated.epub', variants: [{ name: 'audio', contentType: 'audio/mpeg', bytes: 100000, duration: 12, storagePath: 'imports/narration.mp3' }] }] }
          } else data = { total: 1, users: [{ id: 'fixture', displayName: '测试管理员', email: 'admin@example.test', totalBytes: 120000, privateBytes: 0, officialBytes: 120000, assetCount: 1, audioCount: 1, videoCount: 0 }] }
        } else if (pathname === '/api/admin/server-metrics') {
          if (metricsFail) return route.fulfill({ status: 503, json: { error: '监测暂不可用' } })
          data = { sampledAt: '2026-11-14T03:00:00Z', platform: 'Linux', scope: 'container', cpu: { percent: 23.4, logicalCount: 2, loadAverage: [.1, .2, .3] }, memory: { total: 1000000, used: 500000, available: 500000, percent: 50 }, swap: { total: 1000, used: 0 }, disks: [{ ...disk, label: '系统磁盘', path: '/' }, { ...disk, label: '媒体所在磁盘', path: '/media' }], uptimeSeconds: 90000, process: { rss: 1024, uptimeSeconds: 800 }, network: { receivePerSecond: null, sendPerSecond: null }, container: { cpuLimit: 2, memory: { total: 1000, used: 500, percent: 50 } }, history: [{ at: '2026-11-14T03:00:00Z', cpu: 23.4, memory: 50, disk: 25 }], errors: [] }
        }
        return route.fulfill({ json: data })
      })
      try {
        await page.goto(`${server.base}/app?screen=admin&adminTab=media`)
        await page.getByText('统计暂不可用', { exact: true }).first().waitFor()
        assert.equal(calls.filter(call => call.includes('server-metrics')).length, 0)
        statsFail = false
        await page.getByRole('button', { name: '重试统计', exact: true }).first().click()
        await page.getByText('总占用空间', { exact: true }).waitFor()
        await page.getByRole('img', { name: '新增登记空间', exact: true }).waitFor()
        for (const [label, period] of [['按月', 'month'], ['按年', 'year']]) {
          const response = page.waitForResponse(response => response.url().includes(`statistics?period=${period}`))
          await page.locator('.ant-segmented-item').filter({ hasText: label }).click()
          await response
        }
        await page.screenshot({ path: path.join(output, `${site}-media.png`), fullPage: true })
        await page.getByRole('button', { name: '查看资源', exact: true }).click()
        await page.getByText('资源暂不可用', { exact: true }).waitFor()
        detailFail = false
        await page.getByRole('button', { name: '重试资源' }).click()
        await page.getByText('narrated.epub', { exact: true }).waitFor()
        await page.locator('.ant-modal .ant-table-row-expand-icon').first().click()
        await page.getByText('audio/mpeg', { exact: true }).waitFor()
        await page.getByText('imports/narration.mp3', { exact: true }).waitFor()
        await page.screenshot({ path: path.join(output, `${site}-mp3.png`), fullPage: true })
        await page.locator('.ant-modal-close').click()
        empty = true
        await page.getByRole('button', { name: '刷新媒体资产' }).click()
        await page.getByText('该时段暂无新增资源', { exact: true }).waitFor()
        await page.getByRole('tab', { name: '服务器观测', exact: true }).click()
        await page.getByText('监测暂不可用', { exact: true }).waitFor()
        metricsFail = false
        await page.getByRole('button', { name: '重试服务器指标' }).click()
        await page.getByText('23.4%', { exact: true }).first().waitFor()
        await page.getByText('容器内存', { exact: true }).waitFor()
        await page.getByRole('img', { name: 'CPU 使用率', exact: true }).waitFor()
        await page.screenshot({ path: path.join(output, `${site}-server.png`), fullPage: true })
        await page.getByRole('tab', { name: '媒体资产', exact: true }).click()
        const before = calls.filter(call => call.includes('server-metrics')).length
        if (site === 'cn') { await page.waitForTimeout(11000); assert.equal(calls.filter(call => call.includes('server-metrics')).length, before) }
        assert.deepEqual(errors, [])
        console.log(`${site}: media totals, periods, MP3 details, retries, empty state, server metrics and lazy polling passed`)
      } catch (error) {
        await page.screenshot({ path: path.join(output, `${site}-failure.png`), fullPage: true })
        console.error((await page.locator('body').innerText()).slice(-3000))
        throw error
      } finally { await context.close(); await server.close() }
    }
  } finally { await browser.close() }
})().catch(error => { console.error(error); process.exit(1) })
