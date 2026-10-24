import React, { useEffect, useState } from 'react'
import { Form, Input, Modal, Progress, Segmented, Select, Tooltip, Typography } from 'antd'
import { CloudUploadOutlined, QuestionCircleOutlined } from '@ant-design/icons'
import { csrfHeaders, getJson, postJson } from '../api/client'
import { handleMembershipLimit } from '../api/membershipLimit'
import { bookLevels } from '../utils/levels.mjs'
import { MAX_TOPICS, bookTopics } from '../utils/topics.mjs'
import { selectImportFiles } from '../utils/importFiles.mjs'
const { Text } = Typography

export default function ImportModal({ open, onClose, onResume, onCreated, messageApi, official = false }) {
  const base = official ? '/api/admin/content-imports' : '/api/workspace/imports'
  const [form] = Form.useForm()
  const [submitting, setSubmitting] = useState(false)
  const [file, setFile] = useState(null)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [matchedAudio, setMatchedAudio] = useState(null)
  const [localAudio, setLocalAudio] = useState(null)
  const [matching, setMatching] = useState(false)
  const [matchError, setMatchError] = useState('')
  const source = Form.useWatch('source', form) || 'file'
  const watchedFile = file?.name
  useEffect(() => {
    let cancelled = false
    setMatchedAudio(null); setMatchError(''); setMatching(false)
    if (!watchedFile || source !== 'file' || localAudio || !/\.(epub|pdf|txt|md|markdown)$/i.test(watchedFile)) return undefined
    setMatching(true)
    getJson(`${base}/match-audio?filename=${encodeURIComponent(watchedFile)}`).then(result => { if (!cancelled) setMatchedAudio(result.matched || null) }).catch(error => { if (!cancelled) setMatchError(error.message || '音频匹配失败') }).finally(() => { if (!cancelled) setMatching(false) })
    return () => { cancelled = true }
  }, [base, source, watchedFile, localAudio])
  const chooseFiles = event => {
    try {
      if (!event.target.files?.length) return
      const selected = selectImportFiles(event.target.files)
      setFile(selected.file); setLocalAudio(selected.audio); setMatchedAudio(null); setMatchError('')
    } catch (error) { event.target.value = ''; setFile(null); setLocalAudio(null); messageApi.error(error.message) }
  }
  const submit = async values => {
    setSubmitting(true)
    let pendingTask = null
    try {
      const input = values.input?.trim()
      const kind = source === 'youtube' ? 'youtube' : /\.(pdf|epub)$/i.test(file?.name) ? 'document' : /\.mp3$/i.test(file?.name) ? 'mp3' : /\.(mp4|mov|m4v|mkv|webm)$/i.test(file?.name) ? 'video' : 'text'
      if (source === 'file' && !file) throw new Error('请选择要上传的文件')
      const filename = source === 'youtube' ? '' : file.name
      const key = `${kind}-import-${crypto.randomUUID?.() || Date.now()}`
      const title = values.title?.trim() || (source === 'youtube' ? '' : file.name.replace(/\.[^.]+$/, ''))
      const created = await postJson(base, { kind, title, filename, sourceUrl: source === 'youtube' ? input : '', idempotencyKey: key, metadata: { series: values.series || '', level: values.level || '', topics: values.topics || [], matchedAudioFilename: matchedAudio?.filename || '', matchedAudioAssetId: matchedAudio?.assetId || '' } })
      pendingTask = created.task.id
      if (source === 'file') {
        const uploads = [{ file, route: 'upload' }, ...(localAudio ? [{ file: localAudio, route: 'upload-audio' }] : [])]
        const total = uploads.reduce((sum, item) => sum + item.file.size, 0)
        let uploaded = 0
        for (const item of uploads) {
        await new Promise((resolve, reject) => {
          const request = new XMLHttpRequest()
          request.open('POST', `${base}/${encodeURIComponent(created.task.id)}/${item.route}`)
          request.withCredentials = true
          const headers = csrfHeaders({ 'Content-Type': item.file.type || 'application/octet-stream', 'X-Upload-Filename': item.file.name })
          Object.entries(headers).forEach(([key, value]) => request.setRequestHeader(key, value))
          request.upload.onprogress = event => { if (event.lengthComputable) setUploadProgress(Math.round((uploaded + event.loaded) / total * 100)) }
          request.onerror = () => reject(new Error('网络中断，文件上传失败'))
          request.onload = () => {
            let data = {}; try { data = JSON.parse(request.responseText || '{}') } catch {}
            if (request.status < 200 || request.status >= 300) reject(Object.assign(new Error(data.error || '上传失败'), { code: data.code, payload: data }))
            else resolve(data)
          }
          request.send(item.file)
        })
        uploaded += item.file.size
        }
      }
      const taskId = created.task.id
      pendingTask = null
      onClose(); form.resetFields(); setFile(null); setLocalAudio(null); setMatchedAudio(null); setUploadProgress(0); await onCreated?.(); messageApi.success('导入任务已提交，后台处理进度会自动更新')
      void postJson(`${base}/${encodeURIComponent(taskId)}/complete`, {}).then(async result => {
        await onCreated?.()
        if (result.task?.status === 'complete') messageApi.success(official ? '官方内容已导入，请审核后发布' : '内容已导入学习空间')
      }).catch(async error => { await onCreated?.(); if (official || !handleMembershipLimit(error, { onContinue: onResume })) messageApi.error(error.message || '导入处理失败') })
    } catch (error) {
      if (pendingTask) await postJson(`${base}/${encodeURIComponent(pendingTask)}/cancel`, {}).catch(() => {})
      if (official || !handleMembershipLimit(error, { onClose, onContinue: onResume })) messageApi.error(error.message || '导入失败')
    } finally { setSubmitting(false) }
  }
  return <Modal title={official ? '内容导入' : '导入新的学习内容'} open={open} onCancel={submitting ? undefined : onClose} onOk={() => form.submit()} confirmLoading={submitting} okButtonProps={{ disabled: matching }} okText={uploadProgress > 0 && uploadProgress < 100 ? `上传 ${uploadProgress}%` : '创建导入任务'} cancelText="稍后再说"><Form form={form} layout="vertical" onFinish={submit} disabled={submitting}><Form.Item label="内容来源" name="source" initialValue="file"><Segmented block options={[{ label: '上传文件', value: 'file' }, { label: 'YouTube', value: 'youtube' }]} /></Form.Item><Form.Item label="读物标题" name="title"><Input placeholder="可选，默认使用文件名" /></Form.Item><Form.Item label="系列" name="series"><Input placeholder="可选，例如 Oxford Bookworms" /></Form.Item><Form.Item label={<span>等级 <Tooltip title="选择读物适合的词汇与阅读难度等级"><QuestionCircleOutlined /></Tooltip></span>} name="level"><Select allowClear placeholder="选择等级" options={bookLevels.map(level => ({ value: level.value, label: <span>{level.value} · {level.label} <Tooltip title={level.detail}><QuestionCircleOutlined /></Tooltip></span> }))} /></Form.Item><Form.Item label={<span>主题 <Tooltip title="用于书城主题筛选和中文搜索，最多选择 3 个"><QuestionCircleOutlined /></Tooltip></span>} name="topics" extra="审核发布后作为书城标签展示。"><Select mode="multiple" allowClear maxCount={MAX_TOPICS} placeholder="选择主题" options={bookTopics.map(topic => ({ value: topic, label: topic }))} /></Form.Item>{source === 'youtube' ? <Form.Item label="YouTube 链接" name="input" rules={[{ required: true, message: '请输入 YouTube 链接' }]}><Input type="url" prefix={<CloudUploadOutlined />} placeholder="粘贴 YouTube 链接" /></Form.Item> : <Form.Item label="学习文件" extra="可同时选择文档和同名 MP3。"><input aria-label="学习文件" key={open ? 'open' : 'closed'} type="file" multiple disabled={submitting} accept=".txt,.md,.markdown,.pdf,.epub,.mp3,.mp4,.mov,.m4v,.mkv,.webm" onChange={chooseFiles} />{file && <div>{file.name}</div>}</Form.Item>}{source === 'file' && <div role="status" style={{ marginBottom: 16 }}>{localAudio ? <Text type="success">已匹配音频：{localAudio.name}（将一起上传）</Text> : matching ? <Text>正在匹配已上传音频…</Text> : matchedAudio ? <Text type="success">已匹配音频：{matchedAudio.filename}</Text> : matchError ? <Text type="danger">{matchError}</Text> : file && /\.(epub|pdf|txt|md|markdown)$/i.test(file.name) ? <Text type="secondary">未找到已上传的同名 MP3；可重新选择文档和 MP3 一起上传，或仅导入正文。</Text> : null}</div>}{submitting && source === 'file' && <Progress percent={uploadProgress} status={uploadProgress >= 100 ? 'success' : 'active'} />}<Text type="secondary">{official ? '导入后属于官方内容，审核发布后才进入书城。' : '导入后仅自己可见，不进入内容管理。'}支持 TXT、Markdown、PDF、EPUB、MP3、MP4、MOV、M4V、MKV、WebM。</Text></Form></Modal>
}

