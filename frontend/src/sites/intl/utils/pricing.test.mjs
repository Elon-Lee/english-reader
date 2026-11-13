import test from 'node:test'
import assert from 'node:assert/strict'
import { discountLabel, pricePayload } from './pricing.mjs'

test('exact cents and one decimal discount', () => {
  assert.equal(discountLabel(4900, 1900), '3.9折')
  assert.equal(discountLabel(3167, 1900), '6.0折')
  assert.equal(discountLabel(2000, 790), '4.0折')
  assert.equal(discountLabel(10000, 1), '0.0折')
  assert.equal(discountLabel(0, 0), '无折扣')
  assert.equal(discountLabel(100, 100), '无折扣')
  assert.equal(discountLabel(null, 10), '—')
  assert.deepEqual(pricePayload({ originalPrice: 49.99, salePrice: 19.99 }), { originalAmountCents: 4999, amountCents: 1999 })
})
