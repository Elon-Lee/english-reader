import { spawn } from 'node:child_process'
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const [url, widthText, heightText, output] = process.argv.slice(2)
const width = Number(widthText), height = Number(heightText)
if (!url || !width || !height || !output) throw new Error('usage: cdp_screenshot.mjs URL WIDTH HEIGHT OUTPUT')
const chrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const profile = await mkdtemp(join(tmpdir(), 'shiyue-cdp-shot-'))
const port = 9400 + Math.floor(Math.random() * 400)
const child = spawn(chrome, ['--headless', '--disable-gpu', '--no-sandbox', '--disable-dev-shm-usage', '--disable-background-networking', '--disable-sync', `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, '--window-size=900,1000', 'about:blank'], { stdio: 'ignore' })
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
let socket, nextId = 0
try {
  let page
  for (let attempt = 0; attempt < 60; attempt += 1) {
    try { page = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(item => item.type === 'page'); if (page) break } catch {}
    await delay(100)
  }
  if (!page) throw new Error('Chrome debug page unavailable')
  socket = new WebSocket(page.webSocketDebuggerUrl)
  await new Promise((resolve, reject) => { socket.addEventListener('open', resolve, { once: true }); socket.addEventListener('error', reject, { once: true }) })
  const pending = new Map()
  socket.addEventListener('message', event => { const item = JSON.parse(event.data); if (item.id && pending.has(item.id)) { pending.get(item.id)(item); pending.delete(item.id) } })
  const send = (method, params = {}) => new Promise((resolve, reject) => { const id = ++nextId; pending.set(id, item => item.error ? reject(new Error(item.error.message)) : resolve(item.result)); socket.send(JSON.stringify({ id, method, params })); setTimeout(() => { if (pending.delete(id)) reject(new Error(`${method} timeout`)) }, 30000) })
  await send('Page.enable')
  await send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: width < 600, screenWidth: width, screenHeight: height })
  await send('Page.navigate', { url })
  await delay(Number(process.env.SHIYUE_SCREENSHOT_BUDGET_MS || 8000))
  const result = await send('Page.captureScreenshot', { format: 'png', fromSurface: true, captureBeyondViewport: false })
  await writeFile(output, Buffer.from(result.data, 'base64'))
} finally {
  try { socket?.close() } catch {}
  child.kill('SIGTERM')
  await delay(300)
  try { await rm(profile, { recursive: true, force: true, maxRetries: 3, retryDelay: 100 }) } catch {}
}
