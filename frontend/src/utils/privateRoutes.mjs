const screens = new Set(['workspace', 'catalog', 'library', 'stats', 'vocab', 'rewards', 'admin', 'platform', 'settings', 'reader'])
const authPaths = new Set(['/login', '/register', '/verify-email', '/reset-password'])
const policyPaths = new Set(['/terms', '/privacy', '/content-policy', '/copyright'])

export function resolvePrivateRoute(pathname, search = '') {
  const params = new URLSearchParams(search)
  const consoleRoute = pathname === '/app' || (pathname === '/' && params.has('screen'))
  const screen = params.get('screen') || 'workspace'
  return {
    publicPage: consoleRoute ? '' : pathname === '/' ? 'home' : pathname === '/support' ? 'support' : '',
    screen: screens.has(screen) ? screen : 'unavailable',
    exists: consoleRoute ? screens.has(screen) : pathname === '/' || pathname === '/support' || authPaths.has(pathname) || policyPaths.has(pathname),
  }
}

export function safeNextPath(value) {
  if (!value || !value.startsWith('/') || value.startsWith('//') || value.includes('\\')) return '/app'
  const url = new URL(value, 'https://private.invalid')
  if (url.origin !== 'https://private.invalid' || url.pathname !== '/app') return '/app'
  return resolvePrivateRoute(url.pathname, url.search).exists ? `${url.pathname}${url.search}` : '/app'
}
