import React, { useEffect, useState } from 'react'
import { Alert, Button, Form, Input, Modal, Progress, Segmented, Select, Tooltip, Typography } from 'antd'
import { CloudUploadOutlined, QuestionCircleOutlined } from '@ant-design/icons'
import { csrfHeaders, getJson, postJson, requestJson } from '../api/client'
import { bookLevels } from '../utils/levels.mjs'
import { MAX_TOPICS, bookTopics } from '../utils/topics.mjs'
import { selectImportFiles } from '../utils/importFiles.mjs'
import { uploadCompanionAudio } from '../utils/companionAudioUpload.mjs'
import { requestPrivateImport } from '@site'
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
  const [speechOptions, setSpeechOptions] = useState(null)
  const [speechLoading, setSpeechLoading] = useState(false)
  const [speechError, setSpeechError] = useState('')
  const [speechAttempt, setSpeechAttempt] = useState(0)
  const source = Form.useWatch('source', form) || 'file'
  const audioMode = Form.useWatch('audioMode', form) || 'none'
  const watchedFile = file?.name
  const speechEligible = source === 'file' && /\.(epub|pdf)$/i.test(watchedFile || '') && !localAudio && !matchedAudio && !matching && !matchError
  useEffect(() => {
    form.setFieldValue('audioMode', 'none')
  }, [form, watchedFile, source, localAudio, matchedAudio?.assetId])
  useEffect(() => {
    let cancelled = false
    setSpeechOptions(null); setSpeechError(''); setSpeechLoading(false)
    if (!open || !speechEligible) return undefined
    setSpeechLoading(true)
    getJson(`${base}/speech-options`).then(result => {
      if (!cancelled) {
        if (typeof result.available !== 'boolean' || !Array.isArray(result.voices)) throw new Error('AI 朗读选项暂不可用')
        setSpeechOptions(result)
      }
    }).catch(error => { if (!cancelled) setSpeechError(error.message || '无法加载 AI 朗读选项') }).finally(() => { if (!cancelled) setSpeechLoading(false) })
    return () => { cancelled = true }
  }, [base, open, speechEligible, speechAttempt])
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
      if (!official && !await requestPrivateImport(messageApi)) return
      const input = values.input?.trim()
      const kind = source === 'youtube' ? 'youtube' : /\.(pdf|epub)$/i.test(file?.name) ? 'document' : /\.mp3$/i.test(file?.name) ? 'mp3' : /\.(mp4|mov|m4v|mkv|webm)$/i.test(file?.name) ? 'video' : 'text'
      if (source === 'file' && !file) throw new Error('请选择要上传的文件')
      const filename = source === 'youtube' ? '' : file.name
      const key = `${kind}-import-${crypto.randomUUID?.() || Date.now()}`
      const title = values.title?.trim() || (source === 'youtube' ? '' : file.name.replace(/\.[^.]+$/, ''))
      const generateSpeech = values.audioMode === 'kokoro'
      if (generateSpeech && (!speechEligible || !speechOptions?.available || speechLoading)) throw new Error('AI 朗读当前不可用，请选择仅导入正文或重试')
      const created = await postJson(base, { kind, title, filename, sourceUrl: source === 'youtube' ? input : '', idempotencyKey: key, metadata: { series: values.series || '', level: values.level || '', topics: values.topics || [], matchedAudioFilename: matchedAudio?.filename || '', matchedAudioAssetId: matchedAudio?.assetId || '', awaitingAudioUpload: Boolean(localAudio), ...(generateSpeech ? { speechSynthesis: { engine: 'kokoro', voice: values.speechVoice || 'af_heart', speed: values.speechSpeed || 1 } } : {}) } })
      pendingTask = created.task.id
      if (source === 'file') {
        const uploads = [{ file, route: 'upload' }, ...(localAudio ? [{ file: localAudio, route: 'upload-audio' }] : [])]
        const total = uploads.reduce((sum, item) => sum + item.file.size, 0)
        let uploaded = 0
        for (const item of uploads) {
        if (item.route === 'upload-audio') {
          await uploadCompanionAudio({ file: item.file, base, taskId: created.task.id, api: { csrfHeaders, getJson, requestJson }, onProgress: bytes => setUploadProgress(Math.round((uploaded + bytes) / total * 100)) })
          uploaded += item.file.size
          continue
        }
        await new Promise((resolve, reject) => {
          const request = new XMLHttpRequest()
          request.open('POST', `${base}/${encodeURIComponent(created.task.id)}/${item.route}`)
          request.withCredentials = true
          const headers = csrfHeaders({ 'Content-Type': item.file.type || 'application/octet-stream', 'X-Upload-Filename': item.file.name, 'X-Upload-Size': String(item.file.size), ...(item === uploads[uploads.length - 1] ? { 'X-Import-Start-Processing': '1' } : {}) })
          Object.entries(headers).forEach(([key, value]) => request.setRequestHeader(key, value))
          request.upload.onprogress = event => { if (event.lengthComputable) setUploadProgress(Math.round((uploaded + event.loaded) / total * 100)) }
          request.onerror = () => reject(Object.assign(new Error('网络连接中断，任务和已上传文件已保留，请在导入记录中查看或继续处理'), { preserveTask: true }))
          request.onload = () => {
            let data = {}; try { data = JSON.parse(request.responseText || '{}') } catch {}
            if (request.status < 200 || request.status >= 300) reject(Object.assign(new Error(data.error || '上传失败'), { code: data.code, payload: data, preserveTask: request.status >= 500 }))
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
      if (source === 'youtube') void postJson(`${base}/${encodeURIComponent(taskId)}/complete`, {}).then(async result => {
        await onCreated?.()
        if (result.task?.status === 'complete') messageApi.success(official ? '官方内容已导入，请审核后发布' : '内容已导入学习空间')
      }).catch(async error => { await onCreated?.(); messageApi.error(error.message || '导入处理失败') })
    } catch (error) {
      if (pendingTask && error.preserveTask) { onClose(); await onCreated?.() }
      else if (pendingTask) await postJson(`${base}/${encodeURIComponent(pendingTask)}/cancel`, {}).catch(() => {})
      messageApi.error(error.message || '导入失败')
    } finally { setSubmitting(false) }
  }
  return <Modal title={official ? '内容导入' : '导入新的学习内容'} open={open} onCancel={submitting ? undefined : onClose} onOk={() => form.submit()} confirmLoading={submitting} okButtonProps={{ disabled: matching || (audioMode === 'kokoro' && (!speechOptions?.available || speechLoading || !speechEligible)) }} okText={uploadProgress > 0 && uploadProgress < 100 ? `上传 ${uploadProgress}%` : '创建导入任务'} cancelText="稍后再说">
    <Form form={form} layout="vertical" onFinish={submit} disabled={submitting}>
      <Form.Item label="内容来源" name="source" initialValue="file"><Segmented block options={[{ label: '上传文件', value: 'file' }, { label: 'YouTube', value: 'youtube' }]} /></Form.Item>
      <Form.Item label="读物标题" name="title"><Input placeholder="可选，默认使用文件名" /></Form.Item>
      <Form.Item label="系列" name="series"><Input placeholder="可选，例如 Oxford Bookworms" /></Form.Item>
      <Form.Item label={<span>等级 <Tooltip title="选择读物适合的词汇与阅读难度等级"><QuestionCircleOutlined /></Tooltip></span>} name="level"><Select allowClear placeholder="选择等级" options={bookLevels.map(level => ({ value: level.value, label: <span>{level.value} · {level.label} <Tooltip title={level.detail}><QuestionCircleOutlined /></Tooltip></span> }))} /></Form.Item>
      <Form.Item label={<span>主题 <Tooltip title="用于书城主题筛选和中文搜索，最多选择 3 个"><QuestionCircleOutlined /></Tooltip></span>} name="topics" extra="审核发布后作为书城标签展示。"><Select mode="multiple" allowClear maxCount={MAX_TOPICS} placeholder="选择主题" options={bookTopics.map(topic => ({ value: topic, label: topic }))} /></Form.Item>
      {source === 'youtube' ? <Form.Item label="YouTube 链接" name="input" rules={[{ required: true, message: '请输入 YouTube 链接' }]}><Input type="url" prefix={<CloudUploadOutlined />} placeholder="粘贴 YouTube 链接" /></Form.Item> : <Form.Item label="学习文件" extra="可同时选择文档和同名 MP3。"><input aria-label="学习文件" key={open ? 'open' : 'closed'} type="file" multiple disabled={submitting} accept=".txt,.md,.markdown,.pdf,.epub,.mp3,.mp4,.mov,.m4v,.mkv,.webm" onChange={chooseFiles} />{file && <div>{file.name}</div>}</Form.Item>}
      {source === 'file' && <div role="status" style={{ marginBottom: 16 }}>{localAudio ? <Text type="success">已匹配音频：{localAudio.name}（将一起上传）</Text> : matching ? <Text>正在匹配已上传音频…</Text> : matchedAudio ? <Text type="success">已匹配音频：{matchedAudio.filename}</Text> : matchError ? <Text type="danger">{matchError}</Text> : file && /\.(epub|pdf|txt|md|markdown)$/i.test(file.name) ? <Text type="secondary">未找到已上传的同名 MP3；可重新选择文档和 MP3 一起上传，或仅导入正文。</Text> : null}</div>}
      {speechEligible && <>
        <Form.Item label="朗读音频" name="audioMode" initialValue="none"><Segmented block options={[{ label: '仅导入正文', value: 'none' }, { label: 'AI 生成朗读', value: 'kokoro', disabled: !speechOptions?.available || speechLoading }]} /></Form.Item>
        {speechLoading ? <Text role="status">正在检查 AI 朗读服务…</Text> : speechError ? <Alert type="warning" showIcon message={speechError} action={<Button size="small" onClick={() => setSpeechAttempt(value => value + 1)}>重试</Button>} /> : !speechOptions?.available ? <Text type="secondary">{speechOptions?.notice || 'AI 朗读当前不可用'}</Text> : null}
        {audioMode === 'kokoro' && <>
          <Form.Item label="英文音色" name="speechVoice" initialValue="af_heart"><Select options={speechOptions?.voices || []} /></Form.Item>
          <Form.Item label="生成语速" name="speechSpeed" initialValue={1}><Select options={[{ value: .85, label: '舒缓 · 0.85 倍' }, { value: 1, label: '正常 · 1 倍' }, { value: 1.15, label: '稍快 · 1.15 倍' }]} /></Form.Item>
          <Alert type="info" showIcon message="AI 合成朗读" description="仅支持英文正文。上传后在后台生成，可查看进度或取消；生成音频占用存储空间。" style={{ marginBottom: 16 }} />
        </>}
      </>}
      {submitting && source === 'file' && <Progress percent={uploadProgress} status={uploadProgress >= 100 ? 'success' : 'active'} />}
      <Text type="secondary">{official ? '导入后属于官方内容，审核发布后才进入书城。' : '导入后仅自己可见，不进入内容管理。'}支持 TXT、Markdown、PDF、EPUB、MP3、MP4、MOV、M4V、MKV、WebM。</Text>
    </Form>
  </Modal>
}

