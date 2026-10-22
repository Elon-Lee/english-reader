import test from 'node:test'
import assert from 'node:assert/strict'
import { createWordAudioCache, createWordAudioOutput, playWordFromStart } from './wordPronunciation.mjs'

class AudioStub extends EventTarget {
  readyState = 0
  currentTime = 1.2
  plays = []
  loads = 0
  load() { this.loads++ }
  play() { this.plays.push(this.currentTime); return Promise.resolve() }
  ready() { this.readyState = 4; this.dispatchEvent(new Event('canplaythrough')) }
}

test('cold pronunciation waits for buffered audio and starts at zero', async () => {
  const audio = new AudioStub(), abort = new AbortController()
  const playing = playWordFromStart(audio, abort.signal)
  await Promise.resolve()
  assert.deepEqual(audio.plays, [])
  audio.ready()
  await playing
  assert.deepEqual(audio.plays, [0])
})

test('repeated words reuse the prepared player and restart from the beginning', async () => {
  const cache = createWordAudioCache(() => new AudioStub())
  const audio = cache.prepare('Time')
  assert.equal(cache.prepare(' time '), audio)
  assert.equal(audio.loads, 1)
  audio.ready()
  await playWordFromStart(audio, new AbortController().signal)
  audio.currentTime = 1.1
  await playWordFromStart(cache.prepare('TIME'), new AbortController().signal)
  assert.deepEqual(audio.plays, [0, 0])
})

test('switching words or leaving cancels a pending load without late playback', async () => {
  const audio = new AudioStub(), abort = new AbortController()
  const playing = playWordFromStart(audio, abort.signal)
  abort.abort()
  await assert.rejects(playing, { name: 'AbortError' })
  audio.ready()
  assert.deepEqual(audio.plays, [])
})

test('load failures and timeouts reject rather than silently starting', async () => {
  const audio = new AudioStub()
  const playing = playWordFromStart(audio, new AbortController().signal)
  audio.dispatchEvent(new Event('error'))
  await assert.rejects(playing, /加载失败/)
  await assert.rejects(playWordFromStart(new AudioStub(), new AbortController().signal, 1), /超时/)
})

test('preload cache is bounded and replaces failed audio on retry', () => {
  const cache = createWordAudioCache(() => new AudioStub(), 2)
  const first = cache.prepare('one')
  cache.prepare('two'); cache.prepare('three')
  assert.notEqual(cache.prepare('one'), first)
  const failed = cache.prepare('two'); failed.error = new Error('network')
  assert.notEqual(cache.prepare('two'), failed)
})

class OutputStub {
  state = 'suspended'
  currentTime = 0
  timestamp = 0
  sampleRate = 48000
  destination = {}
  sources = []
  resumes = 0
  resume() { this.resumes++; this.state = 'running'; return Promise.resolve() }
  getOutputTimestamp() { return { contextTime: this.timestamp } }
  createMediaElementSource(audio) {
    const node = { audio, connected: false, connect() { this.connected = true }, disconnect() { this.connected = false } }
    this.sources.push(node)
    return node
  }
  close() { this.state = 'closed'; return Promise.resolve() }
}

test('first buffered word waits for device output, later words reuse the running output', async () => {
  const context = new OutputStub(), output = createWordAudioOutput(() => context)
  const first = new AudioStub(); first.ready()
  const playing = playWordFromStart(first, new AbortController().signal, 1000, output)
  assert.equal(context.resumes, 1, 'resume is invoked synchronously in the gesture')
  context.currentTime = 0.1
  await new Promise(resolve => setTimeout(resolve, 20))
  assert.deepEqual(first.plays, [], 'render clock alone is not device output readiness')
  context.timestamp = 0.04
  await playing
  assert.deepEqual(first.plays, [0])
  const second = new AudioStub(); second.ready()
  await playWordFromStart(second, new AbortController().signal, 1000, output)
  assert.deepEqual(second.plays, [0], 'warm output does not need a new timestamp advance')
  await playWordFromStart(first, new AbortController().signal, 1000, output)
  assert.equal(context.sources.length, 2, 'replaying does not create another source for the same element')
  assert.equal(context.sources[0].connected, true)
  assert.equal(context.sources[1].connected, false)
  output.clear()
  assert.equal(context.state, 'closed')
})

test('switch during first output startup cancels the old word, retry plays only the new word', async () => {
  const context = new OutputStub(), output = createWordAudioOutput(() => context)
  const first = new AudioStub(); first.ready()
  const abort = new AbortController()
  const pending = playWordFromStart(first, abort.signal, 1000, output)
  abort.abort()
  await assert.rejects(pending, { name: 'AbortError' })
  const second = new AudioStub(); second.ready()
  const next = playWordFromStart(second, new AbortController().signal, 1000, output)
  context.timestamp = 0.02
  await next
  assert.deepEqual(first.plays, [])
  assert.deepEqual(second.plays, [0])
  output.clear()
})

test('output startup timeout and autoplay denial do not consume the word', async () => {
  const context = new OutputStub(), output = createWordAudioOutput(() => context)
  const audio = new AudioStub(); audio.ready()
  await assert.rejects(playWordFromStart(audio, new AbortController().signal, 5, output), /输出启动超时/)
  context.resume = () => Promise.reject(new DOMException('blocked', 'NotAllowedError'))
  await assert.rejects(playWordFromStart(audio, new AbortController().signal, 1000, output), { name: 'NotAllowedError' })
  assert.deepEqual(audio.plays, [])
  context.resume = OutputStub.prototype.resume
  context.timestamp = 0.02
  await playWordFromStart(audio, new AbortController().signal, 1000, output)
  assert.deepEqual(audio.plays, [0])
  output.clear()
})

test('suspended output must become ready again and missing Web Audio falls back to buffered playback', async () => {
  const context = new OutputStub(), output = createWordAudioOutput(() => context)
  const audio = new AudioStub(); audio.ready(); context.timestamp = 0.02
  await playWordFromStart(audio, new AbortController().signal, 1000, output)
  context.state = 'suspended'; context.currentTime = 1
  const again = playWordFromStart(audio, new AbortController().signal, 1000, output)
  await Promise.resolve()
  assert.equal(audio.plays.length, 1)
  context.timestamp = 1.02
  await again
  assert.equal(audio.plays.length, 2)
  output.clear()
  await playWordFromStart(audio, new AbortController().signal, 1000, createWordAudioOutput(() => null))
  assert.equal(audio.plays.length, 3)
})

test('without output timestamps, wait for the reported output latency before first play', async () => {
  const context = new OutputStub(), output = createWordAudioOutput(() => context)
  context.getOutputTimestamp = undefined
  context.baseLatency = 0.01; context.outputLatency = 0.02
  const audio = new AudioStub(); audio.ready()
  const pending = playWordFromStart(audio, new AbortController().signal, 1000, output)
  context.currentTime = 0.015
  await new Promise(resolve => setTimeout(resolve, 20))
  assert.deepEqual(audio.plays, [])
  context.currentTime = 0.04
  await pending
  assert.deepEqual(audio.plays, [0])
  output.clear()
})
