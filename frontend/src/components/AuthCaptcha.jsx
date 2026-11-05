import React, { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Button, Spin } from 'antd'
import { getJson, postJson } from '../api/client'
import './AuthCaptcha.css'

let loader
function loadSDK() {
  if (window.loadTAC) return Promise.resolve()
  if (!loader) loader = new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = '/tianai/load.js'
    script.onload = resolve
    script.onerror = () => { script.remove(); loader = null; reject(new Error('验证码资源加载失败，请重试')) }
    document.head.appendChild(script)
  })
  return loader
}

function CaptchaDialog({ request, finish }) {
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [attempt, setAttempt] = useState(0)
  const tacRef = useRef(null)
  const dialogRef = useRef(null)
  useEffect(() => {
    let active = true
    const dialog = dialogRef.current
    dialog.showModal()
    setLoading(true)
    setError('')
    const start = async () => {
      try {
        await loadSDK()
        if (!active) return
        const tac = await window.loadTAC('/tianai', {
          bindEl: '#auth-rotation-captcha',
          requestCaptchaDataUrl: '/api/auth/captcha/gen',
          validCaptchaUrl: '/api/auth/captcha/check',
          validSuccess: result => { if (active && result.data?.captchaToken) finish(null, result.data.captchaToken) },
          validFail: (_result, _captcha, instance) => { if (active) instance.reloadCaptcha() },
          btnCloseFun: () => finish(new Error('已取消验证码验证')),
        }, { logoUrl: null, i18n: { rotate_title: '拖动滑块，将图片转正' } })
        if (!active) { tac.destroyWindow(); return }
        tacRef.current = tac
        // Keep the official drawing/track SDK; use the app's same-origin JSON client.
        tac.config.doSendRequest = async options => {
          try {
            const payload = options.url.endsWith('/gen') ? { scene: request.scene, email: request.email } : options.data
            const result = await postJson(options.url, payload)
            if (active) { setError(''); setLoading(false) }
            return result
          } catch (failure) {
            if (active) {
              if (options.url.endsWith('/gen')) setError(failure.message || '验证码加载失败')
              setLoading(false)
            }
            return { code: 4001, msg: failure.message || '验证码暂不可用' }
          }
        }
        tac.init()
      } catch (failure) {
        if (active) { setError(failure.message || '验证码加载失败'); setLoading(false) }
      }
    }
    start()
    return () => { active = false; tacRef.current?.destroyWindow(); tacRef.current = null; dialog.close() }
  }, [request, attempt, finish])
  return createPortal(<dialog ref={dialogRef} className="auth-captcha-dialog" aria-label="旋转图片验证" onCancel={event => { event.preventDefault(); finish(new Error('已取消验证码验证')) }}>
    <div id="auth-rotation-captcha" />
    {(loading || error) && <div className="auth-captcha-status" role={error ? 'alert' : 'status'}>
      {error ? <><span>{error}</span><Button onClick={() => setAttempt(value => value + 1)}>重试</Button></> : <Spin tip="正在加载验证码"><div className="auth-captcha-loading" /></Spin>}
      <Button type="text" onClick={() => finish(new Error('已取消验证码验证'))}>取消验证</Button>
    </div>}
  </dialog>, document.body)
}

export function useAuthCaptcha() {
  const [request, setRequest] = useState(null)
  const pending = useRef(null)
  const finish = React.useCallback((error, token) => {
    const current = pending.current
    pending.current = null
    setRequest(null)
    if (error) current?.reject(error)
    else current?.resolve(token)
  }, [])
  useEffect(() => () => { pending.current?.reject(new Error('验证码已关闭')); pending.current = null }, [])
  const verify = async (scene, email) => {
    const config = await getJson('/api/auth/config')
    if (config.captchaEnabled === false) return ''
    if (config.captchaEnabled !== true) throw new Error('无法读取验证码配置，请重试')
    return new Promise((resolve, reject) => {
      pending.current = { resolve, reject }
      setRequest({ scene, email })
    })
  }
  return { verify, dialog: request ? <CaptchaDialog request={request} finish={finish} /> : null }
}
