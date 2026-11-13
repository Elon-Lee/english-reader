import React, { useRef, useState } from 'react'
import { Button, Progress, Space, Typography } from 'antd'
import { csrfHeaders, getJson, requestJson } from '../api/client'
import { uploadCompanionAudio } from '../utils/companionAudioUpload.mjs'
import { requestPrivateImport } from '@site'

export default function ResumeAudioUpload({ task, base = '/api/workspace/imports', onComplete, messageApi }) {
  const input = useRef(null), busy = useRef(false)
  const [uploading, setUploading] = useState(false), [progress, setProgress] = useState(0), [error, setError] = useState('')
  const upload = async event => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file || busy.current) return
    busy.current = true; setUploading(true); setError('')
    try {
      if (base === '/api/workspace/imports' && !await requestPrivateImport(messageApi)) return
      await uploadCompanionAudio({ file, base, taskId: task.id, api: { csrfHeaders, getJson, requestJson }, onProgress: bytes => setProgress(Math.round(bytes / file.size * 100)) })
      messageApi.success('完整音频已上传，后台已开始处理')
      await onComplete?.()
    } catch (failure) {
      setError(`${failure.message || '上传中断'}。已收到的分段已保留，可再次补传。`)
      await onComplete?.()
    } finally { busy.current = false; setUploading(false) }
  }
  return <Space direction="vertical" size={4}>
    <input ref={input} type="file" accept=".mp3" aria-label={`补传音频 ${task.title || task.id}`} hidden onChange={upload} />
    <Button size="small" type="primary" loading={uploading} onClick={() => input.current?.click()}>{uploading ? `上传音频 ${progress}%` : '补传完整音频'}</Button>
    {uploading && <Progress percent={progress} size="small" />}
    {error && <Typography.Text type="danger" role="alert">{error}</Typography.Text>}
  </Space>
}
