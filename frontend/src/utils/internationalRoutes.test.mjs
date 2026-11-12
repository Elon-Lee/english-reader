import assert from 'node:assert/strict'
import test from 'node:test'
import { resolveInternationalRoute, safeInternationalNextPath } from '../sites/intl/routes.mjs'

test('international routes add pricing, purchases, refunds and authenticated membership', () => {
  assert.equal(resolveInternationalRoute('/pricing').publicPage, 'pricing')
  assert.equal(resolveInternationalRoute('/purchase/pro-monthly').publicPage, 'purchase')
  assert.equal(resolveInternationalRoute('/refunds').exists, true)
  assert.equal(resolveInternationalRoute('/app', '?screen=membership').screen, 'membership')
  assert.equal(resolveInternationalRoute('/app', '?screen=reader').screen, 'reader')
  assert.equal(resolveInternationalRoute('/purchase/').exists, false)
})

test('login return permits local purchase routes and rejects external or unknown returns', () => {
  assert.equal(safeInternationalNextPath('/pricing?purchase=pro'), '/pricing?purchase=pro')
  assert.equal(safeInternationalNextPath('/purchase/pro-monthly'), '/purchase/pro-monthly')
  assert.equal(safeInternationalNextPath('/app?screen=membership'), '/app?screen=membership')
  for (const path of ['https://evil.test/', '//evil.test/', '/\\evil.test', '/unknown', '/login']) assert.equal(safeInternationalNextPath(path), '/app')
})
