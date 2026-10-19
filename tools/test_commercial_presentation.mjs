import test from 'node:test'
import assert from 'node:assert/strict'
import { formatBytes, displayBenefits, featuredProductId, purchaseAction, isReviewDue, bookDescription } from '../frontend/src/utils/presentation.mjs'

test('storage uses matching units and preserves unknown values', () => {
  assert.equal(formatBytes(507565206), '484.05 MB')
  assert.equal(formatBytes(20 * 1024 ** 3), '20 GB')
  assert.equal(formatBytes(0), '0 B')
  assert.equal(formatBytes(undefined), '—')
})
test('only one configured paid plan receives the recommendation', () => {
  assert.equal(featuredProductId([{ id: 'free', family: 'free', featured: true }, { id: 'a', family: 'advanced', featured: true }, { id: 'p', family: 'pro', featured: true }]), 'a')
  assert.equal(featuredProductId([{ id: 'free', family: 'free', featured: true }]), undefined)
})
test('checkout waits for server eligibility and distinguishes transient failure from downgrade', () => {
  const product = { family: 'advanced', shortName: '进阶版' }
  assert.equal(purchaseAction(product, true).disabled, true)
  assert.equal(purchaseAction(product, true, { error: { code: 'membership_downgrade_not_allowed' } }).disabled, true)
  assert.equal(purchaseAction(product, true, { error: { code: 'network_error' } }).retry, true)
  assert.equal(purchaseAction(product, true, { preview: { changeType: 'renewal' } }).label, '续费进阶版')
  assert.equal(purchaseAction(product, true, { preview: { changeType: 'upgrade' } }).label, '升级到进阶版')
  assert.equal(purchaseAction(product, false).label, '登录后购买 / 兑换')
})
test('existing codes remain reachable when new purchases are unavailable', () => {
  assert.equal(purchaseAction({ family: 'pro', purchaseUrl: '' }, true, { preview: { changeType: 'activation' } }).disabled, false)
})
test('benefit copy clarifies scope without changing quotas or custom benefits', () => {
  const product = { benefits: ['免费包含：公版书架收藏不限量', '最多收藏 20 个视频（公版 + 私人）', '免费包含：词汇语境分析不限次数', '定制说明'] }
  const result = displayBenefits(product)
  assert.equal(result[0], '词汇语境分析不限次数')
  assert.ok(result.includes('官方文本收藏不限量；音视频计入收藏上限'))
  assert.ok(result.includes('最多收藏 20 个视频（公版 + 私人）'))
  assert.ok(result.includes('定制说明'))
})
test('review queue uses actual due dates and treats unscheduled words as ready', () => {
  const now = Date.parse('2026-10-19T00:00:00Z')
  assert.ok(isReviewDue({ payload: {} }, now))
  assert.ok(isReviewDue({ payload: { due_at: '2026-10-18T00:00:00Z' } }, now))
  assert.equal(isReviewDue({ payload: { due_at: '2026-10-20T00:00:00Z' } }, now), false)
})
test('catalog removes duplicate title descriptions but preserves authored summaries', () => {
  assert.notEqual(bookDescription({ title: 'Hello', description: 'Hello', resourceType: 'video' }), 'Hello')
  assert.equal(bookDescription({ title: 'Hello', description: '有意义的介绍' }), '有意义的介绍')
})
