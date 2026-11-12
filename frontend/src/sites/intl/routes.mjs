import { resolvePrivateRoute } from '../../utils/privateRoutes.mjs'

export function resolveInternationalRoute(pathname, search = '') {
  const route = resolvePrivateRoute(pathname, search)
  const params = new URLSearchParams(search)
  if ((pathname === '/app' || pathname === '/' && params.has('screen')) && params.get('screen') === 'membership') return { publicPage: '', screen: 'membership', exists: true }
  if (pathname === '/pricing') return { ...route, publicPage: 'pricing', exists: true }
  if (/^\/purchase\/[^/]+$/.test(pathname)) return { ...route, publicPage: 'purchase', exists: true }
  if (pathname === '/refunds') return { ...route, exists: true }
  return route
}

export function safeInternationalNextPath(value) {
  if (!value?.startsWith('/') || value.startsWith('//') || value.includes('\\')) return '/app'
  const url = new URL(value, 'https://international.invalid')
  if (url.origin !== 'https://international.invalid' || !['/app', '/pricing'].includes(url.pathname) && !/^\/purchase\/[^/]+$/.test(url.pathname)) return '/app'
  return resolveInternationalRoute(url.pathname, url.search).exists ? `${url.pathname}${url.search}` : '/app'
}
