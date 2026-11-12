import assert from 'node:assert/strict'
import test from 'node:test'
import { resolvePrivateRoute, safeNextPath } from './privateRoutes.mjs'

test('only current private pages and study screens resolve', () => {
  for (const path of ['/', '/support', '/login', '/register', '/terms', '/privacy']) assert.equal(resolvePrivateRoute(path).exists, true, path)
  for (const path of ['/pricing', '/purchase/pro-30', '/refunds']) assert.equal(resolvePrivateRoute(path).exists, false, path)
  assert.equal(resolvePrivateRoute('/app', '?screen=membership').exists, false)
  assert.equal(resolvePrivateRoute('/app', '?screen=reader&id=book').screen, 'reader')
})

test('login redirects only to an existing local study screen', () => {
  for (const value of ['https://evil.invalid', '//evil.invalid', '/\\evil.invalid', '/pricing', '/app?screen=membership']) assert.equal(safeNextPath(value), '/app', value)
  assert.equal(safeNextPath('/app?screen=reader&id=book'), '/app?screen=reader&id=book')
})
