// Isolated API fixtures verify UI behavior; model inference is tested separately.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const http = require('node:http')
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core')
const root = path.resolve(__dirname, '..')
const output = process.env.READER_TEST_OUTPUT || '/private/tmp/english-reader-kokoro-browser'
const voices = [{ value: 'af_heart', label: '美式英语 · 女声' }, { value: 'bf_emma', label: '英式英语 · 女声' }]
const sample = fs.readFileSync(path.join(root, '.local/kokoro/preflight.wav'))
const narration = Buffer.concat([sample.subarray(0, 44), sample.subarray(44), sample.subarray(44)])
narration.writeUInt32LE(narration.length - 8, 4)
narration.writeUInt32LE(narration.length - 44, 40)

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
  const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true })
  try {
    for (const site of ['cn', 'intl']) {
      const server = await serve(path.join(root, 'reader', site === 'cn' ? 'site' : 'site-intl'))
      const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } })
      const page = await context.newPage(), errors = [], calls = []
      let state = 'failure', payload = null, match = false
      page.on('pageerror', error => errors.push(error.message))
      const base = server.base, imports = site === 'cn' ? '/api/admin/content-imports' : '/api/workspace/imports'
      await context.route(`${base}/api/**`, async route => {
        const request = route.request(), pathname = new URL(request.url()).pathname
        calls.push(pathname)
        let data = {}
        if (pathname === '/api/auth/me') data = { user: { id: 'fixture', email: 'kokoro@example.test', isAdmin: true, role: 'admin' } }
        else if (pathname === '/api/resources') data = { privateImport: { allowed: true } }
        else if (pathname === '/api/preferences') data = { focusMode: false }
        else if (pathname === '/api/workspace/books') data = { books: [] }
        else if (pathname === '/api/library') data = { items: [] }
        else if (pathname === '/api/admin/catalog/sources') data = { sources: [] }
        else if (pathname.endsWith('/match-audio')) data = { matched: match ? { assetId: 'original', filename: 'narration.mp3' } : null }
        else if (pathname.endsWith('/speech-options')) {
          if (state === 'failure') return route.fulfill({ status: 503, json: { error: '测试：朗读服务暂不可用' } })
          data = { available: state === 'ready', voices, notice: 'AI 朗读尚未安装，请联系管理员。' }
        } else if (pathname === imports && request.method() === 'POST') {
          payload = request.postDataJSON()
          data = { task: { id: 'narration-task', status: 'uploading' } }
        } else if (pathname.endsWith('/upload')) data = { task: { id: 'narration-task', status: 'queued' }, asynchronous: true }
        else if (pathname === imports) data = { tasks: [], total: 0 }
        else if (pathname.endsWith('/reader')) data = { book: { id: 'narrated', title: 'Kokoro narration fixture', duration: 6.3, resourceType: 'audio', speechSynthesis: { synthetic: true, engine: 'kokoro' }, sentences: [0, 1].map(index => ({ id: `s-${index + 1}`, text: 'A quiet morning is a good time to read a book.', start: index * 3.15, end: (index + 1) * 3.15, timingPolicy: 'kokoro-sentence-audio', words: [{ text: 'A', start: index * 3.15 + .275, end: index * 3.15 + .35, estimated: true }] })), mediaAssets: [{ id: 'document', contentType: 'application/epub+zip', variants: [{ name: 'audio', contentType: 'audio/wav', url: '/api/media/narration' }] }], progress: {} } }
        else if (pathname === '/api/media/narration') {
          const range = request.headers().range?.match(/^bytes=(\d+)-(\d*)$/)
          const start = range ? Number(range[1]) : 0, end = range?.[2] ? Math.min(Number(range[2]), narration.length - 1) : narration.length - 1
          return route.fulfill({ status: range ? 206 : 200, contentType: 'audio/wav', body: narration.subarray(start, end + 1), headers: {
            'Accept-Ranges': 'bytes', 'Content-Length': String(end - start + 1),
            ...(range ? { 'Content-Range': `bytes ${start}-${end}/${narration.length}` } : {}),
          } })
        }
        else if (/vocabulary|annotations/.test(pathname)) data = { items: [] }
        return route.fulfill({ json: data })
      })
      try {
        await page.goto(`${base}/app?screen=${site === 'cn' ? 'admin&adminTab=catalog' : 'library'}`)
        await page.getByRole('button', { name: site === 'cn' ? /内容导入/ : /导入读物/ }).first().click()
        const upload = page.getByLabel('学习文件', { exact: true })
        const epub = name => ({ name, mimeType: 'application/epub+zip', buffer: Buffer.from('test-only EPUB upload') })
        await upload.setInputFiles(epub('narration.epub'))
        await page.getByText('测试：朗读服务暂不可用', { exact: true }).waitFor()
        state = 'unavailable'
        await page.getByRole('button', { name: /重\s*试/, exact: true }).click()
        await page.getByText('AI 朗读尚未安装，请联系管理员。', { exact: true }).waitFor()
        assert(await page.getByRole('radio', { name: 'AI 生成朗读', exact: true }).isDisabled())
        state = 'ready'
        await upload.setInputFiles(epub('narration2.pdf'))
        await page.locator('.ant-segmented-item:not(.ant-segmented-item-disabled)').filter({ hasText: 'AI 生成朗读' }).click()
        await page.locator('.ant-form-item').filter({ has: page.getByText('英文音色', { exact: true }) }).locator('.ant-select-selector').click()
        await page.getByText('英式英语 · 女声', { exact: true }).click()
        await page.screenshot({ path: path.join(output, `${site}-speech-options.png`), fullPage: true })
        await page.getByRole('button', { name: '创建导入任务', exact: true }).click()
        await page.getByText('导入任务已提交，后台处理进度会自动更新', { exact: true }).waitFor()
        assert.deepEqual(payload.metadata.speechSynthesis, { engine: 'kokoro', voice: 'bf_emma', speed: 1 })
        assert.equal(payload.metadata.awaitingAudioUpload, false)
        assert.equal(payload.metadata.matchedAudioAssetId, '')
        await page.getByRole('button', { name: site === 'cn' ? /内容导入/ : /导入读物/ }).first().click()
        match = true
        const optionsBefore = calls.filter(value => value.endsWith('/speech-options')).length
        await upload.setInputFiles(epub('original.epub'))
        await page.getByText('已匹配音频：narration.mp3', { exact: true }).waitFor()
        assert.equal(await page.getByText('AI 生成朗读', { exact: true }).count(), 0)
        // An initial request can be cancelled while matching starts; no AI mode survives a match.
        assert(calls.filter(value => value.endsWith('/speech-options')).length <= optionsBefore + 1)
        await page.goto(`${base}/app?screen=reader&id=narrated&reader=workspace`)
        await page.getByRole('heading', { name: 'Kokoro narration fixture' }).waitFor()
        assert.equal(await page.getByText('AI 合成朗读', { exact: true }).count(), 0)
        await page.waitForFunction(() => document.querySelector('audio')?.readyState >= 1)
        assert(Math.abs(await page.locator('audio').evaluate(audio => audio.duration) - 6.3) < .01)
        await page.getByRole('button', { name: '练这一句', exact: true }).first().click()
        const listen = page.getByRole('button', { name: /听这一句原音/ })
        await listen.click()
        await page.waitForFunction(() => document.querySelector('audio')?.currentTime > .2)
        await page.getByText('原句播放结束，接下来录一句。', { exact: true }).waitFor()
        assert(await page.locator('audio').evaluate(audio => audio.paused))
        assert(Math.abs(await page.locator('audio').evaluate(audio => audio.currentTime) - 3.15) < .1)
        await page.screenshot({ path: path.join(output, `${site}-narrated-reader.png`), fullPage: true })
        assert.deepEqual(errors, [])
        console.log(`${site}: speech availability, retry, request, original-audio priority, reader and media passed`)
      } catch (error) {
        await page.screenshot({ path: path.join(output, `${site}-failure.png`), fullPage: true })
        console.error((await page.locator('body').innerText()).slice(-2500))
        throw error
      } finally { await context.close(); await server.close() }
    }
  } finally { await browser.close() }
})().catch(error => { console.error(error); process.exit(1) })
