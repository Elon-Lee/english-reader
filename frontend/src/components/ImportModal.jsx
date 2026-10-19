import React, { useState } from 'react'
import { Form, Input, Modal, Progress, Segmented, Typography } from 'antd'
import { CloudUploadOutlined } from '@ant-design/icons'
import { csrfHeaders, postJson } from '../api/client'
import { handleMembershipLimit } from '../api/membershipLimit'
const { Text } = Typography

export default function ImportModal({ open, onClose, onResume, onCreated, messageApi, official = false }) {
  const base = official ? '/api/admin/content-imports' : '/api/workspace/imports'
  const [form] = Form.useForm()
  const [submitting, setSubmitting] = useState(false)
  const [file, setFile] = useState(null)
  const [uploadProgress, setUploadProgress] = useState(0)
  const source = Form.useWatch('source', form) || 'file'
  const submit = async values => {
    setSubmitting(true)
    try {
      const input = values.input?.trim()
      const kind = source === 'youtube' ? 'youtube' : /\.pdf$/i.test(file?.name) ? 'document' : /\.mp3$/i.test(file?.name) ? 'mp3' : /\.(mp4|mov|m4v|mkv|webm)$/i.test(file?.name) ? 'video' : 'text'
      if (source === 'file' && !file) throw new Error('请选择要上传的文件')
      const filename = source === 'youtube' ? '' : file.name
      const key = `${kind}-import-${crypto.randomUUID?.() || Date.now()}`
      const title = values.title?.trim() || (source === 'youtube' ? '' : file.name.replace(/\.[^.]+$/, ''))
      const created = await postJson(base, { kind, title, filename, sourceUrl: source === 'youtube' ? input : '', idempotencyKey: key })
      if (source === 'file') {
        await new Promise((resolve, reject) => {
          const request = new XMLHttpRequest()
          request.open('POST', `${base}/${encodeURIComponent(created.task.id)}/upload`)
          request.withCredentials = true
          const headers = csrfHeaders({ 'Content-Type': file.type || 'application/octet-stream', 'X-Upload-Filename': file.name })
          Object.entries(headers).forEach(([key, value]) => request.setRequestHeader(key, value))
          request.upload.onprogress = event => { if (event.lengthComputable) setUploadProgress(Math.round(event.loaded / event.total * 100)) }
          request.onerror = () => reject(new Error('网络中断，文件上传失败'))
          request.onload = () => {
            let data = {}; try { data = JSON.parse(request.responseText || '{}') } catch {}
            if (request.status < 200 || request.status >= 300) reject(Object.assign(new Error(data.error || '上传失败'), { code: data.code, payload: data }))
            else resolve(data)
          }
          request.send(file)
        })
      }
      const taskId = created.task.id
      onClose(); form.resetFields(); setFile(null); setUploadProgress(0); await onCreated?.(); messageApi.success('导入任务已提交，后台处理进度会自动更新')
      void postJson(`${base}/${encodeURIComponent(taskId)}/complete`, {}).then(async result => {
        await onCreated?.()
        if (result.task?.status === 'complete') messageApi.success(official ? '官方内容已导入，请审核后发布' : '内容已导入学习空间')
      }).catch(async error => { await onCreated?.(); if (official || !handleMembershipLimit(error, { onContinue: onResume })) messageApi.error(error.message || '导入处理失败') })
    } catch (error) { if (official || !handleMembershipLimit(error, { onClose, onContinue: onResume })) messageApi.error(error.message || '导入失败') } finally { setSubmitting(false) }
  }
  return <Modal title={official ? '内容导入' : '导入新的学习内容'} open={open} onCancel={submitting ? undefined : onClose} onOk={() => form.submit()} confirmLoading={submitting} okText={uploadProgress > 0 && uploadProgress < 100 ? `上传 ${uploadProgress}%` : '创建导入任务'} cancelText="稍后再说"><Form form={form} layout="vertical" onFinish={submit}><Form.Item label="内容来源" name="source" initialValue="file"><Segmented block options={[{ label: '上传文件', value: 'file' }, { label: 'YouTube', value: 'youtube' }]} /></Form.Item><Form.Item label="读物标题" name="title"><Input placeholder="可选，默认使用文件名" /></Form.Item><Form.Item label={source === 'youtube' ? 'YouTube 链接' : '学习文件'} name="input" rules={[{ required: true, message: source === 'youtube' ? '请输入 YouTube 链接' : '请选择要上传的文件' }]}><Input size="large" type={source === 'youtube' ? 'url' : 'file'} prefix={source === 'youtube' ? <CloudUploadOutlined /> : null} onChange={event => source === 'file' && setFile(event.target.files?.[0] || null)} placeholder={source === 'youtube' ? '粘贴 YouTube 链接' : undefined} /></Form.Item>{submitting && source === 'file' && <Progress percent={uploadProgress} status={uploadProgress >= 100 ? 'success' : 'active'} />}<Text type="secondary">{official ? '导入后属于官方内容，审核发布后才进入书城。' : '导入后仅自己可见，不进入内容管理。'}支持 TXT、Markdown、PDF、MP3、MP4、MOV、M4V、MKV、WebM。YouTube 高清最高 480p、流畅最高 240p；音视频会在后台处理。</Text></Form></Modal>
}

