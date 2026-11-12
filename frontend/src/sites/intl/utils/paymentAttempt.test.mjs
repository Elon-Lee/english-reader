import assert from 'node:assert/strict'
import test from 'node:test'
import { createPaymentAttempt } from './paymentAttempt.mjs'

test('payment creation blocks concurrent submits and keeps one idempotency key for retries', () => {
  let sequence = 0
  const attempt = createPaymentAttempt(() => `payment-${++sequence}`)
  assert.equal(attempt.begin('pro'), 'payment-1')
  assert.equal(attempt.begin('pro'), null)
  attempt.finish()
  assert.equal(attempt.begin('pro'), 'payment-1')
  attempt.finish()
  assert.equal(attempt.begin('advanced'), 'payment-2')
})

test('a confirmed payment permits a fresh order for a future renewal', () => {
  let sequence = 0
  const attempt = createPaymentAttempt(() => `payment-${++sequence}`)
  assert.equal(attempt.begin('pro'), 'payment-1')
  attempt.finish(true)
  assert.equal(attempt.begin('pro'), 'payment-2')
})
