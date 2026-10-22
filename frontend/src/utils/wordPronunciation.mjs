// Keep only a few recently inspected words warm; never preload the whole book.
export function createWordAudioCache(createAudio = () => new Audio(), limit = 12) {
  const entries = new Map()
  return {
    prepare(word) {
      const key = String(word).trim().toLowerCase()
      let audio = entries.get(key)
      if (audio?.error) { entries.delete(key); audio = null }
      if (!audio) {
        audio = createAudio()
        audio.preload = 'auto'
        audio.src = '/api/word-tts?word=' + encodeURIComponent(key)
        audio.load()
      }
      entries.delete(key)
      entries.set(key, audio)
      if (entries.size > limit) entries.delete(entries.keys().next().value)
      return audio
    },
    clear() { entries.clear() },
  }
}

// One output graph per reader. Buffer readiness alone does not tell us whether
// the device has started consuming samples after a fresh page load.
export function createWordAudioOutput(createContext = () => {
  const Context = globalThis.AudioContext || globalThis.webkitAudioContext
  return Context ? new Context({ latencyHint: 'interactive' }) : null
}) {
  let context, activeNode, warm = false, nodes = new WeakMap()
  return {
    ready(audio, signal, timeoutMs = 15000) {
      if (signal.aborted) return Promise.reject(new DOMException('Pronunciation cancelled', 'AbortError'))
      context ||= createContext()
      if (!context) return Promise.resolve()
      const output = context
      let node = nodes.get(audio)
      if (!node) { node = output.createMediaElementSource(audio); nodes.set(audio, node) }
      if (activeNode !== node) {
        activeNode?.disconnect()
        node.connect(output.destination)
        activeNode = node
      }
      if (output.state !== 'running') warm = false
      const startedAt = output.currentTime
      // Call resume inside the click gesture, before waiting for the network.
      const resumed = output.resume()
      return new Promise((resolve, reject) => {
        let poll, timeout, settled = false
        const done = error => {
          if (settled) return
          settled = true
          clearTimeout(poll); clearTimeout(timeout)
          signal.removeEventListener('abort', cancelled)
          error ? reject(error) : resolve()
        }
        const cancelled = () => done(new DOMException('Pronunciation cancelled', 'AbortError'))
        const check = () => {
          if (settled) return
          if (context !== output || output.state === 'closed') return done(new Error('单词音频输出已关闭，请重试'))
          const timestamp = output.getOutputTimestamp?.()
          const consuming = timestamp
            ? timestamp.contextTime > startedAt
            : output.currentTime > startedAt + (output.baseLatency || 0) + (output.outputLatency || 0) + 128 / output.sampleRate
          if (output.state === 'running' && (warm || consuming)) { warm = true; done() }
          else poll = setTimeout(check, 10)
        }
        signal.addEventListener('abort', cancelled, { once: true })
        timeout = setTimeout(() => done(new Error('单词音频输出启动超时，请重试')), timeoutMs)
        Promise.resolve(resumed).then(check, done)
      })
    },
    clear() {
      activeNode?.disconnect()
      activeNode = null; nodes = new WeakMap(); warm = false
      const previous = context
      context = null
      if (previous && previous.state !== 'closed') previous.close().catch(() => {})
    },
  }
}

// Wait for both the clip and its output without consuming any spoken samples.
export async function playWordFromStart(audio, signal, timeoutMs = 15000, output) {
  const aborted = () => new DOMException('Pronunciation cancelled', 'AbortError')
  if (signal.aborted) throw aborted()
  const waitUntilReady = () => new Promise((resolve, reject) => {
    let timer
    const done = error => {
      clearTimeout(timer)
      audio.removeEventListener('canplaythrough', ready)
      audio.removeEventListener('error', failed)
      signal.removeEventListener('abort', cancelled)
      error ? reject(error) : resolve()
    }
    const ready = () => { if (audio.readyState >= 4) done() }
    const failed = () => done(new Error('单词发音加载失败'))
    const cancelled = () => done(aborted())
    audio.addEventListener('canplaythrough', ready)
    audio.addEventListener('error', failed)
    signal.addEventListener('abort', cancelled, { once: true })
    timer = setTimeout(() => done(new Error('单词发音加载超时，请重试')), timeoutMs)
    if (audio.error) failed()
    else ready()
  })
  await Promise.all([output?.ready(audio, signal, timeoutMs), waitUntilReady()])
  if (signal.aborted) throw aborted()
  if (audio.currentTime !== 0) {
    audio.currentTime = 0
    await waitUntilReady()
  }
  if (signal.aborted) throw aborted()
  await audio.play()
}
