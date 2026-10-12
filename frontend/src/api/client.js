export function csrfHeaders(headers = {}) {
  const csrf = document.cookie
    .split('; ')
    .find(value => value.startsWith('shiyue_csrf='))
    ?.split('=')
    .slice(1)
    .join('=')
  return csrf ? { ...headers, 'X-CSRF-Token': decodeURIComponent(csrf) } : headers
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

export async function requestJson(path, options = {}) {
  const response = await fetch(path, { credentials: 'include', ...options })
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
