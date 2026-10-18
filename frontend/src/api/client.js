export function csrfHeaders(headers = {}) {
  const csrf = document.cookie
    .split(/;\s*/)
    .find(value => value.startsWith('shiyue_csrf='))
    ?.split('=')
    .slice(1)
    .join('=')
  if (!csrf) return headers
  let token = csrf
  try { token = decodeURIComponent(csrf) } catch {}
  return { ...headers, 'X-CSRF-Token': token }
}

async function parseResponse(response) {
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const error = new Error(data.error || `请求失败（${response.status}）`)
    error.status = response.status
    error.code = data.code
    error.payload = data
    throw error
  }
  return data
}

export async function fetchWithCsrf(path, options = {}) {
  const request = { credentials: 'include', ...options }
  let response = await fetch(path, request)
  const method = String(request.method || 'GET').toUpperCase()
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const error = await response.clone().json().catch(() => ({}))
    if (response.status === 403 && error.code === 'csrf_failed') {
      const recovery = await fetch('/api/auth/me', { credentials: 'include', cache: 'no-store' })
      if (recovery.ok) {
        response = await fetch(path, { ...request, headers: csrfHeaders(request.headers) })
      }
    }
  }
  return response
}

export async function requestJson(path, options = {}) {
  const response = await fetchWithCsrf(path, options)
  return parseResponse(response)
}

export async function getJson(path, fallback) {
  try {
    return await requestJson(path)
  } catch (error) {
    if (arguments.length > 1) return fallback
    throw error
  }
}

export function postJson(path, payload) {
  return requestJson(path, {
    method: 'POST',
    headers: csrfHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(payload),
  })
}

export function deleteJson(path, payload) {
  return requestJson(path, {
    method: 'DELETE',
    headers: csrfHeaders({ 'Content-Type': 'application/json' }),
    body: payload === undefined ? undefined : JSON.stringify(payload),
  })
}
