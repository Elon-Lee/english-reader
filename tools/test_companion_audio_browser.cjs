// Only this browser context's fixture API is used; no production account writes.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const { createHash } = require('node:crypto')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core')
const base = process.env.READER_TEST_BASE || 'http://127.0.0.1:4173'
const output = process.env.READER_TEST_OUTPUT || '/private/tmp/english-reader-companion-upload-check'
const hash = body => createHash('sha256').update(body).digest('hex')

;(async () => {
  fs.mkdirSync(output, { recursive: true })
  const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true })
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } }), page = await context.newPage(), errors = []
    page.on('pageerror', error => errors.push(error.message))
    const audio = Buffer.concat([Buffer.alloc(256 * 1024, 97), Buffer.alloc(256 * 1024, 98), Buffer.from('complete ending')])
    let task, mode = 'interrupt', creates = 0, cancels = 0, finishes = 0, lostResponse = false, official = false
    const parts = new Map(), requests = [], officialCalls = []
    await context.route(`${base}/api/**`, async route => {
      const request = route.request(), rawPath = new URL(request.url()).pathname
      const path = rawPath.replace(/^\/api\/admin\/content-imports/, '/api/workspace/imports')
      if (rawPath.startsWith('/api/admin/content-imports/')) officialCalls.push(rawPath)
      let result = {}
      if (path === '/api/auth/me') result = { user: { id: 'transport-test', displayName: 'Upload test', email: 'upload@example.test', role: official ? 'admin' : 'user' } }
      else if (path === '/api/preferences') result = {}
      else if (path === '/api/workspace/books') result = { books: [] }
      else if (path === '/api/library') result = { items: [] }
      else if (path.endsWith('/match-audio')) result = { matched: null }
      else if (path === '/api/workspace/imports' && request.method() === 'POST') {
        creates++; assert.equal(request.postDataJSON().metadata.awaitingAudioUpload, true)
        task = { id: 'same-task', title: 'paired', kind: 'text', status: 'queued', progress: 15, sourceAssetId: 'document', awaitingAudioUpload: true, step: '文档已上传，等待完整配套音频' }
        result = { task }
      } else if (path === '/api/workspace/imports') result = { tasks: task ? [task] : [], total: task ? 1 : 0 }
      else if (path.endsWith('/upload')) {
        assert.equal(request.headers()['x-import-start-processing'], undefined)
        result = { task }
      } else if (path.endsWith('/audio-upload')) result = { chunkSize: 256 * 1024, filename: parts.size ? 'paired.mp3' : '', totalBytes: parts.size ? audio.length : 0, received: Object.fromEntries([...parts].map(([index, body]) => [index, hash(body)])), task }
      else if (path.endsWith('/upload-audio-chunk')) {
        const headers = request.headers(), index = Number(headers['x-upload-chunk-index']), body = request.postDataBuffer()
        requests.push(index)
        assert.ok(body.length <= 256 * 1024)
        assert.equal(headers['x-upload-size'], String(body.length))
        assert.equal(headers['x-upload-file-size'], String(audio.length))
        assert.equal(headers['x-upload-sha256'], hash(body))
        if (mode === 'interrupt' && index === 1) return route.abort('connectionreset')
        if (parts.has(index)) assert.deepEqual(parts.get(index), body)
        else parts.set(index, body)
        if (mode === 'resume' && index === 1 && !lostResponse) { lostResponse = true; return route.abort('connectionreset') }
        result = { index, sha256: hash(body) }
      } else if (path.endsWith('/complete-audio-upload')) {
        finishes++
        assert.deepEqual(Buffer.concat([...parts].sort((a, b) => a[0] - b[0]).map(([, body]) => body)), audio)
        assert.equal(request.postDataJSON().chunkHashes.length, 3)
        task = { ...task, awaitingAudioUpload: false, status: 'running', progress: 35, step: '提取文本并分句' }
        result = { task, asynchronous: true }
      } else if (path.endsWith('/cancel')) { cancels++; result = { task } }
      else if (path.endsWith('/upload-audio')) throw new Error('Companion audio must use bounded chunks')
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(result) })
    })
    await page.goto(`${base}/app?screen=library`, { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: '导入读物', exact: true }).click()
    await page.locator('.ant-modal input[type=file]').setInputFiles([
      { name: 'paired.txt', mimeType: 'text/plain', buffer: Buffer.from('Original text.') },
      { name: 'paired.mp3', mimeType: 'audio/mpeg', buffer: audio },
    ])
    await page.getByRole('button', { name: '创建导入任务', exact: true }).click()
    await page.getByRole('button', { name: '补传完整音频', exact: true }).waitFor({ timeout: 20000 })
    assert.equal(creates, 1); assert.equal(cancels, 0); assert.equal(finishes, 0)
    assert.deepEqual([...parts.keys()], [0])
    assert.equal(requests.filter(index => index === 1).length, 3)
    await page.getByText('等待完整配套音频', { exact: true }).waitFor()
    await page.screenshot({ path: `${output}/interrupted.png` })
    mode = 'resume'
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: '补传完整音频', exact: true }).waitFor()
    await page.getByLabel('补传音频 paired', { exact: true }).setInputFiles({ name: 'paired.mp3', mimeType: 'audio/mpeg', buffer: audio })
    await page.getByText('完整音频已上传，后台已开始处理', { exact: true }).waitFor({ timeout: 20000 })
    assert.equal(creates, 1); assert.equal(cancels, 0); assert.equal(finishes, 1)
    assert.equal(requests.filter(index => index === 0).length, 1)
    assert.equal(requests.filter(index => index === 1).length, 5)
    assert.deepEqual(errors, [])
    await page.screenshot({ path: `${output}/resumed.png` })
    official = true; mode = 'official'; parts.clear()
    task = { ...task, id: 'official-task', status: 'queued', progress: 15, awaitingAudioUpload: true, step: '文档已上传，等待完整配套音频' }
    await page.goto(`${base}/app?screen=admin&adminTab=catalog`, { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: '补传完整音频', exact: true }).waitFor()
    await page.getByLabel('补传音频 paired', { exact: true }).setInputFiles({ name: 'paired.mp3', mimeType: 'audio/mpeg', buffer: audio })
    await page.getByText('完整音频已上传，后台已开始处理', { exact: true }).waitFor({ timeout: 20000 })
    assert.equal(finishes, 2)
    assert.ok(officialCalls.includes('/api/admin/content-imports/official-task/complete-audio-upload'))
    assert.deepEqual(errors, [])
    await page.screenshot({ path: `${output}/official-resumed.png` })
    console.log('PASS: failed chunk retries, preserved document/task, refresh and resume, lost acknowledgment idempotency, checksums/full length, private/official upload APIs, processing only after all parts; zero page exceptions')
  } finally { await browser.close() }
})().catch(error => { console.error(error); process.exitCode = 1 })
