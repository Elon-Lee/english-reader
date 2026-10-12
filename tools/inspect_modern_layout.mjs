import { spawn } from 'node:child_process'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const chrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const profile = await mkdtemp(join(tmpdir(), 'shiyue-layout-'))
const port = 9333
const child = spawn(chrome, ['--headless', '--disable-gpu', '--no-sandbox', '--force-device-scale-factor=1', `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`, '--window-size=390,844', process.argv[2] || 'http://127.0.0.1:5173/modern-assets/'], { stdio: 'ignore' })
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
try {
  let page
  for (let attempt = 0; attempt < 40; attempt += 1) {
    try { page = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(item => item.type === 'page'); if (page) break } catch {}
    await delay(100)
  }
  if (!page) throw new Error('Chrome debug page unavailable')
  const socket = new WebSocket(page.webSocketDebuggerUrl)
  await new Promise((resolve, reject) => { socket.addEventListener('open', resolve, { once: true }); socket.addEventListener('error', reject, { once: true }) })
  const result = await new Promise((resolve, reject) => {
    socket.addEventListener('message', event => { const item = JSON.parse(event.data); if (item.id === 1) resolve(item.result.result.value) })
    socket.send(JSON.stringify({ id: 1, method: 'Runtime.evaluate', params: { returnByValue: true, awaitPromise: true, expression: `(async()=>{await new Promise(r=>setTimeout(r,3000));const auth=document.querySelector('.modern-auth'),card=document.querySelector('.modern-auth-card');return JSON.stringify({innerWidth,devicePixelRatio,bodyScroll:document.body.scrollWidth,auth:auth&&auth.getBoundingClientRect().toJSON(),card:card&&card.getBoundingClientRect().toJSON(),media:matchMedia('(max-width: 640px)').matches})})()` } }))
    setTimeout(() => reject(new Error('CDP timeout')), 10000)
  })
  console.log(result)
  socket.close()
} finally {
  child.kill('SIGTERM')
  await rm(profile, { recursive: true, force: true })
}
