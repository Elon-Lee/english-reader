// Companion MP3s use short, verified requests so interrupted uploads can resume.
const CHUNK_BYTES = 256 * 1024
const TRANSIENT = new Set(['incomplete_upload', 'request_timeout'])

export async function retryAudioRequest(request, sleep = delay => new Promise(resolve => setTimeout(resolve, delay))) {
  for (let attempt = 0; ; attempt++) {
    try { return await request() } catch (error) {
      const retryable = !error.status || error.status >= 500 || [408, 429].includes(error.status) || TRANSIENT.has(error.code)
      if (!retryable || attempt >= 2) throw error
      await sleep(1000 * 2 ** attempt)
    }
  }
}

export async function uploadCompanionAudio({ file, base, taskId, api, onProgress = () => {}, sleep }) {
  const root = `${base}/${encodeURIComponent(taskId)}`
  const send = async (path, options) => {
    const abort = new AbortController(), timeout = setTimeout(() => abort.abort(), 90000)
    try { return await api.requestJson(path, { ...options, signal: abort.signal }) }
    finally { clearTimeout(timeout) }
  }
  try {
    if (!file?.size || !/\.mp3$/i.test(file.name)) throw new Error('请选择与文档同名的完整 MP3')
    const state = await retryAudioRequest(() => api.getJson(`${root}/audio-upload`), sleep)
    if (state.chunkSize !== CHUNK_BYTES) throw new Error('音频上传服务版本不一致，请刷新页面后补传')
    if (state.totalBytes && (state.totalBytes !== file.size || state.filename !== file.name)) throw new Error('请选择上次上传的同一份完整 MP3，已上传分段会继续保留')
    const hashes = []
    for (let index = 0, offset = 0; offset < file.size; index++, offset += CHUNK_BYTES) {
      const chunk = file.slice(offset, offset + CHUNK_BYTES)
      const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', await chunk.arrayBuffer()))].map(value => value.toString(16).padStart(2, '0')).join('')
      hashes.push(digest)
      if (state.received?.[index] && state.received[index] !== digest) throw new Error('所选 MP3 与已上传内容不同，请选择原来的完整文件')
      if (!state.received?.[index]) {
        await retryAudioRequest(() => send(`${root}/upload-audio-chunk`, {
          method: 'POST',
          headers: api.csrfHeaders({ 'Content-Type': 'application/octet-stream', 'X-Upload-Filename': encodeURIComponent(file.name), 'X-Upload-Size': String(chunk.size), 'X-Upload-File-Size': String(file.size), 'X-Upload-Chunk-Index': String(index), 'X-Upload-SHA256': digest }),
          body: chunk,
        }), sleep)
      }
      onProgress(Math.min(file.size, offset + chunk.size))
    }
    return await retryAudioRequest(() => send(`${root}/complete-audio-upload`, {
      method: 'POST', headers: api.csrfHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ filename: file.name, totalBytes: file.size, chunkHashes: hashes }),
    }), sleep)
  } catch (error) {
    error.preserveTask = true
    throw error
  }
}
