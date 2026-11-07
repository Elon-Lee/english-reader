import test from 'node:test'
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { retryAudioRequest, uploadCompanionAudio } from './companionAudioUpload.mjs'

const digest = data => createHash('sha256').update(data).digest('hex')
const file = () => new File([new Uint8Array(256 * 1024).fill(97), new Uint8Array(256 * 1024).fill(98), 'end'], 'paired.mp3')
function transport(state = {}) {
  const calls = [], api = {
    getJson: async () => ({ chunkSize: 256 * 1024, received: {}, ...state }),
    csrfHeaders: headers => ({ ...headers, 'X-CSRF-Token': 'test' }),
    requestJson: async (path, options) => { calls.push({ path, options }); return { task: { status: 'running' } } },
  }
  return { calls, api }
}
test('retries transient failures but stops on ownership and validation rejection', async () => {
  let attempts = 0
  assert.equal(await retryAudioRequest(async () => { if (++attempts < 3) throw new TypeError('connection lost'); return 'ok' }, async () => {}), 'ok')
  assert.equal(attempts, 3)
  attempts = 0
  await assert.rejects(retryAudioRequest(async () => { attempts++; throw Object.assign(new Error('forbidden'), { status: 403 }) }, async () => {}))
  assert.equal(attempts, 1)
})
test('resumes verified parts, sends bounded chunks, then finalizes on the same task', async () => {
  const audio = file(), { calls, api } = transport({ filename: 'paired.mp3', totalBytes: audio.size, received: { 0: digest(new Uint8Array(256 * 1024).fill(97)) } }), progress = []
  await uploadCompanionAudio({ file: audio, base: '/api/workspace/imports', taskId: 'original-task', api, onProgress: value => progress.push(value), sleep: async () => {} })
  assert.equal(calls.length, 3)
  for (const call of calls.slice(0, 2)) {
    assert.ok(call.path.includes('/original-task/upload-audio-chunk'))
    assert.ok(call.options.body.size <= 256 * 1024)
    assert.equal(call.options.headers['X-Upload-Size'], String(call.options.body.size))
    assert.equal(call.options.headers['X-CSRF-Token'], 'test')
  }
  const finish = calls.at(-1)
  assert.ok(finish.path.endsWith('/complete-audio-upload'))
  const payload = JSON.parse(finish.options.body)
  assert.equal(payload.totalBytes, audio.size); assert.equal(payload.chunkHashes.length, 3)
  assert.equal(progress.at(-1), audio.size)
})
test('a different same-sized audio cannot silently reuse existing parts', async () => {
  const audio = file(), { api, calls } = transport({ totalBytes: audio.size, filename: audio.name, received: { 0: '0'.repeat(64) } })
  await assert.rejects(uploadCompanionAudio({ file: audio, base: '/api/workspace/imports', taskId: 'task', api }), error => error.preserveTask && /不同/.test(error.message))
  assert.equal(calls.length, 0)
})
test('exhausted retries preserve the document task and never finalize partial audio', async () => {
  const { api, calls } = transport()
  api.requestJson = async path => { calls.push(path); throw new TypeError('connection lost') }
  await assert.rejects(uploadCompanionAudio({ file: file(), base: '/api/workspace/imports', taskId: 'task', api, sleep: async () => {} }), error => error.preserveTask)
  assert.equal(calls.length, 3)
  assert.ok(calls.every(path => path.endsWith('/upload-audio-chunk')))
})
